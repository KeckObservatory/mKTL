""" Implmentation of the top-level :func:`get` method. This is intended to be
    the principal entry point for users interacting with a key/value store.
"""

import threading

from . import config
from . import protocol
from .store import Store


_cache = dict()
_cache_lock = threading.Lock()

def _clear(store):
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



def discover(*targets):
    """ Look for mKTL registries, both by broadcasting on the local network
        and by directly querying any/all supplied addresses. The goal of
        this discovery is to populate a local cache including any/all stores
        known to these registries, for all future queries. This is especially
        helpful if the local client is not on the same network as the
        registries of interest.
    """

    registries = protocol.discover.search(wait=True, targets=targets)

    if len(registries) == 0:
        raise RuntimeError('no registries available')

    # Hacking the timeout for discovery, this is not expected to throw
    # errors with minimal delay.

    old_timeout = protocol.request.Client.timeout
    protocol.request.Client.timeout = 0.5

    for address,port in registries:
        request = protocol.message.Request('HASH')
        try:
            payload = protocol.request.send(address, port, request)
        except:
            continue

        hashes = payload.value

        for store in hashes.keys():
            request = protocol.message.Request('CONFIG', store)
            payload = protocol.request.send(address, port, request)

            blocks = payload.value

            if blocks:
                configuration = config.get(store)
                for uuid,block in blocks.items():
                    configuration.update(block)


    protocol.request.Client.timeout = old_timeout



def get(store, key=None):
    """ The :func:`get` method is intended to be the primary entry point for
        all interactions with a key/value store.

        The return value is either a cached :class:`Store` or :class:`Item`
        instance. If both a *store* and a *key* are specified, the requested
        item will be returned from the specified *store*. The same will occur
        if the sole argument is a store and key name concatenated with a dot
        (store.KEY). A :class:`Store` instance will be returned if the sole
        argument provided is a *store* name. Both the *store* and the *key*
        are case-insensitive, all arguments are translated to lower case
        before proceeding.

        If the caller always uses :func:`get` to retrieve a :class:`Store` or
        :class:`Item` they will always receive the same instance of that class.
        In that sense, :func:`get` is a factory method enforcing a singleton
        pattern.
    """

    if store is None:
        raise ValueError('the store name must be specified')

    store = str(store)
    store = store.lower()

    if key is None:
        if '.' in store:
            store, key = store.split('.', 1)
    else:
        key = str(key)
        key = key.lower()

    # Work from the in-memory cache of Store instances first. This sequence
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

    # Start with whatever is available in memory, or the local disk cache.

    configuration = config.get(store)

    # Try the network if that didn't yield results.

    if len(configuration) > 0:
        # Confirm the on-disk contents are still valid.
        refresh(configuration)

    if len(configuration) == 0:
        # Nothing valid cached locally. Broadcast for responses.
        registries = protocol.discover.search()
        if len(registries) == 0:
            raise RuntimeError("no configuration available for '%s' (local or remote)" % (store))

        hostname,port = registries[0]
        message = protocol.message.Request('CONFIG', store)
        payload = protocol.request.send(hostname, port, message)

        blocks = payload.value

        if blocks:
            for uuid,block in blocks.items():
                configuration.update(block)
        else:
            raise RuntimeError("no configuration available for '%s' (local or remote)" % (store))


    # If we made it this far without raising an exception there must be a valid
    # configuration available for use.

    _cache_lock.acquire()
    try:
        store = _cache[store]
    except KeyError:
        store = Store(store)
        _cache[store.name] = store
    finally:
        _cache_lock.release()

    if key is None:
        return store
    else:
        return store[key]



def refresh(configuration):
    """ This is a helper method for :func:`get` defined in this file. The
        *configuration* passed in here was loaded from a file. Inspect the
        provenance for each block and attempt to refresh the local contents.
        Save any changes back to disk for future clients.
    """

    store = configuration.store

    for uuid in configuration.uuids():
        block = configuration[uuid]
        local_hash = block['hash']
        updated = False

        # Make a copy of the provenance sequence, traversing it in reverse
        # order (highest stratum first) looking for an updated configuration.

        try:
            provenance = block['provenance']
        except KeyError:
            # Must be local.
            return

        provenance = list(provenance)
        provenance.reverse()

        for stratum in provenance:
            hostname = stratum['hostname']
            rep = stratum['rep']

            client = protocol.request.client(hostname, rep)
            request = protocol.message.Request('HASH', store)

            try:
                client.send(request)
            except TimeoutError:
                # No response from this daemon; move on to the next entry in
                # the provenance. If no daemons respond the client will have
                # to rely on the local disk cache.
                continue

            response = request.wait(timeout=5)

            if response is None:
                # No response from this daemon; it's broken somehow. Move on.
                continue

            hashes = response.payload.value
            if hashes is None:
                # No response available.
                continue

            try:
                remote_hash = hashes[store][uuid]
            except KeyError:
                # This block is not present on the remote side. This implies
                # our local cache is bad, either because the provenance is no
                # longer correct, or the UUID has changed. Clear the cache and
                # keep looking for a better answer; we're still iterating over
                # the previously known provenance.

                configuration.remove(uuid)
                continue

            if local_hash != remote_hash:
                # Mismatch; need to request an update before proceeding.
                message = protocol.message.Request('CONFIG', store)
                client.send(message)
                ### Again, exception handling may be required, though the
                ### previous request went through, so there shouldn't be a
                ### a fresh exception here unless the remote daemon just
                ### went offline.
                response = message.wait(timeout=5)

                if response is None:
                    # No response available.
                    continue

                new_config = response.payload.value

                if new_config is None:
                    # No response available.
                    continue

                # This is not checking to see whether the UUID is present in the
                # results-- it is assumed, because the UUID was present in the
                # response to the HASH query prior to reaching this point.

                new_block = new_config[uuid]
                configuration.update(new_block)
                break



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
