
import traceback

from .Protocol import Publish
from .Protocol import Request
from . import WeakRef


class Item:

    def __init__(self, name, config):

        self.name = name
        self.config = config

        self.callbacks = list()
        self.cached = None
        self.req = None
        self.subscribed = False
        self.timeout = 120

        ## Determine the location we need to connect to from the config
        self.pub = Publish.client()
        self.req = Request.client()


    def get(self, refresh=False):
        ''' Retrieve the current value. Set *refresh* to True to prompt
            the daemon handling the request to provide the most up-to-date
            value available, potentially bypassing any local cache.
        '''

        if refresh == False and self.subscribed == True:
            return self.cached

        request = dict()
        request['request'] = 'GET'
        request['name'] = self.name

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

                ### The exception type here should be something unique.
                raise RuntimeError("GET failed: %s: %s" % (e_type, e_text))


        self._update(response)
        return self.cached


    def register(self, method):
        ''' Register a callback to be invoked whenever a new value is received,
            either by a direct :func:`get` request or the arrival of an
            asynchronous broadcast.
        '''

        if callable(method):
            pass
        else:
            raise TypeError('the registered method must be callable')

        reference = WeakRef.ref(method)
        self.callbacks.append(reference)

        if self.subscribed == False:
            self.subscribe()


    def set(self, new_value, wait=True):
        ''' Set a new value. Set *wait* to True to block until the request
            completes; this is the default behavior. If *wait* is set to
            False, the caller will be returned a :class:`PendingRequest`
            instance, which has a :func:`PendingRequest.wait` method that
            can (optionally) be invoked block until completion of the
            request; the wait will return immediately if the request is
            already satisfied.
        '''

        request = dict()
        request['request'] = 'SET'
        request['name'] = self.name
        request['data'] = new_value

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

                ### The exception type here should be something unique.
                raise RuntimeError("SET failed: %s: %s" % (e_type, e_text))


    def subscribe(self):
        ''' Subscribe to all future broadcast events. Doing so ensures that
            locally cached values will always be current, regardless of whether
            :func:`get` has been invoked recently.
        '''

        if self.subscribed == True:
            return

        ### If this Item has a bulk component this also needs to subscribe
        ### to the bulk topic

        ### If this Item is a leaf of a structured Item we may need to register
        ### a callback on a topic substring of our name.

        self.pub.register(self._update, self.name)
        self.subscribed = True


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

        ### How does this handle bulk data?

        try:
            new_data = new_message['data']
        except KeyError:
            return

        new_timestamp = new_message['time']

        self.cached = new_data
        self.cached_timestamp = new_timestamp
        self._propagate(new_data, new_timestamp)


# end of class Item


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent: