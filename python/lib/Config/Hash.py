''' How to generate a hash of a configuration block.
'''

import hashlib

from ..Protocol import Json
from . import Cache

cache = dict()


def get(name=None):
    ''' Retrieve a hash for a store's configuration. Return the full contents
        of the cache (as an iterable key/value pair sequence) if no *name* is
        specified.
    '''

    if name is None:
        return cache.items()

    try:
        hash = cache[name]
    except KeyError:
        raise KeyError('no local configuration for ' + repr(name))

    return hash


def hash(dumpable):
    ''' Convert the supplied Python list or dictionary to JSON, hash the
        results, and return the hash. The mKTL protocol description limits
        the hash to 32 hexadecimal integers, but the specific hash type is
        unspecified, and allowed to vary between implementations-- as long
        as it is consistent.
    '''

    json = Json.dumps(dumpable)

    hash = hashlib.shake_256(json)
    hash = int(hash.hexdigest(16), 16)
    return hash


def rehash(name):
    ''' Compute the hash for the locally cached data associated with a given
        store.
    '''

    config = Cache.get(name)
    hashable = list()

    for block in config:
        hashable.append(block['keys'])

    if len(hashable) == 0:
        return

    cache[name] = hash(hashable)



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
