
import traceback

try:
    import numpy
except ImportError:
    numpy = None

from .Protocol import Publish
from .Protocol import Request
from . import Config
from . import WeakRef


class Item:
    ''' An Item represents a key/value pair, where the key is the name of the
        Item, and the value is whatever is provided by the daemon, according to
        :func:`get` and :func:`subscribe` requests. A :func:`set` request does
        not update the local value, it only issues a request to the remote
        daemon; it is the daemon's responsibility to issue a post-set update
        with any new value(s).
    '''

    def __init__(self, store, name):

        self.name = name
        self.full_name = store.name + '.' + name
        self.store = store

        self.callbacks = list()
        self.cached = None
        self.req = None
        self.subscribed = False
        self.timeout = 120

        key_config = store.config[name]
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
            raise RuntimeError('cannot find daemon for ' + self.full_name)

        self.pub = Publish.client(hostname, pub)
        self.req = Request.client(hostname, req)


    def get(self, refresh=False):
        ''' Retrieve the current value. Set *refresh* to True to prompt
            the daemon handling the request to provide the most up-to-date
            value available, potentially bypassing any local cache.
        '''

        if refresh == False and self.subscribed == True:
            return self.cached

        request = dict()
        request['request'] = 'GET'
        request['name'] = self.full_name

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
        ''' Register a callback to be invoked whenever a new value is received,
            either by a direct :func:`get` request or the arrival of an
            asynchronous broadcast. :func:`subscribe` will be invoked if
            a subscription has not already occurred.
        '''

        if callable(method):
            pass
        else:
            raise TypeError('the registered method must be callable')

        reference = WeakRef.ref(method)
        self.callbacks.append(reference)

        if self.subscribed == False:
            self.subscribe()


    def set(self, new_value, wait=True, bulk=None):
        ''' Set a new value. Set *wait* to True to block until the request
            completes; this is the default behavior. If *wait* is set to
            False, the caller will be returned a :class:`Request.Pending`
            instance, which has a :func:`Request.Pending.wait` method that
            can (optionally) be invoked block until completion of the
            request; the wait will return immediately if the request is
            already satisfied. There is no return value for a blocking
            request; failed requests will raise exceptions.

            If *bulk* is set to anything it should be an as-bytes representation
            of the new value; the *new_value* component should be a dictionary
            providing whatever metadata is required to appropriately handle
            the as-bytes representation; for example, if a numpy array is being
            transmitted, the *new_value* dictionary will need to include the
            dimensions of the array as well as its data type.
        '''

        request = dict()
        request['request'] = 'SET'
        request['name'] = self.full_name
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
                raise RuntimeError("SET failed: %s: %s" % (e_type, e_text))


    def subscribe(self):
        ''' Subscribe to all future broadcast events. Doing so ensures that
            locally cached values will always be current, regardless of whether
            :func:`get` has been invoked recently.
        '''

        if self.subscribed == True:
            return

        config = self.store.config[self.name]

        try:
            type = config['type']
        except KeyError:
            bulk = False
        else:
            if type == 'bulk':
                bulk = True
            else:
                bulk = False

        if bulk == True:
            self.pub.subscribe('bulk:' + self.full_name)

        self.pub.register(self._update, self.full_name)
        self.subscribed = True

        ### If this Item is a leaf of a structured Item we may need to register
        ### a callback on a topic substring of our name.


    def _interpret_bulk(self, new_message):
        ''' Interpret a new bulk value, returning the new rich data construct
            for further handling by methods like :func:`_update`. The default
            handling here treats the bulk message as if it is an N-dimensional
            numpy array; breaking out the interpretation allows future handlers
            to expand as necessary for subclasses.
        '''

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
        ''' Invoke any registered callbacks upon receipt of a new value.
        '''

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
        ''' The caller received a new data segment either from a directed
            GET request or from a PUB subscription.
        '''

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


# end of class Item


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
