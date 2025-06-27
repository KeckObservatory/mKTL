
import os
import subprocess
import sys
import zmq

from .. import Config
from .. import item
from .. import Protocol
from .. import store

from . import Persist
from . import Port


class Store(store.Store):
    """ The daemon version of a Store is based on the client version; the
        behavior defaults to the client approach, but for items specified in
        the daemon *config* file a daemon-specific variant of the item will
        be loaded that supplements the client behavior with daemon-specific
        functionality.

        The developer is expected to subclass :class:`Store` class and
        implement a :func:`setup` method, and/or a :func:`setup_final`
        method.

        The *store* argument is the name of this store; *config* is the base
        name of the mKTL configuration file that defines the items in this
        store. *arguments* is expected to be an :class:`argparse.ArgumentParser`
        instance, though in practice it can be any Python object with specific
        named attributes of interest to a :class:`Store` subclass; it is not
        required. This is intended to be a vehicle for subclasses to receive
        key information from command-line arguments, such as the location of
        an auxiliary configuration file containing information about a hardware
        controller.
    """

    def __init__(self, name, config, arguments=None):

        self.name = name
        self.config = None
        self._items = dict()
        self.daemon_config = None
        self.daemon_uuid = None
        self._daemon_keys = set()

        daemon_config = Config.load(name, config)
        self._update_daemon_config(daemon_config)

        # Use cached port numbers when possible. The ZMQError is thrown
        # when the requested port is not available; let a new one be
        # auto-assigned when that happens.

        req, pub = Port.load(self.name, self.daemon_uuid)

        try:
            self.pub = Protocol.Publish.Server(port=pub, avoid=Port.used())
        except zmq.error.ZMQError:
            self.pub = Protocol.Publish.Server(port=None, avoid=Port.used())

        try:
            self.req = RequestServer(self, port=req, avoid=Port.used())
        except zmq.error.ZMQError:
            self.req = RequestServer(self, port=None, avoid=Port.used())

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
        self._setup_missing()

        # Restore any persistent values, and enable the retention of future
        # persistent values. If there are no persistent items present in this
        # store the call to _restore() is a no-op, and the persistence
        # subprocess will exit.

        self._restore()
        self._begin_persistence()

        # The promise is that setup_final() gets invoked after everything else
        # is ready, but before we go on the air.

        self.setup_final()

        # Ready to go on the air.

        discovery = Protocol.Discover.DirectServer(self.req.port)

        guides = Protocol.Discover.search(wait=True)
        self._publish_config(guides)


    def _begin_persistence(self):
        """ Start the background process responsible for updating the
            persistent value cache.
        """

        daemon = sys.argv[0]
        dirname = os.path.dirname(daemon)
        markpersistd = os.path.join(dirname, 'markpersistd')

        arguments = list()
        arguments.append(sys.executable)
        arguments.append(markpersistd)
        arguments.append(self.name)
        arguments.append(self.daemon_uuid)

        pipe = subprocess.PIPE
        self.persistence = subprocess.Popen(arguments)


    def _publish_config(self, targets=tuple()):
        """ Put our local configuration out on the wire.
        """

        config = dict(self.daemon_config)

        payload = dict()
        payload['data'] = config

        for address,port in targets:
            message = Protocol.Message.Request('CONFIG', self.name, payload)
            try:
                Protocol.Request.send(address, port, message)
            except zmq.error.ZMQError:
                pass


    def _restore(self):
        """ Bring back any values in the local persistent cache, and push them
            through to affected Items for handling.
        """

        loaded = Persist.load(self.name, self.daemon_uuid)

        for key in loaded.keys():
            faux_message = loaded[key]
            item = self[key]
            item.req_set(faux_message)


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
        self._daemon_keys.update(config)
        self._update_config(config)


    def setup(self):
        """ Subclasses should override the :func:`setup` method to instantiate
            any custom :class:`mktl.Item` subclasses or otherwise execute custom
            code. When :func:`setup` is called the bulk of the :class:`Store`
            machinery is in place, but cached values have not been loaded, nor
            has the presence of this daemon been announced. The default
            implementation of this method takes no actions.
        """

        pass


    def _setup_missing(self):
        """ Inspect the locally known list of :class:`mktl.Item` instances;
            create default, caching instances for any that were not previously
            populated by the call to :func:`setup`.
        """

        local = list(self._daemon_keys)

        for key in local:
            existing = self._items[key]

            if existing is None:
                item.Item(self, key)


    def setup_final(self):
        """ Subclasses should override the :func:`setup_final` method to
            execute any/all code that should occur after all :class:`mktl.Item`
            instances have been created, including any non-custom
            :class:`mktl.Item` instances, but before this :class:`Store`
            announces its availability on the local network. The default
            implementation of this method takes no actions.
        """

        pass


# end of class Store



class RequestServer(Protocol.Request.Server):

    def __init__(self, store, *args, **kwargs):
        Protocol.Request.Server.__init__(self, *args, **kwargs)
        self.store = store


    def req_config(self, store):

        if store == self.store.name:
            config = dict(self.store.daemon_config)
        else:
            config = Config.get(store)

        return config


    def req_handler(self, socket, lock, ident, request):
        """ Inspect the incoming request type and decide how a response
            will be generated.
        """

        self.req_ack(socket, lock, ident, request)

        type = request.type
        target = request.target

        if target == '' and type != 'HASH' and type != 'CONFIG':
            raise KeyError("invalid %s request, 'target' not set" % (type))

        if type == 'HASH':
            payload = self.req_hash(request)
        elif type == 'SET':
            payload = self.req_set(request)
            if payload is None:
                payload = True
        elif type == 'GET':
            payload = self.req_get(request)
        elif type == 'CONFIG':
            payload = self.req_config(request)
        else:
            raise ValueError('unhandled request type: ' + type)

        return payload


    def req_get(self, request):

        store, key = request.target.split('.', 1)

        if key in self.store._daemon_keys:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        payload = self.store[key].req_get(request)
        return payload


    def req_set(self, request):

        store, key = request.target.split('.', 1)

        if key in self.store._daemon_keys:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        payload = self.store[key].req_set(request)
        return payload


    def req_hash(self, request):

        store = request.target
        if store == '':
            store = None

        cached = Config.Hash.get(store)
        return cached


# end of class RequestServer


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
