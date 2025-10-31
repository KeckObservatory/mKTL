""" Implmentation of the top-level :func:`get` method. This is intended to be
    the principal entry point for users interacting with a key/value store.
"""

import zmq

from . import config
from . import protocol
from .store import Store


_cache = dict()

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
        key = key.lower()

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

    # Start with whatever is available in memory, or the local disk cache.

    configuration = config.get(store)

    # Try the network if that didn't yield results.

    if len(configuration) > 0:
        # Confirm the on-disk contents are still valid.
        refresh(configuration)

    if len(configuration) == 0:
        # Nothing valid cached locally. Broadcast for responses.
        guides = protocol.discover.search()
        if len(guides) == 0:
            raise RuntimeError("no configuration available for '%s' (local or remote)" % (store))

        hostname,port = guides[0]
        message = protocol.message.Request('CONFIG', store)
        protocol.request.send(hostname, port, message)
        response = message.wait()

        new_config = response.payload.value

        if new_config is None:
            raise RuntimeError("no configuration available for '%s' (local or remote)" % (store))

        # If we made it this far the network came through with an answer.
        configuration.update(new_config)


    # If we made it this far we have something that the Store class can use.

    store = Store(store)
    _cache[store.name] = store

    if key is None:
        return store
    else:
        key = store[key]
        return key



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
            message = protocol.message.Request('HASH', store)

            try:
                client.send(message)
            except zmq.ZMQError:
                # No response from this daemon; move on to the next entry in
                # the provenance. If no daemons respond the client will have
                # to rely on the local disk cache.
                continue

            response = message.wait()

            hashes = response.payload.value
            if hashes is None:
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

                new_block = response.payload.value

                if new_block is None:
                    # No response available.
                    continue

                configuration.update(new_block)
                break



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
