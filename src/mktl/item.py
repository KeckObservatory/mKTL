
import logging
import queue
import threading
import time
import traceback

try:
    import numpy
except ImportError:
    numpy = None

from . import protocol
from . import poll
from . import weakref


class Item:
    """ An Item represents a key/value pair, where the key is the name of the
        Item, and the value is whatever is provided by the authoritative daemon.
        The principal way for both clients and daemons to get or set the value
        is via the :func:`value` property.

        A non-authoritative Item will automatically :func:`subscribe` itself to
        any available updates.

        :ivar key: The key (name) for this item.
        :ivar full_key: The store and key for this item, in `store.key` format.
        :ivar store: The :class:`mktl.Store` instance containing this item.
        :ivar config: The JSON description of this item.
        :ivar log_on_set: Indicates whether this item will log SET requests. The default is True.
        :ivar publish_on_set: Indicates whether this item will publish a new value whenever :func:`perform_set` is successfully invoked. The default is True.
    """

    untruths = set((None, False, 0, 'false', 'f', 'no', 'n', 'off', 'disable', ''))

    def __init__(self, store, key, subscribe=True, authoritative=False, pub=None):

        self.authoritative = authoritative
        key = key.lower()
        self.key = key
        self.full_key = store.name + '.' + key
        self.store = store
        self.config = store.config[key]
        self.callbacks = list()
        self.log_on_set = True
        self.publish_on_set = True
        self.subscribed = False
        self.timeout = 120

        self._value = None
        self._value_timestamp = None
        self._daemon_value = None
        self._daemon_value_timestamp = None

        self.pub = pub
        self.sub = None
        self.req = None
        self.rep = None
        self._update_queue = None
        self._update_queue_put = None
        self._update_thread = None
        self._updated = threading.Event()

        # An Item is a singleton in practice; enforce that constraint.

        try:
            old = self.store._items[key]
        except KeyError:
            old = None

        if old is not None:
            raise RuntimeError('duplicate item not allowed: ' + self.full_key)

        self.store._items[key] = self

        # Use the highest-numbered stratum that will handle a full range of
        # queries. This capability is implied by the presence of the 'pub'
        # field in the provenance; this may be made more declarative in the
        # future, instead of the implied role being assumed here.

        provenance = self.config['provenance']
        hostname = None

        for stratum in provenance:
            try:
                pub = stratum['pub']
            except KeyError:
                continue
            else:
                hostname = stratum['hostname']
                rep = stratum['rep']
                break

        if hostname is None:
            # This should never occur, it should not be possible to have a
            # configuration that doesn't contain a provenance.
            raise RuntimeError('cannot find daemon for ' + self.full_key)

        self.sub = protocol.publish.client(hostname, pub)
        self.req = protocol.request.client(hostname, rep)

        try:
            settable = self.config['settable']
        except KeyError:
            settable = True

        if settable == False:
            self.req_set = self.reject_set

        try:
            gettable = self.config['gettable']
        except KeyError:
            gettable = True

        if gettable == False:
            self.req_get = self.reject_get

        if subscribe == True:
            if self.authoritative == True:
                prime = False
            else:
                prime = True

            self.subscribe(prime=prime)


    def _cleanup(self):
        """ Shut down any background processing involved with this item.
            In the general case this is not required; :class:`Item` instances
            are singletons, and should persist for the lifetime of the
            application. But there are some corner cases where they need
            to be replaced; this method facilitates that procedure.
        """

        if self._update_thread is not None:
            self._update_thread.stop()
            self._update_thread = None

        self.callbacks = tuple()
        self.store._items[self.key] = None


    @property
    def formatted(self):
        """ Get and set the human-readable representation of the item.
            For example, the formatted variant of an enumerated type
            is the string string representation, as opposed to the integer
            reported as the current item value. These permutations are driven
            by the JSON configuration of the item. In the absence of any
            configured formatting the current value will be returned as a
            string.

            This property can also be used to set the new value of the item
            using the formatted representation.

            See also :py:attr:`quantity` and :py:attr:`value`.
        """

        # Use self.value as the preferred way to access the value; this
        # ensures it is handled in the appropriate way regardless of whether
        # this specific item is authoritative.

        formatted = self.to_format(self.value)
        return formatted


    @formatted.setter
    def formatted(self, new_value):

        new_value = self.from_format(new_value)
        self.value = new_value


    def from_format(self, value):
        """ Convert the supplied value from its human-readable formatted
            representation, if any, to the on-the-wire representation for
            this item. This conversion is driven by the configuration.

            This is the inverse of :func:`to_format`.
        """

        try:
            unformatted = self.store.config.from_format(self.key, value)
        except:
            message = "format conversion failed for %s:"
            logger = logging.getLogger(__name__)
            logger.exception(message, self.full_key)
            raise

        return unformatted


    def from_payload(self, payload):
        """ Recreate the fundamental Python type of the value from the provided
            :class:`mktl.protocol.message.Payload` instance, and return it to
            the caller.

            This default handler will interpret the bulk component, if any,
            of the payload as an N-dimensional numpy array, with the
            description of the array present in the other fields of the payload.

            This is the inverse of :func:`to_payload`.
        """

        if payload.bulk is not None:

            if numpy is None:
                raise ImportError('numpy module not available')

            bulk = payload.bulk

            shape = payload.shape
            dtype = payload.dtype
            dtype = getattr(numpy, dtype)

            serialized = numpy.frombuffer(bulk, dtype=dtype)
            new_value = numpy.reshape(serialized, newshape=shape)

        else:
            new_value = payload.value


        return new_value


    def from_quantity(self, quantity):
        """ Convert the supplied quantity to a base numeric representation
            if possible, appropriate to the base, unformatted units for this
            item.

            This is the inverse of :func:`to_quantity`.
        """

        value = self.store.config.from_quantity(self.key, quantity)
        return value


    def get(self, refresh=False, formatted=False, quantity=False):
        """ Retrieve the current value. Set *refresh* to True to prompt
            the daemon responding to the request to return the most up-to-date
            value available, potentially bypassing any local cache. Set
            *formatted* to True to receive the human-readable formatting
            of the value, if any such formatting is available; similarly,
            set *quantity* to true to receive the value as a
            :class:`pint.Quantity` instance, which will only work if the
            item is configured to have physical units.

            Use of the :py:attr:`formatted`, :py:attr:`quantity`, and
            :py:attr:`value` properties is encouraged in the case where
            a synchronous refresh is not required.
        """

        if refresh == False and self.subscribed == True and self._value is not None:
            # This is expected to be the average case: the item already has
            # a value because we always subscribe, so a non-refresh get()
            # request can just return the current value.

            if formatted == False and quantity == False:
                # This is expected to be the average case.
                return self.value
            elif formatted == True and quantity == True:
                # A little extra work to honor the intent of getting the
                # quantity with the units specific to the 'formatted'
                # representation. For example, the formatted value could
                # be degrees instead of radians.

                try:
                    units = self.config['units']
                except KeyError:
                    units = None
                else:
                    try:
                        units = units['formatted']
                    except (KeyError, TypeError):
                        pass

                quantity = self.to_quantity(self._value, units)
                return quantity
            elif quantity == True:
                return self.quantity
            elif formatted == True:
                return self.formatted
            else:
                raise ValueError('formatted+quantity arguments must be boolean')

        elif refresh == False:
            request = protocol.message.Request('GET', self.full_key)
        elif refresh == True:
            payload = protocol.message.Payload(None, refresh=True)
            request = protocol.message.Request('GET', self.full_key, payload)
        else:
            raise TypeError('refresh argument must be a boolean')

        self.req.send(request)
        response = request.wait(self.timeout)

        if response is None:
            raise RuntimeError('GET failed: no response to request')

        error = response.payload.error
        if error is not None and error != '':
            e_type = error['type']
            e_text = error['text']

            # Logging this error may not have lasting value; remote errors
            # should not occur, and there ought to be a good way to expose
            # them without overwhelming the caller.

            try:
                error['debug']
            except KeyError:
                pass
            else:
                message = "remote GET error for %s:"
                logger = logging.getLogger(__name__)
                logger.error(message, self.full_key)
                logger.error(error['debug'])

            ### The exception type here should be something unique
            ### instead of a RuntimeError.
            raise RuntimeError("GET failed: %s: %s" % (e_type, e_text))

        self._update(response)

        # This explicit check for None eliminates the possibility of subsequent
        # use of properties resulting in an infinite loop, where get() is called
        # because there is no cached value.

        if self._value is None:
            return None

        # This block duplicates the check at the beginning of this method.

        if formatted == False and quantity == False:
            return self.value
        elif formatted == True and quantity == True:
            try:
                units = self.config['units']
            except KeyError:
                units = None
            else:
                try:
                    units = units['formatted']
                except (KeyError, TypeError):
                    pass

            quantity = self.to_quantity(self._value, units)
            return quantity

        elif quantity == True:
            return self.quantity
        elif formatted == True:
            return self.formatted
        else:
            raise ValueError('formatted+quantity arguments must be boolean')


    def perform_get(self):
        """ Acquire the most up-to-date value available for this :class:`Item`
            and return it to the caller. Return None if no new value is
            available; if a :class:`mktl.protocol.message.Payload` instance
            is returned it will be used as-is, otherwise the return value
            will be passed to :func:`to_payload` for encapsulation.

            Returning None will not clear the currently known value, that will
            only occur if the returned Payload instance is assigned None as the
            'value'; this is not expected to be a common occurrence, but if a
            custom :func:`perform_get` implementation wants that to occur they
            need to instantiate and return the Payload instance directly rather
            than use :func:`to_payload`.
        """

        # This default implementation is strictly caching, there is nothing
        # to refresh.

        payload = self.to_payload()
        return payload


    def perform_set(self, new_value):
        """ Implement any custom behavior that should occur as a result of
            a set request for this item. No return value is expected. Any
            subclass implementations should raise an exception in order to
            trigger an error response.

            Any return value, though again none is expected, will be
            encapsulated via :func:`to_payload`, after the same fashion as
            :func:`perform_get`, and included in the response to the original
            request.
        """

        # This default implementation is a no-op, there is nothing to set.
        # the local cache of the new value will be updated when the value
        # is published.

        pass


    def poll(self, period):
        """ Poll for a new value every *period* seconds. Polling will be
            discontinued if *period* is set to None or zero. Polling will
            invoke :func:`req_poll`, and occurs at the requested interval
            within a background thread unique to this item.
        """

        poll.start(self.req_poll, period)


    def publish(self, new_value, timestamp=None, repeat=False):
        """ Publish a new value, which is expected to be the Python native
            representation of the new value. If *timestamp* is set it is
            expected to be a UNIX epoch timestamp; the current time will be
            used if it is not provided. Newly published values are always
            cached locally. If *repeat* is set to True the value will be
            published regardless of whether it is a repeat of the previously
            published value.

            Note that, for simple cases, an authoritative daemon can set the
            :func:`value` property to publish a new value instead of calling
            :func:`publish` directly. In other words, these two calls are
            equivalent::

                item.value = new_value
                item.publish(new_value)
        """

        if timestamp is None:
            timestamp = time.time()
        else:
            timestamp = float(timestamp)

        # publish() does not require a Payload instance as an argument to
        # allow flexibility in cases where the timestamp is not already
        # established, though in the average case publish() will be invoked
        # as a result of a req_poll() call, which already has a Payload
        # instance.

        payload = self.to_payload(new_value, timestamp)
        changed = False

        if repeat == False:
            if payload.bulk is None:
                changed = self._daemon_value != new_value
            else:
                if self._daemon_value is None and new_value is not None:
                    changed = True
                elif self._daemon_value is not None and new_value is None:
                    changed = True
                else:
                    ### This check could be expensive for large arrays.
                    match = (self._daemon_value & new_value).all()
                    changed = not match

        if changed == True:
            self._daemon_value = new_value
            self._daemon_value_timestamp = timestamp


        if changed == True or repeat == True:
            key = self.full_key
            message = protocol.message.Broadcast('PUB', key, payload)

            # One could bypass the normal broadcast handling internally
            # within a daemon by putting the message in self._update_queue
            # instead of relying on the full ZeroMQ-based broadcast handling.
            # This would be more efficient, but there is something to be said
            # for fully exercising the normal handling chain in identical
            # fashion for all pub/sub interactions.

            self.pub.publish(message)


    @property
    def quantity(self):
        """ Get and set the current value of the item as a
            :class:`pint.Quantity` instance.

            This property can also be used to set the new value of the item
            using a valid :class:`pint.Quantity` instance; the provided
            quantity will be translated to the base units of the item before
            proceeding.

            See also :py:attr:`formatted` and :py:attr:`value`.
        """

        # Use self.value as the preferred way to access the value; this
        # ensures it is handled in the appropriate way regardless of whether
        # this specific item is authoritative.

        quantity = self.to_quantity(self.value)
        return quantity


    @quantity.setter
    def quantity(self, new_quantity):

        new_value = self.from_quantity(new_quantity)
        self.value = new_value


    def register(self, method, prime=False):
        """ Register a callback to be invoked whenever a new value is received
            from a remote daemon, regardless of how that new value arrived.
            :func:`subscribe` will automatically be invoked if it has not been
            invoked for this :class:`Item` instance, the client does not need
            to call it separately. If *prime* is set to True the callback will
            be invoked using the current value of the item, if any, before
            returning; no priming call will occur if the item has no value.
        """

        if callable(method):
            pass
        else:
            raise TypeError('the registered method must be callable')

        reference = weakref.ref(method)
        self.callbacks.append(reference)

        if self.subscribed == False:
            self.subscribe()
        elif prime == True:
            if self._value is not None or self._daemon_value is not None:
                method(self, self.value, self.timestamp)


    def reject_get(self, *args, **kwargs):
        """ Reject a GET request. This method is only invoked if an Item
            is not gettable (write-only).
        """

        raise TypeError(self.key + ' is not a gettable item')


    def reject_set(self, *args, **kwargs):
        """ Reject a SET request. This method is only invoked if an Item
            is not settable (read-only).
        """

        raise TypeError(self.key + ' is not a settable item')


    def req_get(self, request):
        """ Handle a GET request. The *request* argument is a
            :class:`protocol.message.Request` instance; the value returned
            from :func:`req_get` is identical to the value returned by
            :func:`perform_get`, which is where custom handling by subclasses
            is expected to occur.
        """

        try:
            refresh = request.payload.refresh
        except AttributeError:
            refresh = False

        if refresh == True:
            payload = self.req_poll()
        else:
            payload = self.to_payload()

        return payload


    def req_initialize(self, request):
        """ This is a sub-case of :func:`req_set` that bypasses some of the
            normal checks, like whether an item is settable or valid.
            :func:`perform_set` will not be called as a result of this
            initialization; values initialized in this fashion are always
            published.
        """

        payload = request.payload
        if payload is None:
            return

        new_value = self.from_payload(payload)
        self.publish(new_value)


    def req_poll(self, repeat=False):
        """ Handle a background poll request, established by calling
            :func:`poll`. :func:`perform_get` is where custom handling by
            subclasses is expected to occur. The payload returned from
            :func:`req_poll` is identical to the payload returned by
            :func:`perform_get`.

            A common pattern for custom subclasses involves registering
            :func:`req_poll` as a callback on other items, so that the value
            of this item can be refreshed when external events occur.
        """

        response = self.perform_get()

        if response is None:
            # Direct assertion that there is no new value. In this case,
            # return the current value(s), and discontinue further processing.
            return self.to_payload()
        elif isinstance(response, protocol.message.Payload):
            payload = response
        else:
            payload = self.to_payload(response)

        # The default behavior is to only publish a value if the value has
        # changed. That check is made is in the publish() method.

        self.publish(payload.value, payload.time, repeat)

        return payload


    def req_set(self, request):
        """ Handle a SET request. The *request* argument is a
            :class:`protocol.message.Request` instance; the value returned
            from :func:`req_set` will be returned to the caller, though no
            such return value is expected. Any calls to :func:`req_set` are
            expected to block until completion. Custom handling by subclasses
            is expected to occur in :func:`perform_set`.

            If the `publish_on_set` attribute is set to True (this is the
            default) a call to :func:`publish` will occur at the tail end
            of any successful SET request. Custom subclasses can set this
            attribute to False to inhibit that behavior.
        """

        payload = request.payload
        if payload is None:
            return

        if self.log_on_set:
            logger = logging.getLogger(__name__)
            request.log(logger)

        new_value = self.from_payload(payload)
        new_value = self.validate_type(new_value)
        new_value = self.validate(new_value)

        # All custom logic is expected to occur in the perform_set() method,
        # similar to perform_get().

        response = self.perform_set(new_value)

        # Provide a default, effectively empty response to indicate the set
        # request is complete. If the custom implementation had something
        # special to say, by all means, let them say it, though by default
        # the contents of the response payload are not inspected.

        if response is None:
            payload = protocol.message.Payload(True)
        elif isinstance(response, protocol.message.Payload):
            payload = response
        else:
            payload = self.to_payload(response)

        # Not all custom implementations want req_set() to publish the newly
        # set value. The publish_on_set attribute allows subclasses to inhibit
        # this behavior.

        if self.publish_on_set == True:
            self.publish(new_value)

        return payload


    def set(self, new_value, wait=True, formatted=False, quantity=False):
        """ Set a new value. Set *wait* to True to block until the request
            completes; this is the default behavior. If *wait* is set to False,
            the caller will be returned a :class:`mktl.protocol.message.Request`
            instance, which has a :func:`mktl.protocol.message.Request.wait`
            method that can optionally be invoked to block until completion of
            the request; the wait will return immediately once the request is
            satisfied. There is no return value for a blocking request; failed
            requests will raise exceptions.

            The optional *formatted* and *quantity* options enable calling
            :func:`set` with either the string-formatted representation or
            the :class:`pint.Quantity` representation of the item; the new
            value is still the first argument, but set one of *formatted*
            or *quantity* to True to indicate it should be interpreted.

            Use of the :py:attr:`formatted`, :py:attr:`quantity`, and
            :py:attr:`value` properties is encouraged in the case where
            a blocking set operation is desired.
        """

        self._updated.clear()

        # This next set of conditions mirrors what occurs in the get() method,
        # but no additional special handling is required for the case where
        # both formatted and quantity are True: a quantity is a quantity,
        # regardless of the actual units.

        if formatted == False and quantity == False:
            pass
        elif quantity == True:
            new_value = self.from_quantity(new_value)
        elif formatted == True:
            new_value = self.from_format(new_value)
        else:
            raise ValueError('formatted+quantity arguments must be boolean')

        payload = self.to_payload(new_value)
        payload.add_origin()
        message = protocol.message.Request('SET', self.full_key, payload)
        self.req.send(message)

        if wait == False:
            return message

        response = message.wait(self.timeout)

        if response is None:
            raise RuntimeError("SET of %s failed: no response to request" % (self.key))

        error = response.payload.error
        if error is not None and error != '':
            e_type = error['type']
            e_text = error['text']

            # Logging this error may not have lasting value; remote errors
            # should not occur, and there ought to be a good way to expose
            # them without overwhelming the caller.

            try:
                error['debug']
            except KeyError:
                pass
            else:
                message = "remote SET error for %s:"
                logger = logging.getLogger(__name__)
                logger.error(message, self.full_key)
                logger.error(error['debug'])

            ### The exception type here should be something unique
            ### instead of a RuntimeError.
            error = "SET of %s failed: %s: %s" % (self.key, e_type, e_text)
            raise RuntimeError(error)


        # Wait a smidge for local values to update in response to the set
        # request. This is not guaranteed to occur, but it often does-- and
        # typical client behavior expects the local value to be up-to-date
        # upon returning from a blocking set() operation. If everything is
        # working as expected this wait() should return immediately.

        # It would be better if this delay blocked on the definite arrival
        # of a broadcast, as opposed to hoping that one arrives. That's part
        # of why this arbitrary wait is so short.

        self._updated.wait(0.01)


    def subscribe(self, prime=True):
        """ Subscribe to all future broadcast events. Doing so ensures that
            locally cached values will always be current, regardless of any
            local polling behavior. If *prime* is True a call
            will be made to :func:`get` to refresh the locally cached value
            before this method returns. A failure on a priming call will be
            caught and ignored, it will not be reported to the caller.

            A non-authoritative :class:`Item` will automatically call
            this method` upon being instantiated; an authoritative variant
            will do so upon a call to :func:`register`. In other words, it
            should never be necessary to call this method directly.
        """

        if self.subscribed == True:
            return

        # A local thread is used to execute callbacks to ensure we don't tie
        # up the protocol.publish.Client from moving on to the next broadcast.
        # This does mean there's an extra background thread for every Item
        # that receives callbacks; on older systems we are limited to 4,000
        # such threads before running into resource limitations, modern systems
        # allow 32,000 or more, sometimes depending on the amount of physical
        # memory in the system.

        # A thread pool might be just as performant for this purpose, but the
        # control flow in that thread would be a lot more complex. Having a
        # dedicated _Updater background thread for each Item with an active
        # subscription makes the processing straightforward.

        # The reference to SimpleQueue.put() gets deallocated immediately if we
        # don't keep a local reference; the weak reference used in register()
        # (despite using a weak method wrapper) doesn't function once it goes
        # out of scope.

        try:
            # Available in Python 3.7+.
            self._update_queue = queue.SimpleQueue()
        except AttributeError:
            self._update_queue = queue.Queue()

        self._update_queue_put = self._update_queue.put
        self._update_thread = _Updater(self._update, self._update_queue)

        self.sub.register(self._update_queue_put, self.full_key)
        self.subscribed = True

        if prime == True:
            try:
                self.get(refresh=True)
            except (TimeoutError, RuntimeError):
                # Timeout errors and remote errors on priming reads are
                # thrown away; an error here means the remote daemon is not
                # available to respond to requests, but despite that error
                # the subscription will still be valid when the remote daemon
                # returns to service.

                # Other exception types indicate programming errors and should
                # still be raised.
                pass

        ### If this Item is a leaf of a structured Item we may need to register
        ### a callback on a topic substring of our key name.


    @property
    def timestamp(self):
        """ Get the timestamp associated with the current value of the item.
        """

        if self.authoritative == True:
            return self._daemon_value_timestamp
        else:
            return self._value_timestamp


    def to_format(self, value):
        """ Convert the supplied value to its human-readable formatted
            representation, if any. This conversion is driven by the
            configuration for this item.

            This is the inverse of :func:`from_format`.
        """

        try:
            formatted = self.store.config.to_format(self.key, value)
        except:
            formatted = str(self.value)

        return formatted


    def to_payload(self, value=None, timestamp=None):
        """ Interpret the provided arguments into a
            :class:`mktl.protocol.message.Payload` instance; if the *value* is
            not specified the current value of this :class:`Item` will be
            used; if the *timestamp* is not specified the current time will
            be used. This is particularly important as a step in a custom
            :func:`perform_get` implementation.

            This is the inverse of :func:`from_payload`.
        """

        if value is None:
            if self.authoritative == False:
                value = self._value
            else:
                value = self._daemon_value

        elif timestamp is None:
            # If the value is specified, but the timestamp is not, use the
            # current time as the timestamp-- the next condition would instead
            # use the previous timestamp, which is not appropriate for a new
            # payload.
            timestamp = time.time()

        if timestamp is None:
            timestamp = self.timestamp

        # Perhaps there is a more declarative way to know whether a given
        # value is expected to be bulk data; perhaps reference the per-Item
        # configuration? Or does an attribute need to be set to make the
        # expected behavior explicit?

        try:
            bulk = value.tobytes()
        except AttributeError:
            bulk = None
            payload = protocol.message.Payload(value, timestamp)
        else:
            shape = value.shape
            dtype = str(value.dtype)
            payload = protocol.message.Payload(None, timestamp, bulk=bulk, shape=shape, dtype=dtype)

        return payload


    def to_quantity(self, value, units=None):
        """ Convert the supplied value to a :class:`pint.Quantity`
            representation, if possible, appropriate to the units,
            if any, for this item. The default units of the item can be
            overridden by providing a *units* argument, which is either a
            :class:`pint.Unit` instance or a string acceptable to the
            :func:`pint.UnitRegistry.parse_units` method. Exceptions will
            be raised if the units are not recognized or the item doesn't
            have units at all.

            This is the inverse of :func:`from_quantity`.
        """

        quantity = self.store.config.to_quantity(self.key, value, units)
        return quantity


    def validate(self, value):
        """ A hook for a daemon to validate a new value. The default behavior
            is a no-op; any checks should raise exceptions if they encounter
            a problem with the incoming value. The 'validated' value must be
            returned by this method; this allows for the possibility that
            the incoming value has been translated to a more acceptable format,
            for example, converting the string '123' to the integer 123 for a
            numeric item type.
        """

        return value


    def validate_type(self, value):
        """ Inspect the type of this item, if any, and reassign the reference
            to this method to the appropriate type-specific validation.
        """

        try:
            type = self.config['type']
        except KeyError:
            type = None
        else:
            if type == '':
                type = None

        if type is None:
            self.validate_type = self._validate_typeless
        else:
            type = type.lower()

            if type == 'boolean':
                self.validate_type = self._validate_boolean
            elif type == 'enumerated':
                self.validate_type = self._validate_enumerated
            elif type == 'mask':
                self.validate_type = self._validate_enumerated
            elif type == 'numeric':
                self.validate_type = self._validate_numeric
            elif type == 'numeric array':
                self.validate_type = self._validate_numeric_array
            else:
                # This includes the 'string' type, for which there is no
                # additional validation, hence typeless for this purpose.
                self.validate_type = self._validate_typeless

        return self.validate_type(value)


    def _validate_boolean(self, value):
        value = self._validate_enumerated(value)

        # The unformatted value for a boolean is a boolean. A successful return
        # from _validate_enumerated() will provide an integer, normalize that
        # value here.

        if value:
            value = True
        else:
            value = False

        return value


    def _validate_enumerated(self, value):
        # Performing the format conversion confirms that the provided value
        # is valid for the locally defined enumeration (or mask).
        self.to_format(value)

        # The unformatted value for an enumeration (or mask) is an integer.
        value = int(value)

        return value


    def _validate_numeric(self, value):

        if isinstance(value, float):
            pass
        else:
            try:
                value = int(value)
            except:
                value = float(value)

        # This is where a range check should go.

        return value


    def _validate_numeric_array(self, value):

        validated = list()

        for field in value:
            field = self._validate_numeric(field)
            validated.append(field)

        return validated


    def _validate_typeless(self, value):
        return value


    @property
    def value(self):
        """ Get and set the current value of the item. The caller should use
            :func:`get` and :func:`set` directly for additional control over
            how these respective calls are handled, the handling invoked here
            relies on default values for all optional arguments.

            See also :py:attr:`formatted` and :py:attr:`quantity`.
        """

        if self.authoritative == True:
            return self._daemon_value

        if self._value is None:
            self.get(refresh=True)

        return self._value


    @value.setter
    def value(self, new_value):

        if self.authoritative == True:
            self.publish(new_value)
        else:
            self.set(new_value)


    def _propagate(self, new_data, new_timestamp):
        """ Invoke any registered callbacks upon receipt of a new value.
        """

        if self.callbacks:
            pass
        else:
            return

        invalid = list()

        for reference in self.callbacks:
            callback = reference()

            if callback is None:
                invalid.append(reference)

            try:
                callback(self, new_data, new_timestamp)
            except:
                message = "callback failed for %s:"
                logger = logging.getLogger(__name__)
                logger.exception(message, self.full_key)
                continue

        for reference in invalid:
            self.callbacks.remove(reference)


    def _update(self, message):
        """ The caller received a new data segment either from a directed
            GET request or from a PUB subscription.
        """

        payload = message.payload

        if payload is None:
            return

        new_value = self.from_payload(payload)
        timestamp = message.payload.time

        self._value = new_value
        self._value_timestamp = timestamp
        self._updated.set()
        self._propagate(new_value, timestamp)


    def __bool__(self):
        current = self.value

        if current in self.untruths:
            return False
        else:
            try:
                lower = current.lower()
            except AttributeError:
                return True

            if lower in self.untruths:
                return False

        return True


    def __bytes__(self):

        try:
            bytes = self.value.tobytes()
        except AttributeError:
            bytes = bytes(str(self))

        return bytes


    def __hash__(self):
        """ The __hash__() method needs to be defined in order for Items to
            be usable in dictionaries. Note there is a difference between the
            meaning of __hash__() and __eq__() as defined here: the hash is
            relying on the identity of the Item instance, where equivalence
            is based on the (mutable) value of the item.
        """
        return id(self)


    def __str__(self):
        return str(self.formatted)


    def __lt__(self, other):
        return self.value < other

    def __le__(self, other):
        return self.value <= other

    def __eq__(self, other):
        return self.value == other

    def __ne__(self, other):
        return self.value != other

    def __gt__(self, other):
        return self.value > other

    def __ge__(self, other):
        return self.value >= other

    def __add__(self, other):
        return self.value + other

    def __radd__(self, other):
        return other + self.value

    def __sub__(self, other):
        return self.value - other

    def __rsub__(self, other):
        return other - self.value

    def __mul__(self, other):
        return self.value * other

    def __rmul__(self, other):
        return other * self.value

    def __div__(self, other):
        return self.value / other

    def __rdiv__(self, other):
        return other / self.value

    def __truediv__(self, other):
        current = float(self.value)
        return current / other

    def __rtruediv__(self, other):
        current = float(self.value)
        return other / current

    def __mod__(self, other):
        return self.value % other

    def __rmod__(self, other):
        return other % self.value

    def __floordiv__(self, other):
        return self.value // other

    def __rfloordiv__(self, other):
        return other // self.value

    def __divmod__(self, other):
        return (self.value // other, self % other)

    def __rdivmod__(self, other):
        return (other // self.value, other % self)

    def __pow__(self, other):
        return self.value ** other

    def __rpow__(self, other):
        return other ** self.value

    def __neg__(self):
        return -self.value

    def __pos__(self):
        return +self.value

    def __abs__(self):
        return abs(self.value)

    def __invert__(self):
        return ~self.value

    def __and__(self, other):
        return self.value & other

    def __rand__(self, other):
        return other & self.value

    def __or__(self, other):
        return self.value | other

    def __ror__(self, other):
        return other | self.value

    def __xor__(self, other):
        return self.value ^ other

    def __rxor__(self, other):
        return other ^ self.value


    def __inplace(self, method, value):

        if self.subscribed == False:
            self.subscribe()

        modified = method(value)
        self.set(modified)

        ## Though the call to set() blocks until the request is complete
        ## there is no guarantee that the broadcast of the updated value
        ## has arrived. Is there a good way to block until that occurs?
        ## Some kind of wait-for-broadcast method? A transient callback
        ## that goes out of scope?

        return self

    def __iadd__(self, value):
        return self.__inplace(self.__add__, value)

    def __isub__(self, value):
        return self.__inplace(self.__sub__, value)

    def __imul__(self, value):
        return self.__inplace(self.__mul__, value)

    def __idiv__(self, value):
        return self.__inplace(self.__div__, value)

    def __itruediv__(self, value):
        return self.__inplace(self.__truediv__, value)

    def __ifloordiv__(self, value):
        return self.__inplace(self.__floordiv__, value)

    def __imod__(self, value):
        return self.__inplace(self.__mod__, value)

    def __ipow__(self, value):
        return self.__inplace(self.__pow__, value)

    def __iand__(self, value):
        return self.__inplace(self.__and__, value)

    def __ixor__(self, value):
        return self.__inplace(self.__xor__, value)

    def __ior__(self, value):
        return self.__inplace(self.__or__, value)

# end of class Item



class _UpdaterWake(RuntimeError):
    pass


class _Updater:
    """ Background thread to invoke any per-Item callbacks. This allows the
        event processing loop sitting on the ZeroMQ socket to be consistent
        and tight, where a user-provided callback may require an unbounded
        amount of time to process.
    """

    def __init__(self, method, queue):

        self.method = method
        self.queue = queue
        self.shutdown = False

        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def run(self):

        while True:
            if self.shutdown == True:
                break

            try:
                dequeued = self.queue.get(timeout=300)
            except queue.Empty:
                continue

            if isinstance(dequeued, _UpdaterWake):
                continue

            self.method(dequeued)


    def stop(self):
        self.shutdown = True
        self.wake()


    def wake(self):
        self.queue.put(_UpdaterWake())


# end of class Updater


### Additional subclasses would go here, if they existed. Numeric types, bulk
### keyword types, etc.


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
