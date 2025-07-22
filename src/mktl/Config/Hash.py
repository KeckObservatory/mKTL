""" How to generate a hash of a configuration block.
"""

import hashlib

from .. import json
from . import Cache

_cache = dict()


def get(name=None):
    """ Retrieve known hashes for a store's cached configuration blocks. Return
        all known hashes if no *name* is specified. The hashes are always
        returned as a dictionary, keyed first by store name, then by UUID for
        the associated configuration block.
    """

    if name is None:
        return dict(_cache)

    try:
        hashes = _cache[name]
    except KeyError:
        raise KeyError('no local configuration for ' + repr(name))

    return dict(hashes)



def hash(dumpable):
    """ Convert the supplied Python list or dictionary to JSON, hash the
        results, and return the hash. The mKTL protocol description limits
        the hash to 32 hexadecimal integers, but the specific hash type is
        unspecified, and allowed to vary between implementations-- as long
        as it is consistent.
    """

    raw_json = json.dumps(dumpable)

    hash = hashlib.shake_256(raw_json)
    hash = int(hash.hexdigest(16), 16)
    return hash



def rehash(store):
    """ Extract and cache the hash values associated with any configuration
        blocks for the specified *store*.
    """

    config = Cache.get(store)
    uuids = config.keys()

    for uuid in uuids:
        block = config[uuid]
        hash = block['hash']

        try:
            cached = _cache[store]
        except KeyError:
            cached = dict()
            _cache[store] = cached

        cached[uuid] = hash


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
