
import os
import subprocess
import sys
import zmq

from . import Config
from . import Get
from . import item
from . import Protocol
from . import store

from . import persist
from . import port


class Daemon:
    """ The mKTL :class:`Daemon` is little more than a facilitator for common
        mKTL actions taken in a daemon context: loading a configuration file,
        instantiating :class:`mktl.Item` instances, and commencing routine
        operations.

        The developer is expected to subclass the :class:`Daemon` class and
        implement a :func:`setup` method, and/or a :func:`setup_final`
        method.

        The *store* argument is the name of this store; *config* is the base
        name of the mKTL configuration file that defines the items in this
        store. *arguments* is expected to be an :class:`argparse.ArgumentParser`
        instance, though in practice it can be any Python object with specific
        named attributes of interest to a :class:`Daemon` subclass; it is not
        required. This is intended to be a vehicle for subclasses to receive
        key information from command-line arguments, such as the location of
        an auxiliary configuration file containing information about a hardware
        controller.
    """

    def __init__(self, store, config, arguments=None):

        self._items = dict()
        self.config = None
        self.uuid = None

        config = Config.load(store, config)
        self._update_config(store, config)

        # Use cached port numbers when possible. The ZMQError is thrown
        # when the requested port is not available; let a new one be
        # auto-assigned when that happens.

        rep, pub = port.load(store, self.uuid)

        try:
            self.pub = Protocol.Publish.Server(port=pub, avoid=port.used())
        except zmq.error.ZMQError:
            self.pub = Protocol.Publish.Server(port=None, avoid=port.used())

        try:
            self.rep = RequestServer(self, port=rep, avoid=port.used())
        except zmq.error.ZMQError:
            self.rep = RequestServer(self, port=None, avoid=port.used())

        port.save(store, self.uuid, self.rep.port, self.pub.port)

        provenance = dict()
        provenance['stratum'] = 0
        provenance['hostname'] = self.rep.hostname
        provenance['rep'] = self.rep.port
        provenance['pub'] = self.pub.port

        self.provenance = list()
        self.provenance.append(provenance)

        # A bit of a chicken and egg problem with the provenance. It can't be
        # established until the listener ports are known; we can't establish
        # the listener ports without knowing our UUID; we don't know the UUID
        # until the configuration is loaded. We're doctoring the configuration
        # after-the-fact, and thus need to refresh the local cache to ensure
        # consistency.

        self.config[self.uuid]['provenance'] = self.provenance
        Config.add(store, self.config)

        # The cached configuration managed by Config needs to be in its final
        # form before creating a local Store instance. For the sake of future
        # calls to get() we need to be sure that there are no existing instances
        # in the cache, the daemon needs to always get back the instance
        # containing authoritative items.

        existing = Get.clear(store)

        if existing is None:
            pass
        else:
            # It's possible this should be a warning as opposed to a hard error.
            raise RuntimeError('the Daemon needs to be started before any client requests against its store name')

        self.store = Get.get(store)

        # Local machinery is intact. Invoke the setup() method, which is the
        # hook for the developer to establish their own custom Item classes
        # before filling in with empty caching Item classes.

        self.setup()
        self._setup_missing()

        # Restore any persistent values, and enable the retention of future
        # persistent values. If there are no persistent items present for this
        # daemon the call to _restore() is a no-op, and the persistence
        # subprocess will exit.

        self._restore()
        self._begin_persistence()

        # The promise is that setup_final() gets invoked after everything else
        # is ready, but before we go on the air.

        self.setup_final()

        # Ready to go on the air.

        discovery = Protocol.Discover.DirectServer(self.rep.port)

        guides = Protocol.Discover.search(wait=True)
        self._publish_config(guides)


    def add_item(self, item_class, key, **kwargs):
        """ Add an :class:`mktl.Item` to this daemon instance; this is the entry
            point for establishing an authoritative item, one that will handle
            inbound get/set request and the like. The *kwargs* will be passed
            directly to the *item_class* when it is called to be instantiated.
        """

        try:
            self._items[key]
        except KeyError:
            raise KeyError("this daemon is not authoritative for the key '%s'" %(key))

        existing = self.store._items[key]

        if existing is None:
            kwargs['authoritative'] = True
            kwargs['pub'] = self.pub
            new_item = item_class(self.store, key, **kwargs)
        else:
            raise RuntimeError('duplicate item not allowed: ' + key)


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
        arguments.append(self.store.name)
        arguments.append(self.uuid)

        pipe = subprocess.PIPE
        self.persistence = subprocess.Popen(arguments)


    def _publish_config(self, targets=tuple()):
        """ Put our local configuration out on the wire.
        """

        config = dict(self.config)
        payload = dict()
        payload['data'] = config
        message = Protocol.Message.Request('CONFIG', self.store.name, payload)

        for address,port in targets:
            try:
                Protocol.Request.send(address, port, message)
            except zmq.error.ZMQError:
                pass


    def _restore(self):
        """ Bring back any values in the local persistent cache, and push them
            through to affected Items for handling.
        """

        loaded = persist.load(self.store.name, self.uuid)

        for key in loaded.keys():
            faux_message = loaded[key]
            item = self.store[key]
            item.req_set(faux_message)


    def _update_config(self, store, config):

        uuid = list(config.keys())[0]
        self.config = config
        self.uuid = uuid
        Config.add(store, config)

        config = Config.Items.get(store)
        self._items.update(config)


    def setup(self):
        """ Subclasses should override the :func:`setup` method to invoke
            :func:`add_item` for any custom :class:`mktl.Item` subclasses
            or otherwise execute custom code. When :func:`setup` is called
            the bulk of the :class:`Store` machinery is in place, but cached
            values have not been loaded, nor has the presence of this daemon
            been announced. The default implementation of this method takes
            no actions.
        """

        pass


    def _setup_missing(self):
        """ Inspect the locally known list of :class:`mktl.Item` instances;
            create default, caching instances for any that were not previously
            populated by the call to :func:`setup`.
        """

        local = self._items.keys()
        local = list(local)

        for key in local:
            existing = self.store._items[key]

            if existing is None:
                self.add_item(item.Item, key)


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

    def __init__(self, daemon, *args, **kwargs):
        Protocol.Request.Server.__init__(self, *args, **kwargs)
        self.daemon = daemon


    def req_config(self, request):

        target = request.target

        if target == self.daemon.store.name:
            config = dict(self.daemon.config)
        else:
            config = Config.get(target)

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

        if store != self.daemon.store.name:
            raise ValueError("this request is for %s, but this daemon is in %s" % (repr(store), repr(self.daemon.store.name)))

        if key in self.daemon._items:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        payload = self.daemon.store[key].req_get(request)
        return payload


    def req_set(self, request):

        store, key = request.target.split('.', 1)

        if store != self.daemon.store.name:
            raise ValueError("this request is for %s, but this daemon is in %s" % (repr(store), repr(self.daemon.store.name)))

        if key in self.daemon._items:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        payload = self.daemon.store[key].req_set(request)
        return payload


    def req_hash(self, request):

        store = request.target
        if store == '':
            store = None

        cached = Config.Hash.get(store)
        return cached


# end of class RequestServer


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
