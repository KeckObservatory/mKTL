
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
        self.subscribe(prime=False)


    def poll(self, period):
        """ Poll for a new value every *period* seconds. Polling will be
            discontinued if *period* is set to None or zero.
        """

        Poll.start(self.req_refresh, period)


    def publish(self, new_value, timestamp=None, cache=False):
        """ Publish a new value.
        """

        if timestamp is None:
            timestamp = time.time()

        message = dict()
        message['message'] = 'PUB'
        message['name'] = self.full_key
        message['time'] = timestamp
        message['data'] = new_value

        if cache == True:
            try:
                self._daemon_cached = new_value['bin']
            except (TypeError, KeyError):
                self._daemon_cached = new_value

        self.store.pub.publish(message)


    def req_get(self, request):
        """ Handle a GET request.
        """

        try:
            refresh = request['refresh']
        except KeyError:
            refresh = False

        if refresh == True:
            self.req_refresh()

        payload = dict()
        payload['asc'] = str(self._daemon_cached)
        payload['bin'] = self._daemon_cached

        return payload


    def req_refresh(self):
        """ Refresh the current value and publish it. This is where a daemon
            would communicate with a controller or other source-of-authority
            to retrieve the current value.
        """

        # This implementation is strictly caching, there is nothing to refresh.

        payload = dict()
        payload['asc'] = str(self._daemon_cached)
        payload['bin'] = self._daemon_cached

        self.publish(payload)


    def req_set(self, request):
        """ Handle a SET request.
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
    """ The daemon version of a `class:Client.Item` is based on the client
        version, implementing additional methods that are relevant in a daemon
        context, but with all other client behavior left unchanged.
    """

    def __init__(self, *args, **kwargs):

        Client.Item.__init__(self, *args, **kwargs)
        Daemon.__init__(self, *args, **kwargs)


# end of class Item


### Additional subclasses would go here, if they existed. Numeric types, bulk
### keyword types, etc.


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
