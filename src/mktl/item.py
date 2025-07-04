
import queue
import threading
import time
import traceback

try:
    import numpy
except ImportError:
    numpy = None

from . import Config
from . import Protocol
from . import WeakRef
from .Daemon import Poll


class Item:
    """ An Item represents a key/value pair, where the key is the name of the
        Item, and the value is whatever is provided by the daemon, according to
        :func:`get` and :func:`subscribe` requests. A :func:`set` request does
        not update the local value, it only issues a request to the remote
        daemon; it is the daemon's responsibility to issue a post-set update
        with any new value(s).
    """

    untruths = set((None, False, 0, 'false', 'f', 'no', 'n', 'off', 'disable', ''))

    def __init__(self, store, key, subscribe=True):

        self.authoritative = False
        self.key = key
        self.full_key = store.name + '.' + key
        self.store = store
        self.config = store.config[key]

        self.callbacks = list()
        self.value = None
        self._daemon_value = None
        self._daemon_value_timestamp = None
        self.req = None
        self.subscribed = False
        self.timeout = 120
        self._update_queue = None
        self._update_queue_put = None
        self._update_thread = None

        item_config = store.config[key]
        provenance = item_config['provenance']

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
                req = stratum['req']
                break

        if hostname is None:
            raise RuntimeError('cannot find daemon for ' + self.full_key)

        ### A bit of tight coupling here to try and determine if we're
        ### the authoritative item. It'd be nice if this was more direct.

        try:
            store_provenance = store.provenance[0]
        except AttributeError:
            pass
        else:
            if store_provenance in provenance:
                self.authoritative = True

        self.pub = Protocol.Publish.client(hostname, pub)
        self.req = Protocol.Request.client(hostname, req)

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


    def get(self, refresh=False):
        """ Retrieve the current value. Set *refresh* to True to prompt
            the daemon handling the request to provide the most up-to-date
            value available, potentially bypassing any local cache.
        """

        if refresh == False and self.subscribed == True and self.value is not None:
            return self.value

        request = dict()

        if refresh == True:
            request['refresh'] = True

        message = Protocol.Message.Request('GET', self.full_key, request)
        self.req.send(message)
        response = message.wait(self.timeout)

        if response == None:
            raise RuntimeError('GET failed: no response to request')

        try:
            error = response.payload['error']
        except KeyError:
            pass
        else:
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
        return self.value


    def poll(self, period):
        """ Poll for a new value every *period* seconds. Polling will be
            discontinued if *period* is set to None or zero. The actual
            acquisition of a new value is accomplished via the :func:`req_poll`
            method, which in turn leans heavily on :func:`req_refresh` to do
            the actual work.
        """

        Poll.start(self.req_poll, period)


    def publish(self, new_value, bulk=None, timestamp=None, repeat=False):
        """ Publish a new value, which is expected to be a dictionary minimally
            containing 'asc' and 'bin' keys rerepsenting different views of the
            new value; bulk values are not represented as a dictionary, they are
            passed in directly as the *bulk* argument, and the *new_value*
            argument will be ignored. If *timestamp* is set it is expected to be
            a UNIX epoch timestamp; the current time will be used if it is not
            set. Any published values are always cached locally for future
            requests.
        """

        if timestamp is None:
            timestamp = time.time()
        else:
            timestamp = float(timestamp)

        payload = dict()
        payload['time'] = timestamp
        payload['data'] = new_value

        changed = False

        if bulk is None:
            payload['data'] = new_value
            if self._daemon_value != new_value['bin']:
                self._daemon_value = new_value['bin']
                self._daemon_value_timestamp = time.time()
                changed = True
        else:
            bytes = bulk.tobytes()
            description = dict()
            description['shape'] = bulk.shape
            description['dtype'] = str(bulk.dtype)
            payload['data'] = description

            new_value = bulk

            ### This check could be expensive for large arrays.

            if self._daemon_value is None:
                match = False
            else:
                match = (self._daemon_value & new_value).all()

            if match == False:
                self._daemon_value = new_value
                self._daemon_value_timestamp = time.time()
                changed = True

        message = Protocol.Message.Message(None, 'PUB', self.full_key, payload, bulk)

        # The local call to manipulate the _update_queue is presently commented
        # out because the daemon-aware handling in subscribe() is not enabled.
        # This could be enabled if allowing client-facing updates to occur via
        # the usual PUB/SUB machinery is too expensive.

        if changed == True or repeat == True:
            ### self._update_queue.put(message)
            self.store.pub.publish(message)


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

        reference = WeakRef.ref(method)
        self.callbacks.append(reference)

        if self.subscribed == False:
            self.subscribe()


    def req_get(self, request):
        """ Handle a GET request. A typical subclass should not need to
            re-implement this method, implementing :func:`req_refresh`
            would normally be sufficient. The *request* argument is a
            class:`Protocol.Message.Request` instance, parsed from the
            on-the-wire request. The value returned from :func:`req_get`
            is identical to the value returned by :func:`req_refresh`.

            ### req_get should put the response in as request.response.
        """

        try:
            refresh = request.payload['refresh']
        except (TypeError, KeyError):
            refresh = False

        if refresh == True:
            payload = self.req_poll()
        else:
            try:
                self._daemon_value.tobytes
            except AttributeError:
                payload = dict()
                ### This translation to a string representation needs to be
                ### generalized to allow more meaningful behavior.
                payload['asc'] = str(self._daemon_value)
                payload['bin'] = self._daemon_value
                payload['time'] = self._daemon_value_timestamp
            else:
                payload = self._daemon_value

        try:
            bytes = payload.tobytes()
        except AttributeError:
            pass
        else:
            bulk = payload
            payload = dict()
            payload['shape'] = bulk.shape
            payload['dtype'] = str(bulk.dtype)
            payload['bulk'] = bytes

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

        # Perhaps there is a more declarative way to know whether a given
        # payload is expected to be bulk data; perhaps reference the per-Item
        # configuration? Or does an attribute need to be set to make the
        # expected behavior explicit?

        # The default behavior is to only publish a value if the value has
        # changed.

        try:
            payload.tobytes
        except AttributeError:
            self.publish(payload, repeat=repeat)
        else:
            self.publish(None, bulk=payload, repeat=repeat)

        return payload


    def req_refresh(self):
        """ Acquire the most up-to-date value available for this :class:`Item`
            and return it to the caller. The return value is a dictionary,
            nominally with 'asc' and 'bin' keys, representing a human-readable
            format ('asc') format, and a Python binary representation of the
            same value. For example, ``{'asc': 'On', 'bin': True}``.

            Bulk values are returned solely as a numpy array. Other return
            values are in theory possible, as long as the request and publish
            handling code are prepared to accept them.
        """

        # This implementation is strictly caching, there is nothing to refresh.

        payload = dict()
        ### This translation to a string representation needs to be
        ### generalized to allow more meaningful behavior.
        payload['asc'] = str(self._daemon_value)
        payload['bin'] = self._daemon_value
        payload['time'] = self._daemon_value_timestamp

        return payload


    def req_set(self, request):
        """ Handle a client-initiated SET request. Any calls to :func:`req_set`
            are expected to block until completion of the request; no return
            value of significance is expected, though one can be provided (in
            dictionary form, with the response in the 'data' field) if desired.
            Any errors should be indicated by raising an exception.

            The *request* is a :class:`Protocol.Message.Request` instance.
            ### req_set should put the response in as request.response.
        """

        try:
            request.payload['bulk']
        except KeyError:
            bulk = False
            new_value = request.payload['data']
        else:
            bulk = True
            new_value = self._interpret_bulk(request)

        new_value = self.validate(new_value)
        publish = dict()

        if bulk == True:
            publish['data'] = request['data']
            publish['bulk'] = request['bulk']
        else:
            ### This translation to a string representation needs to be
            ### generalized to allow more meaningful behavior.
            publish['asc'] = str(new_value)
            publish['bin'] = new_value

        self.publish(publish)

        # If req_set() returns a payload it will be returned to the caller;
        # absent any explicit response (not required, nor expected), a default
        # response will be provided.


    def set(self, new_value, wait=True, bulk=None):
        """ Set a new value. Set *wait* to True to block until the request
            completes; this is the default behavior. If *wait* is set to False,
            the caller will be returned a :class:`mktl.Protocol.Request.Pending`
            instance, which has a :func:`mktl.Protocol.Request.Pending.wait`
            method that can optionally be invoked block until completion of the
            request; the wait will return immediately once the request is
            satisfied. There is no return value for a blocking request; failed
            requests will raise exceptions.

            If *bulk* is set to anything it should be an as-bytes representation
            of the new value; the *new_value* component should be a dictionary
            providing whatever metadata is required to appropriately handle
            the as-bytes representation; for example, if a numpy array is being
            transmitted, the *new_value* dictionary will need to include the
            dimensions of the array as well as its data type; in that specific
            case, the expected keys in the dictionary are the 'shape' of the
            numpy array, and the string representation of the dtype attribute.
        """

        request = dict()
        request['data'] = new_value

        if bulk is None:
            bulk = b''

        message = Protocol.Message.Request('SET', self.full_key, request, bulk)
        self.req.send(message)

        if wait == False:
            return message

        response = message.wait(self.timeout)

        if response is None:
            raise RuntimeError("SET of %s failed: no response to request" % (self.key))

        try:
            error = response.payload['error']
        except KeyError:
            pass
        else:
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
        # up the Protocol.Publish.Client from moving on to the next broadcast.
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
        # don't keep a local reference.

        self._update_queue = queue.SimpleQueue()
        self._update_queue_put = self._update_queue.put
        self._update_thread = _Updater(self._update, self._update_queue)

        ### This subscription against self.pub could be omitted if the
        ### Item is in a Daemon context. See the publish() method for the extra
        ### call to the _update_queue that needs to be enabled to bypass that
        ### machinery.

        self.pub.register(self._update_queue_put, self.full_key)
        self.subscribed = True

        if prime == True:
            self.get(refresh=True)

        ### If this Item is a leaf of a structured Item we may need to register
        ### a callback on a topic substring of our key name.


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


    def _interpret_bulk(self, message):
        """ Interpret a new bulk value, returning the new rich data construct
            for further handling by methods like :func:`_update`. The default
            handling here treats the bulk message as if it is an N-dimensional
            numpy array; breaking out the interpretation allows future handlers
            to change this behavior for different types of bulk data.
        """

        if numpy is None:
            raise ImportError('numpy module not available')

        description = message.payload['data']
        bulk = message.bulk

        shape = description['shape']
        dtype = description['dtype']
        dtype = getattr(numpy, dtype)

        serialized = numpy.frombuffer(bulk, dtype=dtype)
        reshaped = numpy.reshape(serialized, newshape=shape)

        return reshaped


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


    def _update(self, message):
        """ The caller received a new data segment either from a directed
            GET request or from a PUB subscription.
        """

        if message.bulk is not None:
            payload = self._interpret_bulk(message)
        else:
            try:
                payload = message.payload['data']
            except KeyError:
                payload = None

        try:
            timestamp = message.payload['time']
        except KeyError:
            ### Catching this error may not be desirable-- if it's part of
            ### the wire protocol, the payload should always have a timestamp
            ### associated with it.
            timestamp = time.time()

        self.value = payload
        self.value_timestamp = timestamp
        self._propagate(payload, timestamp)


    def __bool__(self):
        if self.value is None:
            return False

        try:
            current = self.value['bin']
        except:
            # Something other than an asc/bin dictionary. Not sure what it is,
            # but it's _something_, so...
            return True

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


    # __hash__() is not defined, because it would be tied to the key, and would
    # clash with the use of __eq__() defined above, which is not tied to the
    # key. This was a point of some confusion for comparison operations in
    # KTL Python, and the inability to use Item instances as keys in a
    # dictionary seems like a lesser price to pay.


    def __str__(self):
        if self.value is None:
            return ''

        return str(self.value['asc'])


    def __lt__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current < other

    def __le__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current <= other

    def __eq__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current == other

    def __ne__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current != other

    def __gt__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current > other

    def __ge__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current >= other

    def __add__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current + other

    def __radd__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other + current

    def __sub__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current - other

    def __rsub__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other - current

    def __mul__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current * other

    def __rmul__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other * current

    def __div__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current / other

    def __rdiv__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other / current

    def __truediv__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        current = float(current)
        return current / other

    def __rtruediv__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        current = float(current)
        return other / current

    def __mod__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current % other

    def __rmod__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other % current

    def __floordiv__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current // other

    def __rfloordiv__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other // current

    def __divmod__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return (current // other, self % other)

    def __rdivmod__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return (other // current, other % self)

    def __pow__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current ** other

    def __rpow__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other ** current

    def __neg__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return -current

    def __pos__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return +current

    def __abs__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return abs(current)

    def __invert__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return ~current

    def __and__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current & other

    def __rand__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other & current

    def __or__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current | other

    def __ror__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other | current

    def __xor__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return current ^ other

    def __rxor__(self, other):
        if self.value is None:
            current = None
        else:
            current = self.value['bin']
        return other ^ current


    def __inplace(self, method, value):

        if self.subscribed == False:
            self.subscribe()

        modified = method(value)
        self.set(modified)

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
