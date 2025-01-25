''' Local storage for configuration data.
'''

from . import File
from . import Hash
from . import Provenance

cache = dict()

def add(name, data):
    ''' Add a configuration block to the local cache.
    '''

    try:
        blocks = cache[name]
    except KeyError:
        blocks = []             # list() was redefined locally
        cache[name] = blocks

    try:
        data['hash']
    except KeyError:
        data['hash'] = Hash.hash(data['keys'])

    # The uniqueness of a configuration block is determined by UUID.
    # Remove the previous data block, if any.

    try:
        remove(name, data)
    except KeyError:
        pass

    ## What about duplicate keys? Or is something upstream in the configuration
    ## handling chain handling that before this method gets called?

    def get_uuid(config_block):
        return config_block['uuid']

    blocks.append(data)
    blocks.sort(key=get_uuid)
    Hash.rehash(name)
    File.save(name, blocks)



def get(name):
    ''' Retrieve the locally stored configuration for a given store. A KeyError
        exception is raised if there are no locally stored configuration blocks.
    '''

    try:
        blocks = cache[name]
    except KeyError:
        blocks = []             # list() was redefined locally
        cache[name] = blocks

    if len(blocks) == 0:
        raise KeyError('no local configuration for ' + repr(name))

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


def remove(name, data):
    ''' Remove a configuration block from the local cache. Matches are
        determined via UUID.
    '''

    try:
        blocks = cache[name]
    except KeyError:
        raise KeyError('no local configuration for ' + repr(name))

    to_remove = None
    target_uuid = data['uuid']

    for block in blocks:
        block_uuid = block['uuid']

        if block_uuid == target_uuid:
            to_remove = block
            break

    if to_remove is None:
        raise KeyError('no matching provenance found for data block')

    blocks.remove(to_remove)
    Hash.rehash(name)
    File.remove(name, data)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
