
import time

from . import Poll
from .. import Client



class Daemon:
    """ Additional methods implementing daemon functionality for an Item.
        This supplemental class is intended to be strictly additive to a
        client-side Item class; multiple inheritance is leveraged to allow
        cleaner addition of these methods to not just the base client Item
        class, but potentially any subclasses as well.

        The default behavior of the daemon-specific methods is to act as a
        simple key/value cache.
    """

    def __init__(self, *args, **kwargs):
        self._daemon_cached = None
        self.subscribe(prime=False)


    def poll(self, period):
        """ Poll for a new value every *period* seconds. Polling will be
            discontinued if *period* is set to None or zero. Requesting a
            new value is accomplished via the :func:`req_refresh` method.
        """

        Poll.start(self.req_refresh, period)


    def publish(self, new_value, bulk=None, timestamp=None, cache=False):
        """ Publish a new value, which is expected to be a dictionary minimally
            containing 'asc' and 'bin' keys rerepsenting different views of the
            new value; bulk values are not represented as a dictionary, they are
            passed in directly as the *bulk* argument, and the *new_value*
            argument will be ignored. If *timestamp* is set it is expected to be
            a UNIX epoch timestamp; the current time will be used if it is not
            set. If *cache* is set to True the published value will be cached
            locally for any future requests.
        """

        if timestamp is None:
            timestamp = time.time()
        else:
            timestamp = float(timestamp)

        message = dict()
        message['message'] = 'PUB'
        message['name'] = self.full_key
        message['time'] = timestamp

        if bulk is None:
            message['data'] = new_value
        else:
            bytes = bulk.tobytes()
            description = dict()
            description['shape'] = bulk.shape
            description['dtype'] = str(bulk.dtype)
            message['data'] = description
            message['bulk'] = bytes

            new_value = bulk

        if cache == True:
            try:
                self._daemon_cached = new_value['bin']
            except (TypeError, KeyError, IndexError):
                self._daemon_cached = new_value

        self.store.pub.publish(message)


    def req_get(self, request):
        """ Handle a GET request. A typical subclass should not need to
            re-implement this method, implementing :func:`req_refresh`
            would normally be sufficient.
        """

        try:
            refresh = request['refresh']
        except KeyError:
            refresh = False

        if refresh == True:
            self.req_refresh()

        ### This needs to properly handle bulk data types.

        payload = dict()
        payload['asc'] = str(self._daemon_cached)
        payload['bin'] = self._daemon_cached

        return payload


    def req_refresh(self):
        """ Refresh the current value and publish it. This is the entry point
            for any calls made via the :func:`poll` machinery, or for any GET
            requests explicitly requesting a refresh of the current value.
            Subclasses do not need to call this parent method, they can call
            :func:`publish` directly with or without the *cache* argument set
            to True.
        """

        # This implementation is strictly caching, there is nothing to refresh.

        payload = dict()
        payload['asc'] = str(self._daemon_cached)
        payload['bin'] = self._daemon_cached

        self.publish(payload)


    def req_set(self, request):
        """ Handle a client-initiated SET request. Any calls to :func:`req_set`
            are expected to block until completion of the request.
        """

        try:
            request['bulk']
        except KeyError:
            bulk = False
            new_value = request['data']
        else:
            bulk = True
            new_value = self._interpret_bulk(request)

        new_value = self.validate(new_value)
        self._daemon_cached = new_value

        publish = dict()

        if bulk == True:
            publish['data'] = request['data']
            publish['bulk'] = request['bulk']
        else:
            publish['asc'] = str(new_value)
            publish['bin'] = new_value

        self.publish(publish)

        # Returning True here acknowledges that the request is complete.

        payload = dict()
        payload['data'] = True
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


# end of class Daemon



class Item(Client.Item, Daemon):
    """ This daemon-specific subclass of a :class:`mKTL.Client.Item` implements
        additional methods that are relevant in a daemon context, but with all
        client behavior left unchanged. For example, if a callback is registered
        with this :class:`Item` instance, it is handled precisely the same way
        as if this were a regular :class:`mKTL.Client.Item` instance.
    """

    def __init__(self, *args, **kwargs):

        Client.Item.__init__(self, *args, **kwargs)
        Daemon.__init__(self, *args, **kwargs)


# end of class Item


### Additional subclasses would go here, if they existed. Numeric types, bulk
### keyword types, etc.


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
