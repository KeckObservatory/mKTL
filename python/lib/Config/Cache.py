''' Local storage for configuration data.
'''

cache = dict()


def add(self, name, data):
    ''' Add a configuration block to the local cache.
    '''

    try:
        blocks = cache[name]
    except KeyError:
        blocks = list()
        cache[name] = blocks

    ## Does there need to be a provenance check here?
    ## What about duplicate keys?

    blocks.append(data)


def get(self, name):
    ''' Retrieve the locally stored configuration for a given store. A KeyError
        exception is raised if there are no locally stored configuration blocks.
    '''

    try:
        blocks = cache[name]
    except KeyError:
        blocks = list()
        cache[name] = blocks

    if len(blocks) == 0:
        raise KeyError('no local configuration for ' + repr(name))

    return blocks


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
