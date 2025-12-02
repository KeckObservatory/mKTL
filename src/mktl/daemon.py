
import atexit
import os
import platform
import queue
import resource
import socket
import subprocess
import sys
import time
import zmq

from . import begin
from . import config
from . import item
from . import json
from . import poll
from . import protocol
from . import store


class Daemon:
    """ The mKTL :class:`Daemon` is a facilitator for common mKTL actions taken
        in a daemon context: loading a configuration file, instantiating
        :class:`mktl.Item` instances, and commencing routine operations.

        The developer is expected to subclass the :class:`Daemon` class and
        implement a :func:`setup` method, and/or a :func:`setup_final`
        method. This subclass is the gateway between mKTL functionality and
        the domain-specific custom code appropriate for the developer's
        application.

        The *store* argument is the name of the store that this daemon is
        providing items for; *alias* is the unique name of this mKTL daemon,
        and is used to locate the configuration file that defines the items
        for which this daemon is authoritative.

        *arguments* is expected to be an :class:`argparse.ArgumentParser`
        instance, though in practice it can be any Python object with specific
        named attributes of interest to a :class:`Daemon` subclass; the
        *arguments* argument is not required. This is intended to be a vehicle
        for custom subclasses to receive key information from command-line
        arguments, such as the location of an auxiliary configuration file
        containing information about a hardware controller.
    """

    def __init__(self, store, alias, override=False, arguments=None):

        self.alias = alias
        self.config = None
        self.store = None
        self.uuid = None

        self.config = config.get(store, alias)
        self.uuid = self.config.authoritative_uuid

        if self.uuid is None:
            # This isn't supposed to happen. Catching it here just in case.
            raise RuntimeError('mktl.config did not set my UUID!')

        # Use cached port numbers when possible. The ZMQError is thrown
        # when the requested port is not available; let a new one be
        # auto-assigned when that happens.

        rep, pub = _load_port(store, self.uuid)
        avoid = _used_ports()

        # Before we proceed let's take a moment to verify whether another
        # instance of this daemon is already running on those ports. It's
        # important to make this check before invoking the publish+request
        # servers, as they will rewrite local cache files used to remember
        # which port is being used by which UUID.

        if rep:
            self._test_port(store, rep)

        try:
            self.pub = protocol.publish.Server(port=pub, avoid=avoid)
        except zmq.error.ZMQError:
            self.pub = protocol.publish.Server(port=None, avoid=avoid)

        avoid = _used_ports()

        try:
            self.rep = RequestServer(self, port=rep, avoid=avoid)
        except zmq.error.ZMQError:
            self.rep = RequestServer(self, port=None, avoid=avoid)

        _save_port(store, self.uuid, self.rep.port, self.pub.port)

        # A bit of a chicken and egg problem with the provenance. It can't be
        # established until the listener ports are known; we can't establish
        # the listener ports without knowing our UUID; we don't know the UUID
        # until the configuration is loaded. We're doctoring the configuration
        # after-the-fact, and thus need to refresh the local cache to ensure
        # consistency.

        block = self.config.authoritative_block
        config.add_provenance(block, self.rep.hostname, self.rep.port, self.pub.port)
        self.config.update(block)

        # The cached configuration needs to be in its final form before creating
        # a local Store instance. For the sake of future calls to get() we need
        # to be sure that there are no existing instances in the cache, the
        # daemon needs to always get back the instance containing authoritative
        # items.

        existing = begin._clear(store)

        if existing is None:
            pass
        else:
            # It's possible this should be a warning as opposed to a hard error.
            raise RuntimeError('the Daemon needs to be started before any client requests against its store name')

        self.store = begin.get(store)

        # Local machinery is intact. Invoke the setup() method, which is the
        # hook for the developer to establish their own custom Item classes
        # before filling in with empty caching Item classes.

        self.setup()
        self._setup_builtin_items()
        self._setup_missing()

        # The configuration should now be finalized. Make sure it is written
        # out to disk so that subprocesses (if any) can load it before we're
        # fully on the air.

        self.config.save()

        # Apply any initial values according to the configuration contents.

        self._setup_initial_values()

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

        self._discovery = protocol.discover.DirectServer(self.rep.port)
        config.announce(self.config, self.uuid, override)


    def add_item(self, item_class, key, **kwargs):
        """ Add an :class:`mktl.Item` to this daemon instance; this is the entry
            point for establishing an authoritative item, one that will handle
            inbound get/set request and the like. The *kwargs* will be passed
            directly to the *item_class* when it is called to be instantiated.
        """

        key = key.lower()

        try:
            self.config.authoritative_items[key]
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
        markpersisted = os.path.join(dirname, 'markpersisted')

        arguments = list()
        arguments.append(sys.executable)
        arguments.append(markpersisted)
        arguments.append(self.store.name)
        arguments.append(self.uuid)

        self.persistence = subprocess.Popen(arguments)


    def _restore(self):
        """ Bring back any values in the local persistent cache, and push them
            through to affected Items for handling.
        """

        loaded = _load_persistent(self.store.name, self.uuid)

        for key in loaded.keys():
            faux_message = loaded[key]
            item = self.store[key]
            item.req_set(faux_message)


    def setup(self):
        """ Subclasses should override the :func:`setup` method to invoke
            :func:`add_item` for any custom :class:`mktl.Item` subclasses
            or otherwise execute custom code. When :func:`setup` is called
            the bulk of the :class:`Daemon` machinery is in place, but cached
            values have not been loaded, nor has the presence of this daemon
            been announced. The default implementation of this method takes
            no actions.
        """

        pass


    def _setup_builtin_items(self):
        """ Add the built-in :class:`mktl.Item` instances for this daemon.
            These items use standard suffixes applied to the unique alias
            assigned to this daemon.
        """

        # The configuration needs to be updated with these items before they
        # can be instantiated.

        block = self.config.authoritative_block
        items = block['items']

        key = self.alias + 'clk'
        items[key] = dict()
        items[key]['description'] = 'Uptime for this daemon.'
        items[key]['type'] = 'numeric'
        items[key]['units'] = 'seconds'

        key = self.alias + 'cpu'
        items[key] = dict()
        items[key]['description'] = 'Processor consumption by this daemon.'
        items[key]['type'] = 'numeric'
        items[key]['units'] = 'percent'
        items[key]['settable'] = False

        key = self.alias + 'dev'
        items[key] = dict()
        items[key]['description'] = 'A terse description for the function of this daemon.'
        items[key]['type'] = 'string'
        items[key]['persist'] = True
        items[key]['initial'] = ''

        key = self.alias + 'host'
        items[key] = dict()
        items[key]['description'] = 'The hostname where this daemon is running.'
        items[key]['type'] = 'string'
        items[key]['initial'] = platform.node()
        items[key]['settable'] = False

        key = self.alias + 'mem'
        items[key] = dict()
        items[key]['description'] = 'Physical memory consumption by this daemon.'
        items[key]['type'] = 'numeric'
        items[key]['units'] = 'kilobytes'
        items[key]['settable'] = False

        self.config.update(block, save=False)
        self.store._update_config()


        # Having updated the configuration, now instantiate the built-in items.

        self.add_item(Uptime, self.alias + 'clk')
        self.add_item(MemoryUsage, self.alias + 'mem')
        self.add_item(ProcessorUsage, self.alias + 'cpu')

        for suffix in ('dev', 'host'):
            key = self.alias + suffix
            self.add_item(item.Item, key)


    def _setup_missing(self):
        """ Inspect the locally known list of :class:`mktl.Item` instances;
            create default, caching instances for any that were not previously
            populated by the call to :func:`setup`; this method is called before
            :func:`setup_final` is invoked.
        """

        for key in self.config.authoritative_items.keys():
            existing = self.store._items[key]

            if existing is None:
                self.add_item(item.Item, key)


    def _setup_initial_values(self):
        """ Apply all initial values defined in the configuration for all
            local authoritative items. If a persistent value is available
            it will override the default initial value.
        """

        items = self.config[self.uuid]['items']

        for key in items.keys():

            configuration = items[key]
            try:
                initial = configuration['initial']
            except KeyError:
                continue

            item = self.store[key]
            payload = protocol.message.Payload(initial)
            request = protocol.message.Request('SET', item.full_key, payload)
            item.req_initialize(request)


    def setup_final(self):
        """ Subclasses should override the :func:`setup_final` method to
            execute any/all code that should occur after all :class:`mktl.Item`
            instances have been created, including any non-custom
            :class:`mktl.Item` instances, but before this daemon
            announces its availability on the local network. The default
            implementation of this method takes no actions.
        """

        pass


    def _test_port(self, store, port):
        """ Look to see whether an instance of this daemon is already
            running on the cached port number, and if so, raise an
            exception to stop execution.
        """

        hostname = socket.getfqdn()
        request = protocol.message.Request('CONFIG', store)

        try:
            payload = protocol.request.send(hostname, port, request)
        except zmq.ZMQError:
            # Not running; perfect.
            return

        blocks = payload.value

        # There should only be one UUID in this block, because we're asking
        # a direct question of an authoritative daemon running on the same
        # host we're trying to run on. But that assumption is not being checked.

        for uuid,block in blocks.items():
            alias = block['alias']

            if alias == self.alias:
                raise RuntimeError("another instance of %s is running, aborting" % (alias))

        # Otherwise something _is_ running on that port, but it's not the
        # same daemon; someone took our port number! That's unfortunate
        # but they can have it, we'll be assigned a new one.


# end of class Daemon



class RequestServer(protocol.request.Server):

    def __init__(self, daemon, *args, **kwargs):
        protocol.request.Server.__init__(self, *args, **kwargs)
        self.daemon = daemon


    def req_config(self, request):

        target = request.target
        response = dict()

        if target == self.daemon.store.name:
            uuid = self.daemon.uuid
            configuration = dict(self.daemon.config[uuid])
            response[uuid] = configuration
        else:
            configuration = config.get(target)
            uuids = configuration.uuids()
            for uuid in uuids:
                response[uuid] = config[uuid]

        payload = protocol.message.Payload(response)
        return payload


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
            response = self.req_hash(request)
        elif type == 'SET':
            response = self.req_set(request)
        elif type == 'GET':
            response = self.req_get(request)
        elif type == 'CONFIG':
            response = self.req_config(request)
        else:
            raise ValueError('unhandled request type: ' + type)

        return response


    def req_get(self, request):

        store, key = request.target.split('.', 1)

        if store != self.daemon.store.name:
            raise ValueError("this request is for %s, but this daemon is in %s" % (repr(store), repr(self.daemon.store.name)))

        block = self.daemon.config[self.daemon.uuid]
        items = block['items']
        if key in items:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        response = self.daemon.store[key].req_get(request)
        return response


    def req_set(self, request):

        store, key = request.target.split('.', 1)

        if store != self.daemon.store.name:
            raise ValueError("this request is for %s, but this daemon is in %s" % (repr(store), repr(self.daemon.store.name)))

        block = self.daemon.config[self.daemon.uuid]
        items = block['items']
        if key in items:
            pass
        else:
            raise KeyError('this daemon does not contain ' + repr(key))

        ### This may be the right place to send a publish message indicating
        ### that a set request has been received. This would largely be a
        ### debug message, structured exactly like a publish request, but
        ### with a leading 'set:' for the topic to distinguish it from anything
        ### that might be a normal broadcast.

        ### This would allow a debug client to subscribe to all messages with
        ### a leading 'set:' topic.

        response = self.daemon.store[key].req_set(request)
        return response


    def req_hash(self, request):

        store = request.target
        if store == '':
            store = None

        hashes = config.get_hashes(store)
        payload = protocol.message.Payload(hashes)
        return payload


# end of class RequestServer




def _load_port(store, uuid):
    """ Return the REQ and PUB port numbers, if any, that were last used
        for the specified *store* and *uuid*. The numbers are returned as
        a two-item tuple (REQ, PUB). None will be returned if a specific
        value cannot be retrieved.
    """

    base_directory = config.directory()
    port_directory = os.path.join(base_directory, 'daemon', 'port', store)
    pub_filename = os.path.join(port_directory, uuid + '.pub')
    req_filename = os.path.join(port_directory, uuid + '.req')

    try:
        pub_port = open(pub_filename, 'r').read()
    except FileNotFoundError:
        pub_port = None
    else:
        pub_port = pub_port.strip()
        pub_port = int(pub_port)

    try:
        req_port = open(req_filename, 'r').read()
    except FileNotFoundError:
        req_port = None
    else:
        req_port = req_port.strip()
        req_port = int(req_port)

    return (req_port, pub_port)



def _save_port(store, uuid, req=None, pub=None):
    """ Save a REQ or PUB port number to the local disk cache for future
        restarts of a persistent daemon.
    """

    base_directory = config.directory()
    port_directory = os.path.join(base_directory, 'daemon', 'port', store)
    pub_filename = os.path.join(port_directory, uuid + '.pub')
    req_filename = os.path.join(port_directory, uuid + '.req')

    if os.path.exists(port_directory):
        if os.access(port_directory, os.W_OK) != True:
            raise OSError('cannot write to port directory: ' + port_directory)
    else:
        os.makedirs(port_directory, mode=0o775)

    if pub is not None:
        pub = int(pub)
        pub = str(pub)

        if os.path.exists(pub_filename):
            if os.access(pub_filename, os.W_OK) != True:
                raise OSError('cannot write to cache file: ' + pub_filename)

        pub_file = open(pub_filename, 'w')
        pub_file.write(pub + '\n')
        pub_file.close()

    if req is not None:
        req = int(req)
        req = str(req)

        if os.path.exists(req_filename):
            if os.access(req_filename, os.W_OK) != True:
                raise OSError('cannot write to cache file: ' + req_filename)

        req_file = open(req_filename, 'w')
        req_file.write(req + '\n')
        req_file.close()



def _used_ports():
    """ Return a set of port numbers that were previously in use on this host.
        There are enough ports in the available range that a previously used
        port can be "reserved" for that daemon unless/until there are no other
        ports available.
    """

    base_directory = config.directory()
    port_directory = os.path.join(base_directory, 'daemon', 'port')

    ports = set()
    targets = list()
    targets.append(port_directory)

    if os.path.exists(port_directory):
        pass
    else:
        return ports

    for target in targets:
        if os.path.isdir(target):
            contents = os.listdir(target)
            for thing in contents:
                targets.append(os.path.join(target, thing))
            continue

        port = open(target, 'r').read()
        port = port.strip()
        port = int(port)

        ports.add(port)

    return ports




persist_queues = dict()


def _load_persistent(store, uuid):
    """ Load any/all saved values for the specified *store* name and *uuid*.
        The values will be returned as a dictionary, with the item key as the
        dictionary key, and the value will be a
        :class:`protocol.message.Request` instance, as if it were a set request,
        so that the handling of any interpretation can be unified within the
        :class`Item` code.
    """

    loaded = dict()

    base_directory = config.directory()
    uuid_directory = os.path.join(base_directory, 'daemon', 'persist', uuid)

    try:
        files = os.listdir(uuid_directory)
    except FileNotFoundError:
        return loaded

    for key in files:
        if key[:5] == 'bulk:':
            continue

        filename = os.path.join(uuid_directory, key)
        bulk_filename = os.path.join(uuid_directory, 'bulk:' + key)

        raw_json = open(filename, 'rb').read()

        if len(raw_json) == 0:
            continue

        # The data on-disk is expected to be the payload component of a typical
        # mKTL response or broadcast, with an adjacent file containing the bulk
        # data, if any. In other words, exactly the components that would be
        # put into a protocol.message.Message instance.

        payload = json.loads(raw_json)

        try:
            bulk = open(bulk_filename, 'rb').read()
        except FileNotFoundError:
            bulk = None

        payload = protocol.message.Payload(**payload, bulk=bulk)
        message = protocol.message.Request('SET', key, payload)
        loaded[key] = message

    return loaded



def _save_persistent(item, *args, **kwargs):
    """ Queue the Item._value attribute to be written out to disk. Additional
        arguments are ignored so that this method can be registered as a
        callback for a :class:`mktl.Item` instance.
    """

    uuid = item.config['uuid']

    try:
        pending = persist_queues[uuid]
    except KeyError:
        pending = PendingPersistence(uuid)

    by_prefix = dict()
    payload = item.to_payload()

    if payload.bulk is not None:
        by_prefix['bulk'] = payload.bulk

    by_prefix[''] = payload.encapsulate()

    pending.put((item.key, by_prefix))



def _flush_persistent():
    """ Request that any/all background threads with queued :func:`save` calls
        flush their queue out to disk. This call will block until the flush is
        complete.
    """

    for uuid in persist_queues.keys():
        pending = persist_queues[uuid]
        pending.flush()


atexit.register(_flush_persistent)



class PendingPersistence:
    """ This is a helper class to accumulate saved values, and periodically
        write them out to disk.
    """

    def __init__(self, uuid):

        self.uuid = uuid
        persist_queues[uuid] = self

        base_directory = config.directory()
        uuid_directory = os.path.join(base_directory, 'daemon', 'persist', uuid)

        if os.path.exists(uuid_directory):
            if os.access(uuid_directory, os.W_OK) != True:
                raise OSError('cannot write to persistent directory: ' + uuid_directory)
        else:
            os.makedirs(uuid_directory, mode=0o775)

        self.directory = uuid_directory

        try:
            # Available in Python 3.7+.
            self.queue = queue.SimpleQueue()
        except AttributeError:
            self.queue = queue.Queue()

        self.put = self.queue.put

        # Use a background poller to flush events to disk every five seconds.
        poll.start(self.flush, 5)


    def flush(self):

        pending = dict()

        while True:
            try:
                key, value = self.queue.get(block=False)
            except queue.Empty:
                break

            # Only write out the most recent value. Whatever is last in the
            # queue, that's what we will commit to disk.

            pending[key] = value


        for key in pending.keys():
            value = pending[key]

            for prefix in value.keys():
                if prefix == '':
                    filename = os.path.join(self.directory, key)
                else:
                    filename = os.path.join(self.directory, prefix + ':' + key)

                bytes = value[prefix]
                file = open(filename, 'wb')
                file.write(bytes)
                file.close()


    def put(self, *args, **kwargs):
        """ The reference to this method should be replaced when initialization
            occurs, but once in a blue moon an AttributeError exception sneaks
            through.
        """

        return self.queue.put(*args, **kwargs)


# end of class PendingPersistence



class MemoryUsage(item.Item):

    def __init__(self, *args, **kwargs):
        item.Item.__init__(self, *args, **kwargs)
        self.poll(1)


    def perform_get(self):

        resources = resource.getrusage(resource.RUSAGE_SELF)
        max_usage = resources.ru_maxrss

        return self.to_payload(max_usage)


# end of class MemoryUsage



class ProcessorUsage(item.Item):

    def __init__(self, *args, **kwargs):
        resources = resource.getrusage(resource.RUSAGE_SELF)
        self.previous_usage = resources.ru_utime + resources.ru_stime
        self.previous_time = time.time()

        item.Item.__init__(self, *args, **kwargs)
        self.poll(1)


    def perform_get(self):

        resources = resource.getrusage(resource.RUSAGE_SELF)
        current_usage = resources.ru_utime + resources.ru_stime
        current_time = time.time()

        consumed = current_usage - self.previous_usage
        elapsed = current_time - self.previous_time

        self.previous_usage = current_usage
        self.previous_time = current_time

        if elapsed > 0:
            usage_percent = 100 * consumed / elapsed
        elif consumed > 0:
            usage_percent = 100
        else:
            usage_percent = 0

        return self.to_payload(usage_percent, current_time)


# end of class ProcessorUsage



class Uptime(item.Item):

    def __init__(self, *args, **kwargs):

        self.starttime = time.time()
        item.Item.__init__(self, *args, **kwargs)
        self.poll(1)


    def perform_get(self):
        current_time = time.time()
        uptime = current_time - self.starttime

        return self.to_payload(uptime, current_time)


# end of class Uptime


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
