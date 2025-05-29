
import queue
import time

from . import Poll
from .. import Client


class Daemon:
    """ Additional methods implementing daemon functionality for an Item.
        This supplemental class is intended to be strictly additive to a
        client-side Item class; multiple inheritance is leveraged to allow
        cleaner addition of these methods to not just the base client Item
        class, but potentially any subclasses as well-- for example, a
        Daemon.Item.Numeric class may benefit from subclassing both this
        Daemon class as well as Client.Item.Numeric, whereas if Daemon.Item
        were a simple subclass of Client.Item it would be more challenging
        to include the additional behavior.
    """

    def __init__(self, *args, **kwargs):
        self._daemon_cached = None
        self.subscribe()


    def poll(self, period):
        """ Poll for a new value every *period* seconds. Polling will be
            discontinued if *period* is set to None or zero. The actual
            acquisition of a new value is accomplished via the :func:`req_poll`
            method, which in turn leans heavily on :func:`req_refresh` to do
            the actual work.
        """

        Poll.start(self.req_poll, period)


    def publish(self, new_value, bulk=None, timestamp=None):
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

        message = dict()
        message['message'] = 'PUB'
        message['name'] = self.full_key
        message['time'] = timestamp

        if bulk is None:
            message['data'] = new_value
            self._daemon_cached = new_value['bin']
        else:
            bytes = bulk.tobytes()
            description = dict()
            description['shape'] = bulk.shape
            description['dtype'] = str(bulk.dtype)
            message['data'] = description
            message['bulk'] = bytes

            new_value = bulk
            self._daemon_cached = new_value

        # The internal update needs a separate copy of the message dictionary,
        # as its contents relating to bulk messages are manipulated as part of
        # putting the message out "on the wire". A deep copy is not necessary.

        self._update_queue.put(dict(message))
        self.store.pub.publish(message)


    def subscribe(self, *args, **kwargs):
        ''' This is a stripped-down version of the :func:`Client.Item.subscribe`
            method, as part of allowing a :class:`Item` to avoid the overhead of
            the full publish/subscribe machinery for updates that are strictly
            internal; this is primarily motivated by efficiency, where for bulk
            data transmission the additional overhead reduces the overall
            throughput (in terms of broadcasts per second) by roughly 30%.

            The daemon variant of an Item is always subscribed to itself; the
            :func:`publish` method bypasses the normal publish/subscribe
            handling by directly manipulating the :class:`queue.SimpleQueue`
            established here.
        '''

        if self.subscribed == True:
            return

        self._update_queue = queue.SimpleQueue()
        self._update_thread = Client.Updater.Updater(self._update, self._update_queue)
        self.subscribed = True


    def req_get(self, request):
        """ Handle a GET request. A typical subclass should not need to
            re-implement this method, implementing :func:`req_refresh`
            would normally be sufficient. The *request* argument is a
            Python dictionary, parsed from the inbound JSON-formatted
            request. The value returned from :func:`req_get` is identical
            to the value returned by :func:`req_refresh`.
        """

        try:
            refresh = request['refresh']
        except KeyError:
            refresh = False

        if refresh == True:
            payload = self.req_poll()
        else:
            try:
                self._daemon_cached.tobytes
            except AttributeError:
                payload = dict()
                ### This translation to a string representation needs to be
                ### generalized to allow more meaningful behavior.
                payload['asc'] = str(self._daemon_cached)
                payload['bin'] = self._daemon_cached
            else:
                payload = self._daemon_cached

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


    def req_poll(self):
        """ Entry point for calls originating from :func:`poll`. The only reason
            this method exists is to streamline the expected behavior of
            :func:`req_refresh`; a typical subclass would not need to
            reimplement this method. The value returned from :func:`req_poll`
            is identical to the value returned by :func:`req_refresh`.
        """

        payload = self.req_refresh()

        # Perhaps there is a more declarative way to know whether a given
        # payload is expected to be bulk data; perhaps reference the per-Item
        # configuration? Or does an attribute need to be set to make the
        # expected behavior explicit?

        try:
            payload.tobytes
        except AttributeError:
            self.publish(payload)
        else:
            self.publish(None, bulk=payload)

        return payload


    def req_refresh(self):
        """ Acquire the most up-to-date value available for this :class:`Item`
            and return it to the caller. The return value is a dictionary,
            nominally with 'asc' and 'bin' keys, representing a human-readable
            format ('asc') format, and a Python binary representation of the
            same value. For example, {'asc': 'On', 'bin': True}.

            Bulk values are returned solely as a numpy array. Other return
            values are in theory possible, as long as the request and publish
            handling code are prepared to accept them.
        """

        # This implementation is strictly caching, there is nothing to refresh.

        payload = dict()
        ### This translation to a string representation needs to be
        ### generalized to allow more meaningful behavior.
        payload['asc'] = str(self._daemon_cached)
        payload['bin'] = self._daemon_cached

        return payload


    def req_set(self, request):
        """ Handle a client-initiated SET request. Any calls to :func:`req_set`
            are expected to block until completion of the request; upon
            completion a simple dictionary should be returned to acknowledge
            that the request is complete: ``{'data': True}``.
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



# For the final Item class, the Daemon class is inheritedfirst because we want
# it to override some behavior of the Client.Item class. Subclasses should be
# careful to continue this pattern; the initialization, however, invokes the
# Client.Item code first, and then the Daemon code; this is likewise deliberate,
# so that the Daemon initialization can override steps taken during the
# Client.Item intialization.


class Item(Daemon, Client.Item):
    """ This daemon-specific subclass of a :class:`Client.Item` implements
        additional methods that are relevant in a daemon context, but with all
        client behavior left unchanged. For example, if a callback is registered
        with this :class:`Item` instance, it is handled precisely the same way
        as if this were a regular :class:`Client.Item` instance.
    """

    def __init__(self, *args, **kwargs):

        Client.Item.__init__(self, *args, **kwargs)
        Daemon.__init__(self, *args, **kwargs)


# end of class Item


### Additional subclasses would go here, if they existed. Numeric types, bulk
### keyword types, etc.


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
