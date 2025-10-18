
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

        provenance = self.config['provenance']

        # Use the highest-numbered stratum that will handle a full range of
        # queries. This capability is implied by the presence of the 'pub'
        # field in the provenance; this may be made more declarative in the
        # future, instead of the implied role being assumed here.

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
            raise RuntimeError('cannot find daemon for ' + self.full_key)

        self.sub = protocol.publish.client(hostname, pub)
        self.req = protocol.request.client(hostname, rep)

        # An Item is a singleton in practice; enforce that constraint here.

        try:
            old = self.store._items[key]
        except KeyError:
            old = None

        if old is not None:
            raise RuntimeError('duplicate item not allowed: ' + self.full_key)

        self.store._items[key] = self

        if subscribe == True:
            if self.authoritative == True:
                prime = False
            else:
                prime = True

            self.subscribe(prime=prime)


    @property
    def formatted(self):
        """ The human-readable representation, if any, of an item value.
        """

        ### Interpret self.value according to the item description

        return str(self.value)


    @formatted.setter
    def formatted(self, new_value):

        ### interpret new_value according to the item description
        ### or punt, and let the daemon handle it

        self.set(new_value)


    def get(self, refresh=False, formatted=False):
        """ Retrieve the current value. Set *refresh* to True to prompt
            the daemon handling the request to provide the most up-to-date
            value available, potentially bypassing any local cache. Set
            *formatted* to True to receive the human-readable formatting
            of the value, if any such formatting is available.
        """

        if refresh == False and self.subscribed == True and self._value is not None:
            if formatted == True:
                return self.formatted
            else:
                return self._value

        request = dict()

        request = protocol.message.Payload(None, refresh=refresh)
        message = protocol.message.Request('GET', self.full_key, request)
        self.req.send(message)
        response = message.wait(self.timeout)

        if response == None:
            raise RuntimeError('GET failed: no response to request')

        error = response.payload.error
        if error is not None and error != '':
            e_type = error['type']
            e_text = error['text']

            ### This debug print should be removed.
            try:
                print(error['debug'])
            except KeyError:
                pass

            ### The exception type here should be something unique
            ### instead of a RuntimeError.
            raise RuntimeError("GET failed: %s: %s" % (e_type, e_text))

        self._update(response)

        if formatted == True:
            return self.formatted
        else:
            return self._value


    def poll(self, period):
        """ Poll for a new value every *period* seconds. Polling will be
            discontinued if *period* is set to None or zero. The actual
            acquisition of a new value is accomplished via the :func:`req_poll`
            method, which in turn leans heavily on :func:`req_refresh` to do
            the actual work.
        """

        poll.start(self.req_poll, period)


    def publish(self, new_value, timestamp=None, repeat=False):
        """ Publish a new value, which is expected to be the Python binary
            representation of the new value.
            If *timestamp* is set it is expected to be
            a UNIX epoch timestamp; the current time will be used if it is not
            provided. Newly published values are always cached locally.

            Note that, for simple cases, an authoritative daemon can set the
            :func:`value` property to publish a new value instead of calling
            :func:`publish` directly.
        """

        if timestamp is None:
            timestamp = time.time()
        else:
            timestamp = float(timestamp)

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


        # The local call to manipulate the _update_queue is presently commented
        # out because the daemon-aware handling in subscribe() is not enabled.
        # This could be enabled if allowing client-facing updates to occur via
        # the usual PUB/SUB machinery is too expensive.

        if changed == True or repeat == True:
            key = self.full_key
            message = protocol.message.Broadcast('PUB', key, payload)

            ### self._update_queue.put(message)
            self.pub.publish(message)


    def register(self, method):
        """ Register a callback to be invoked whenever a new value is received,
            either by a direct :func:`get` request or the arrival of an
            asynchronous broadcast. :func:`subscribe` will automatically be
            invoked as necessary, the client does not need to call it
            separately.
        """

        if callable(method):
            pass
        else:
            raise TypeError('the registered method must be callable')

        reference = weakref.ref(method)
        self.callbacks.append(reference)

        if self.subscribed == False:
            self.subscribe()


    def req_get(self, request):
        """ Handle a GET request. A typical subclass should not need to
            re-implement this method, implementing :func:`req_refresh`
            would normally be sufficient. The *request* argument is a
            :class:`protocol.message.Request` instance, parsed from the
            on-the-wire request. The value returned from :func:`req_get`
            is identical to the value returned by :func:`req_refresh`.
        """

        ### TODO:
        ### Should req_get put the response in as request.response,
        ### instead of returning a payload?

        try:
            refresh = request.payload.refresh
        except AttributeError:
            refresh = False

        if refresh == True:
            payload = self.req_poll()
        else:
            payload = self.to_payload()

        return payload


    def req_poll(self, repeat=False):
        """ Entry point for calls established by :func:`poll`; a typical
            subclass should not need to reimplement this method. The main reason
            :func:`req_poll` exists is to streamline the expected behavior of
            :func:`req_refresh`, allowing it to focus entirely on what it means
            to acquire a new value; after receiving the refreshed value,
            :func:`req_poll` will additionally publish the new value. A common
            pattern for custom subclasses involves registering :func:`req_poll`
            as a callback on other items, so that the local value of this item
            can be refreshed when events occur elsewhere within a daemon.

            For convenience, the value returned from :func:`req_poll` is
            identical to the value returned by :func:`req_refresh`.
        """

        payload = self.req_refresh()

        if payload is None:
            return

        new_value = payload.value
        timestamp = payload.time

        # The default behavior is to only publish a value if the value has
        # changed. That check is made is in the publish() method.

        self.publish(new_value, timestamp=timestamp, repeat=repeat)

        return payload


    def req_refresh(self):
        """ Acquire the most up-to-date value available for this :class:`Item`
            and return it to the caller. The return value is a dictionary,
            with a 'value' key containing the Python binary representation of
            the item value, and a 'time' key with a UNIX epoch timestamp
            representing the last-changed time for that value. Returning None
            is expected if no new value is available; returning None will not
            clear the currently known value, that is only done if the returned
            dictionary contains None as the 'value'.

            Examples::

                {'time': 1234.5678, 'value': 54}
                {'time': 8765.4321, 'value': None}
        """

        # This implementation is strictly caching, there is nothing to refresh.

        payload = self.to_payload()
        return payload


    def req_set(self, request):
        """ Handle a client-initiated SET request. Any calls to :func:`req_set`
            are expected to block until completion of the request; no return
            value of significance is expected, though one can be provided and
            will be returned to the client, even if the client does not use
            it. Any errors should be indicated by raising an exception.

            The *request* is a :class:`protocol.message.Request` instance.
        """

        new_value = self._recreate_value(request)
        new_value = self.validate(new_value)
        self.publish(new_value)

        # If req_set() returns a payload it will be returned to the caller;
        # absent any explicit response (not required, nor expected), a default
        # response will be provided.

        ### Perhaps req_set should put the response in as request.response.



    def set(self, new_value, wait=True):
        """ Set a new value. Set *wait* to True to block until the request
            completes; this is the default behavior. If *wait* is set to False,
            the caller will be returned a :class:`mktl.protocol.message.Request`
            instance, which has a :func:`mktl.protocol.message.Request.wait`
            method that can optionally be invoked to block until completion of
            the request; the wait will return immediately once the request is
            satisfied. There is no return value for a blocking request; failed
            requests will raise exceptions.
        """

        self._updated.clear()

        payload = self.to_payload(new_value)
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

            ### This debug print should be removed.
            try:
                print(error['debug'])
            except KeyError:
                pass

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
            locally cached values will always be current, regardless of whether
            :func:`get` has been invoked recently. If *prime* is True a call
            will be made to :func:`get` to refresh the locally cached value
            before returning.
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

        self._update_queue = queue.SimpleQueue()
        self._update_queue_put = self._update_queue.put
        self._update_thread = _Updater(self._update, self._update_queue)

        ### This subscription against self.sub could be omitted if the
        ### Item is in a Daemon context. See the publish() method for the extra
        ### call to the _update_queue that needs to be enabled to bypass that
        ### machinery.

        self.sub.register(self._update_queue_put, self.full_key)
        self.subscribed = True

        if prime == True:
            self.get(refresh=True)

        ### If this Item is a leaf of a structured Item we may need to register
        ### a callback on a topic substring of our key name.


    def to_payload(self, value=None, timestamp=None):
        """ Interpret the current value of this item (or the provided
            arguments, if any) into a :class:`protocol.message.Payload`
            instance, appropriate for inclusion in a
            :class:`protocol.message.Message` instance.

            This is the inverse of :func:`_recreate_value`.
        """

        if value is None:
            if self.authoritative == False:
                value = self._value
            else:
                value = self._daemon_value

        if timestamp is None:
            if self.authoritative == False:
                timestamp = self._value_timestamp
            else:
                timestamp = self._daemon_value_timestamp

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


    def validate(self, value):
        """ A hook for a daemon to validate a new value. The default behavior
            is a no-op; any checks should raise exceptions if they encounter
            a problem with the incoming value. The 'validated' value should
            be returned by this method; this allows for the possibility that
            the incoming value has been translated to a more acceptable format,
            for example, converting '123' to the bare number 123 for a numeric
            item type.
        """

        return value


    @property
    def value(self):
        """ Get and set the current value of the item. Invoke :func:`get` and
            :func:`set` directly for additional control over how these calls
            are handled.
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
                ### This should probably be logged in a more graceful fashion.
                print(traceback.format_exc())
                continue

        for reference in invalid:
            self.callbacks.remove(reference)


    def _recreate_value(self, message):
        """ Recreate the fundamental Python type of the value from the provided
            *message*.

            This default handler will interpret the bulk component, if any,
            as an N-dimensional numpy array, with the description of the
            array present in the payload of the message.

            This is the inverse of :func:`to_payload`.
        """

        ### TODO: should this work on a Payload instead of a Message?

        payload = message.payload
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
            new_value = message.payload.value


        return new_value


    def _update(self, message):
        """ The caller received a new data segment either from a directed
            GET request or from a PUB subscription.
        """

        new_value = self._recreate_value(message)
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


    # __hash__() is not defined, because it would be tied to the item key,
    # and would clash with the use of __eq__() defined below, which is not
    # tied to the key. This was a point of some confusion for comparison
    # operations in KTL Python, and the inability to use Item instances as
    # keys in a dictionary due to the absence of __hash__() seems like a
    # lesser price to pay.


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
