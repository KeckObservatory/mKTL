
from .Protocol import Discover
from .Protocol import Request


def get(name):
    ''' Retrieve the mKTL configuration for the specified `name`.
    '''

    ## check the cache

    ## confirm the current version is up-to-date by contacting the last known
    ## source of authority and asking for the current hash

    ## if the cache is not available, or the cache is stale, retrieve the
    ## current configuration from the last known source of authority

    ## return the configuration

    return



def addProvenance(block, hostname, port):
    ''' Add the provenance of this daemon to the supplied configuration
        block. The block is provided as a Python dictionary; the hostname
        and port combine to provide a unique location identifier that clients
        can use to track the chain of handling for this configuration data.
    '''

    try:
        full_provenance = block['provenance']
    except KeyError:
        full_provenance = list()
        block['provenance'] = full_provenance

    stratum = -1
    for provenance in full_provenance:
        if provenance['stratum'] > stratum:
            stratum = provenance['stratum']

    provenance = dict()
    provenance['stratum'] = stratum + 1
    provenance['hostname'] = hostname
    provenance['port'] = port

    block['provenance'].append(provenance)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
