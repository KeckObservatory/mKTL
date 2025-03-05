
from .. import Client
from .. import Config
from .. import Protocol

from . import Item
from . import Port


class Store(Client.Store):
    ''' The daemon version of a Store is based on the client version; the
        behavior defaults to the client approach, but for items specified in
        the daemon *config* file a daemon-specific variant of the item will
        be loaded that supplements the client behavior with daemon-specific
        functionality.

        The developer is expected to subclass this :class:`Store` class and
        implement a :func:`setup` method. :func:`setup`* will be called near
        the end of the initialization process, once most of the local
        infrastructure has been established, but before all of the local Items
        have been instantiated. :func:`setup` is a hook allowing the subclass
        to instantiate custom Item classes, and make any other custom supporting
        calls as part of the initialization.
    '''

    def __init__(self, name, config):

        self.name = name
        self.config = None
        self._items = dict()
        self.daemon_config = None
        self.daemon_uuid = None
        self._daemon_items = set()

        daemon_config = Config.load(name, config)
        self._update_daemon_config(daemon_config)

        # Use cached port numbers when possible.

        req, pub = Port.load(self.name, self.daemon_uuid)

        self.pub = Protocol.Publish.Server(pub, avoid=Port.used())
        self.req = RequestServer(self, req, avoid=Port.used())

        Port.save(self.name, self.daemon_uuid, self.req.port, self.pub.port)

        provenance = dict()
        provenance['stratum'] = 0
        provenance['hostname'] = self.req.hostname
        provenance['req'] = self.req.port
        provenance['pub'] = self.pub.port

        self.provenance = list()
        self.provenance.append(provenance)

        # A bit of a chicken and egg problem with the provenance. It can't be
        # established until the listener ports are known; we can't establish
        # the listener ports without knowing our UUID; we don't know the UUID
        # until the configuration is loaded. We're doctoring the configuration
        # after-the-fact, and thus need to refresh the local cache to ensure
        # consistency.

        self.daemon_config[self.daemon_uuid]['provenance'] = self.provenance
        Config.add(self.name, self.daemon_config)

        config = Config.Items.get(name)
        self._update_config(config)

        # Local machinery is intact. Invoke the setup() method, which is the
        # hook for the developer to establish their own custom Item classes
        # before filling in with empty caching Item classes.

        self.setup()
        self.setupRemaining()

        ### This is where loading values from a cache should occur.

        # Ready to go on the air.

        discovery = Protocol.Discover.DirectServer(self.req.port)

        guides = Protocol.Discover.search(wait=True)
        self.publish_config(guides)


    def _update_config(self, config):

        self.config = config

        keys = config.keys()
        keys = list(keys)
        keys.sort()

        for key in keys:
            try:
                self._items[key]
            except KeyError:
                self._items[key] = None


    def _update_daemon_config(self, config):

        uuid = list(config.keys())[0]
        self.daemon_config = config
        self.daemon_uuid = uuid
        Config.add(self.name, config)

        config = Config.Items.get(self.name)
        self._daemon_items.update(config)
        self._update_config(config)


    def publish_config(self, targets=tuple()):
        ''' Put our local configuration out on the wire.
        '''

        config = dict(self.daemon_config)

        request = dict()
        request['request'] = 'CONFIG'
        request['name'] = self.name
        request['data'] = config

        for address,port in targets:
            try:
                Protocol.Request.send(request, address, port)
            except zmq.error.ZMQError:
                pass


    def setup(self):
        ''' Subclasses should override the :func:`setup` method to instantiate
            any local Item classes or otherwise execute custom code that needs
            to occur as part of establishing this Store instance.
        '''

        raise NotImplementedError('subclass must define a setup() method')


    def setupRemaining(self):
        ''' Provision any unset local Item instances with caching
            implementations.
        '''

        local = list(self._daemon_items)

        for key in local:
            item = self._items[key]

            if item is None:
                item = Item.Item(self, key)
                self._items[key] = item


# end of class Store



class RequestServer(Protocol.Request.Server):

    def __init__(self, store, *args, **kwargs):
        Protocol.Request.Server.__init__(self, *args, **kwargs)
        self.store = store


    def req_config(self, request):

        store = request['name']

        if store == self.store.name:
            config = dict(self.store.daemon_config)
        else:
            config = Config.get(store)

        return config


    def req_handler(self, socket, lock, ident, request):
        ''' Inspect the incoming request type and decide how a response
            will be generated.
        '''

        self.req_ack(socket, lock, ident, request)

        try:
            type = request['request']
        except KeyError:
            raise KeyError("invalid request JSON, 'request' not set")

        try:
            name = request['name']
        except KeyError:
            if type != 'HASH':
                raise KeyError("invalid request JSON, 'name' not set")

        if type == 'HASH':
            payload = self.req_hash(request)
        elif type == 'SET':
            payload = self.req_set(request)
        elif type == 'GET':
            payload = self.req_get(request)
        elif type == 'CONFIG':
            payload = self.req_config(request)
        else:
            raise ValueError('unhandled request type: ' + type)

        return payload


    def req_get(self, request):

        key = request['name']
        store, key = key.split('.', 1)

        if key in self.store._daemon_items:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        payload = self.store[key].req_get(request)
        return payload


    def req_set(self, request):

        key = request['name']
        store, key = key.split('.', 1)

        if key in self.store._daemon_items:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        payload = self.store[key].req_set(request)
        return payload


    def req_hash(self, request):

        try:
            store = request['name']
        except KeyError:
            store = None

        cached = Config.Hash.get(store)
        return cached


# end of class RequestServer


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
