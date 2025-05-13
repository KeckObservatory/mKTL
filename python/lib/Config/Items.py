""" Decompose a standard configuration into a by-key dictionary for use by
    other classes internal to the mKTL Python module.
"""

from . import Cache
from . import Hash

cache = dict()
hashes = dict()


def get(store):
    """ Parse the cached configuration for the specified *store* into a
        by-key dictionary, with additional fields populated from block-wide
        definitions.
    """

    # Return a cached version if the contents stored by the Cache haven't
    # been modified.

    try:
        cached = cache[store]
    except KeyError:
        pass
    else:
        if hashes[store] == Hash.get(store):
            return cached

    config = Cache.get(store)
    by_key = dict()

    for uuid in config.keys():
        block = config[uuid]

        items = block['items']
        for key in items.keys():
            item = items[key]

            # Making a fresh dictionary here so we don't modify what's stored
            # in the Cache, which is supposed to be representative of the
            # on-the-wire representation.

            copied = dict(item)
            copied['uuid'] = uuid

            try:
                copied['provenance'] = block['provenance']
            except KeyError:
                pass

            by_key[key] = copied

    hashes[store] = Hash.get(store)
    cache[store] = by_key

    return by_key



def clear(store):
    """ Clear the cached by-item configuration for the specified store.
    """

    try:
        del cache[store]
    except KeyError:
        pass

    try:
        del hashes[store]
    except KeyError:
        pass

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
