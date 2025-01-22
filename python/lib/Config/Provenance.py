''' Routines to handle provenance information.
'''

def add(block, hostname, port):
    ''' Add the provenance of this daemon to the supplied configuration
        block. The block is provided as a Python dictionary; the hostname
        and port combine to provide a unique location identifier that
        clients can use to track the chain of handling for this
        configuration data.

        The newly added provenance block is returned for convenient access,
        though it is already included in the configuration block.
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

    provenance = create(stratum + 1, hostname, port)

    block['provenance'].append(provenance)
    return provenance



def contains(block, provenance):
    ''' Does this configuration block contain this provenance? The stratum
        field of the provenance is ignored for this check.
    '''

    try:
        full_provenance = block['provenance']
    except KeyError:
        full_provenance = list()
        block['provenance'] = full_provenance

    # A simple 'if provenence in full' won't get the job done, because
    # the stratum may not be set in the provided provenance.

    hostname = provenance['hostname']
    port = provenance['port']

    for known in full_provenance:
        if known['hostname'] == hostname and known['port'] == port:
            return True

    return False



def create(stratum, hostname, port):
    ''' Create a provenance dictionary.
    '''

    provenance = dict()

    if stratum is None:
        pass
    else:
        provenance['stratum'] = stratum

    provenance['hostname'] = str(hostname)
    provenance['port'] = int(port)

    return provenance


def match(full_provenance1, full_provenance2):
    ''' Check the two provided provenance lists, and return True if they match.
        This check allows for one provenance to be longer than the other; if
        they are aligned from stratum 0 up to the full length of the shorter
        provenance, that is considered a match.
    '''

    # There has to be at least one matching stratum in the provenance
    # in order for it to be a match. Two empty provenances compared
    # against each other is still a negative result, there is no data.

    index = 0
    matched = False

    while True:
        try:
            provenance1 = full_provenance1[index]
        except IndexError:
            provenance1 = None

        try:
            provenance2 = full_provenance2[index]
        except IndexError:
            provenance2 = None

        if provenance1 is None or provenance2 is None:
            return matched

        # This next dictionary comparison requires all fields to match:
        # stratum, hostname, and port.

        if provenance1 != provenance2:
            return False

        matched = True
        index += 1


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
