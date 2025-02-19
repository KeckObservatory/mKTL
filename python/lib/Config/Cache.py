''' Local storage for configuration data.
'''

from . import File
from . import Hash

cache = dict()


def add(store, data, save=True):
    ''' Add a configuration block to the local cache. The *store* name is
        a simple string; *data* can either be a bare configuration block,
        or a dictionary of uuid-keyed configuration blocks. If *save* is
        set to True any additions will be written back out to the local
        cache on disk.
    '''

    try:
        blocks = cache[store]
    except KeyError:
        blocks = dict()
        cache[store] = blocks

    try:
        data['uuid']
    except KeyError:
        # Many blocks, keyed by UUID. No changes required to the format.
        pass
    else:
        # Just one block. Put it in dictionary form so we handle it the
        # same way below.
        uuid = data['uuid']
        data = {uuid: data}
        uuids = data.keys()

    # Make sure the blocks each have a hash.

    for uuid in data.keys():
        block = data[uuid]

        try:
            block['hash']
        except KeyError:
            block['hash'] = Hash.hash(block['keys'])


    # The update() call will replace any matching UUID keys with new blocks,
    # or add them if the UUID is unique.

    blocks.update(data)

    ## What about duplicate keys? Or is something upstream in the configuration
    ## handling chain handling that before this method gets called?

    Hash.rehash(store)
    if save == True:
        File.save(store, blocks)



def get(store):
    ''' Retrieve the locally stored configuration for a given *store*.
        A KeyError exception is raised if there are no locally stored
        configuration blocks for that store.
    '''

    try:
        blocks = cache[store]
    except KeyError:
        blocks = dict()
        cache[store] = blocks

    if len(blocks) == 0:
        raise KeyError('no local configuration for ' + repr(store))

    return blocks



def list():
    ''' Return a list of known store names currently in the local cache.
    '''

    names = cache.keys()
    results = []                # list() was redefined locally

    for name in names:
        blocks = cache[name]
        if len(blocks) > 0:
            results.append(name)

    return results



def remove(store, data, cleanup=True):
    ''' Remove a configuration block from the local cache. Matches are
        determined via UUID.
    '''

    try:
        blocks = cache[store]
    except KeyError:
        raise KeyError('no local configuration for ' + repr(store))

    target_uuid = data['uuid']

    try:
        del(blocks[target_uuid])
    except KeyError:
        raise KeyError('no matching block for UUID ' + repr(target_uuid))

    if cleanup == True:
        File.remove(store, target_uuid)
        Hash.rehash(store)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
