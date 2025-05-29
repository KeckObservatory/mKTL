
import queue
import traceback

try:
    import numpy
except ImportError:
    numpy = None

from . import Updater
from .. import Config
from .. import Protocol
from .. import WeakRef


class Item:
    """ An Item represents a key/value pair, where the key is the name of the
        Item, and the value is whatever is provided by the daemon, according to
        :func:`get` and :func:`subscribe` requests. A :func:`set` request does
        not update the local value, it only issues a request to the remote
        daemon; it is the daemon's responsibility to issue a post-set update
        with any new value(s).
    """

    untruths = set((None, False, 0, 'false', 'f', 'no', 'n', 'off', 'disable', ''))

    def __init__(self, store, key):

        self.key = key
        self.full_key = store.name + '.' + key
        self.store = store
        self.config = store.config[key]

        self.callbacks = list()
        self.cached = None
        self.req = None
        self.subscribed = False
        self.timeout = 120
        self._update_queue = None
        self._update_queue_put = None
        self._update_thread = None

        key_config = store.config[key]
        provenance = key_config['provenance']

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


    def get(self, refresh=False):
        """ Retrieve the current value. Set *refresh* to True to prompt
            the daemon handling the request to provide the most up-to-date
            value available, potentially bypassing any local cache.
        """

        if refresh == False and self.subscribed == True:
            return self.cached

        request = dict()
        request['request'] = 'GET'
        request['name'] = self.full_key

        if refresh == True:
            request['refresh'] = True

        pending = self.req.send(request)
        response = pending.wait(self.timeout)

        try:
            error = response['error']
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
        return self.cached


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


    def set(self, new_value, wait=True, bulk=None):
        """ Set a new value. Set *wait* to True to block until the request
            completes; this is the default behavior. If *wait* is set to False,
            the caller will be returned a :class:`Protocol.Request.Pending`
            instance, which has a :func:`Protocol.Request.Pending.wait` method
            that can optionally be invoked block until completion of the
            request; the wait will return immediately once the request is
            satisfied. There is no return value for a blocking request; failed
            requests will raise exceptions.

            If *bulk* is set to anything it should be an as-bytes representation
            of the new value; the *new_value* component should be a dictionary
            providing whatever metadata is required to appropriately handle
            the as-bytes representation; for example, if a numpy array is being
            transmitted, the *new_value* dictionary will need to include the
            dimensions of the array as well as its data type.
        """

        request = dict()
        request['request'] = 'SET'
        request['name'] = self.full_key
        request['data'] = new_value

        if bulk is not None:
            request['bulk'] = bulk

        pending = self.req.send(request)

        if wait == False:
            return pending

        response = pending.wait(self.timeout)

        try:
            error = response['error']
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

        config = self.store.config[self.key]

        try:
            type = config['type']
        except KeyError:
            bulk = False
        else:
            if type == 'bulk':
                bulk = True
            else:
                bulk = False

        # A local thread is used to execute callbacks to ensure we don't tie
        # up the Protocol.Publish.Client from moving on to the next broadcast.
        # This does mean there's an extra background thread for every Item
        # that receives callbacks; on older systems we are limited to 4,000
        # such threads before running into resource limitations, modern systems
        # allow 32,000 or more, sometimes depending on the amount of physical
        # memory in the system.

        # A thread pool might be just as performant for this purpose, but the
        # control flow in that thread would be a lot more complex. Having a
        # dedicated Updater background thread for each Item with an active
        # subscription makes the processing straightforward.

        # The reference to SimpleQueue.put() gets deallocated immediately if we
        # don't keep a local reference.

        self._update_queue = queue.SimpleQueue()
        self._update_queue_put = self._update_queue.put
        self._update_thread = Updater.Updater(self._update, self._update_queue)

        if bulk == True:
            self.pub.subscribe('bulk:' + self.full_key)

        self.pub.register(self._update_queue_put, self.full_key)
        self.subscribed = True

        if prime == True:
            self.get(refresh=True)

        ### If this Item is a leaf of a structured Item we may need to register
        ### a callback on a topic substring of our key name.


    def _interpret_bulk(self, new_message):
        """ Interpret a new bulk value, returning the new rich data construct
            for further handling by methods like :func:`_update`. The default
            handling here treats the bulk message as if it is an N-dimensional
            numpy array; breaking out the interpretation allows future handlers
            to change this behavior for different types of bulk data.
        """

        if numpy is None:
            raise ImportError('numpy module not available')

        description = new_message['data']
        bulk = new_message['bulk']

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


    def _update(self, new_message):
        """ The caller received a new data segment either from a directed
            GET request or from a PUB subscription.
        """

        try:
            new_data = new_message['data']
        except KeyError:
            return

        try:
            new_message['bulk']
        except KeyError:
            pass
        else:
            new_data = self._interpret_bulk(new_message)

        new_timestamp = new_message['time']

        self.cached = new_data
        self.cached_timestamp = new_timestamp
        self._propagate(new_data, new_timestamp)


    def __bool__(self):
        if self.cached is None:
            return False

        try:
            current = self.cached['bin']
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
            bytes = self.cached.tobytes()
        except AttributeError:
            bytes = bytes(str(self))

        return bytes


    # __hash__() is not defined, because it would be tied to the key, and would
    # clash with the use of __eq__() defined above, which is not tied to the
    # key. This was a point of some confusion for comparison operations in
    # KTL Python, and the inability to use Item instances as keys in a
    # dictionary seems like a lesser price to pay.


    def __str__(self):
        if self.cached is None:
            return ''

        return str(self.cached['asc'])


    def __lt__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current < other

    def __le__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current <= other

    def __eq__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current == other

    def __ne__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current != other

    def __gt__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current > other

    def __ge__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current >= other

    def __add__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current + other

    def __radd__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other + current

    def __sub__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current - other

    def __rsub__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other - current

    def __mul__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current * other

    def __rmul__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other * current

    def __div__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current / other

    def __rdiv__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other / current

    def __truediv__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        current = float(current)
        return current / other

    def __rtruediv__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        current = float(current)
        return other / current

    def __mod__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current % other

    def __rmod__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other % current

    def __floordiv__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current // other

    def __rfloordiv__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other // current

    def __divmod__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return (current // other, self % other)

    def __rdivmod__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return (other // current, other % self)

    def __pow__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current ** other

    def __rpow__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other ** current

    def __neg__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return -current

    def __pos__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return +current

    def __abs__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return abs(current)

    def __invert__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return ~current

    def __and__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current & other

    def __rand__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other & current

    def __or__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current | other

    def __ror__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return other | current

    def __xor__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
        return current ^ other

    def __rxor__(self, other):
        if self.cached is None:
            current = None
        else:
            current = self.cached['bin']
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


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
