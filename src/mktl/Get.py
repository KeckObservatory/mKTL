""" Implmentation of the top-level :func:`get` method. This is intended to be
    the principal entry point for users interacting with a key/value store.
"""

import zmq

from . import Config
from . import protocol
from .store import Store


_cache = dict()

def clear(store):
    """ Clear any cached :class:`mktl.Store` instances currently in the cache.
        Returns None if no instances were cleared; if there was an instance,
        it will be returned, largely to allow for possible error handling or
        inspection.
    """

    try:
        existing = _cache[store]
    except KeyError:
        return

    del _cache[store]
    return existing



def get(store, key=None):
    """ The :func:`get` method is intended to be the primary entry point for
        all interactions with a key/value store.

        The return value is either a cached :class:`Store` or :class:`Item`
        instance. If both a *store* and a *key* are specified, the requested
        item will be returned from the specified *store*. The same will occur
        if the sole argument is a store and key name concatenated with a dot
        (store.KEY). A :class:`Store` instance will be returned if the sole
        argument provided is a *store* name. Both the *store* and the *key*
        are case-insensitive.

        If the caller always uses :func:`get` to retrieve a :class:`Store` or
        :class:`Item` they will always receive the same instance of that class.
        In that sense, :func:`get` is a factory method enforcing a singleton
        pattern.
    """

    if store is None:
        raise ValueError('the store name must be specified')

    store = str(store)

    if key is None and '.' in store:
        store, key = store.split('.', 1)

    # Case-insensitivity is enforced:

    store = store.lower()

    if key is not None:
        key = str(key)
        key = key.upper()

    # Work from the local cache of Store instances first. This sequence
    # of checks is replicated at the end of the routine, after all the
    # handling of configuration data.

    try:
        store = _cache[store]
    except KeyError:
        pass
    else:
        if key is None:
            return store
        else:
            key = store[key]
            return key


    # Assume any configuration loaded into memory is recent and adequate.

    try:
        config = Config.get(store)
    except KeyError:
        config = None

    # If there is no local configuration, try loading one from disk. If that
    # succeeds we need to confirm it is still current before proceeding.

    if config is None:
        try:
            config = Config.load(store)
        except KeyError:
            config = None
        else:
            Config.add(store, config, save=False)
            config = refresh(store, config)

    # If we still don't have a configuration it's time to try a network
    # broadcast and hope someone's out there that can help.

    if config is None:
        guides = protocol.discover.search()
        if len(guides) == 0:
            raise RuntimeError("no configuration available for '%s' (local or remote)" % (store))

        hostname,port = guides[0]
        message = protocol.message.Request('CONFIG', store)
        protocol.request.send(hostname, port, message)
        response = message.wait()

        try:
            config = response.payload['value']
        except KeyError:
            raise RuntimeError("no configuration available for '%s' (local or remote)" % (store))

        # If we made it this far the network came through with an answer.
        Config.add(store, config)


    # The local reference to the configuration isn't necessary, when the Store
    # instance initializes it will request the current configuration from what's
    # in Config.Cache.

    store = Store(store)
    _cache[store.name] = store

    if key is None:
        return store
    else:
        key = store[key]
        return key



def refresh(store, config):
    """ This is a helper method for :func:`get` defined in this file. The
        *config* passed in here was loaded from a file. Inspect the provenance
        for each block and attempt to refresh the local contents. Save any
        changes back to disk for future clients.
    """

    for uuid in config.keys():
        block = config[uuid]
        local_hash = block['hash']
        updated = False

        # Make a copy of the provenance sequence, traversing it in reverse
        # order (highest stratum first) looking for an updated configuration.

        provenance = list(block['provenance'])
        provenance.reverse()

        for stratum in provenance:
            hostname = stratum['hostname']
            rep = stratum['rep']

            client = protocol.request.client(hostname, rep)
            message = protocol.message.Request('HASH', store)

            try:
                client.send(message)
            except zmq.ZMQError:
                # No response from this daemon; move on to the next entry in
                # the provenance. If no daemons respond the client will have
                # to rely on the local disk cache.
                continue

            response = message.wait()

            try:
                hashes = response.payload['value']
            except KeyError:
                # No response available.
                continue

            try:
                remote_hash = hashes[uuid]
            except KeyError:
                # This block is not present on the remote side.
                continue

            if local_hash != remote_hash:
                # Mismatch; need to request an update before proceeding.
                message = protocol.message.Request('CONFIG', store)
                client.send(message)
                ### Again, exception handling may be required, though the
                ### previous request went through, so there shouldn't be a
                ### a fresh exception here unless the remote daemon just
                ### went offline.
                response = message.wait()

                try:
                    new_block = response.payload['value']
                except KeyError:
                    # No response available.
                    continue

                Config.add(store, new_block)
                break


    # Whatever is present in the loaded cache is as good as it will get.
    # Return the current contents.

    config = Config.get(store)
    return config





# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
