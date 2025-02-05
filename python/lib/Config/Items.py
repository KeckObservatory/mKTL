''' Decompose a standard configuration into a by-key dictionary for use by
    other classes internal to the mKTL Python module.
'''

from . import Cache

cache = dict()
hashes = dict()


def get(store):
    ''' Parse the cached configuration for the specified *store* into a
        by-key dictionary, with additional fields populated from block-wide
        definitions.
    '''

    config = Cache.get(store)

    # Return a cached version if the contents stored by the Cache haven't
    # been modified.

    try:
        cached = cache[store]
    except KeyError:
        pass
    else:
        if hashes[store] == config['hash']:
            return cached

    by_key = dict()

    for uuid in config.keys():
        block = config[uuid]

        for item in block['keys']:
            key = item['name']

            # Making a fresh dictionary here so we don't modify what's
            # stored in the Cache.

            copied = dict(item)
            copied['uuid'] = uuid
            copied['provenance'] = block['provenance']

            by_key[key] = copied

    hashes[store] = config['hash']
    cached[store] = by_key

    return by_key



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
