''' Port numbers are cached for listeners.
'''

import os

from .. import Config


def load(store, uuid):
    ''' Return the REQ and PUB port numbers, if any, that were last used
        for the specified *store* and *uuid*. The numbers are returned as
        a two-item tuple (REQ, PUB). None will be returned if a specific
        value cannot be retrieved.
    '''

    base_directory = Config.File.directory()
    port_directory = os.path.join(base_directory, 'daemon', 'port', store)
    pub_filename = os.path.join(port_directory, uuid + '.pub')
    req_filename = os.path.join(port_directory, uuid + '.req')

    try:
        pub_port = open(pub_filename, 'r').read()
    except FileNotFoundError:
        pub_port = None
    else:
        pub_port = pub_port.strip()
        pub_port = int(pub_port)

    try:
        req_port = open(req_filename, 'r').read()
    except FileNotFoundError:
        req_port = None
    else:
        req_port = req_port.strip()
        req_port = int(req_port)

    return (req_port, pub_port)



def save(store, uuid, req=None, pub=None):
    ''' Save a REQ or PUB port number to the local disk cache for future
        restarts of a persistent daemon.
    '''

    base_directory = Config.File.directory()
    port_directory = os.path.join(base_directory, 'daemon', 'port', store)
    pub_filename = os.path.join(port_directory, uuid + '.pub')
    req_filename = os.path.join(port_directory, uuid + '.req')

    if os.path.exists(port_directory):
        if os.access(port_directory, os.W_OK) != True:
            raise OSError('cannot write to port directory: ' + port_directory)
    else:
        os.makedirs(port_directory, mode=0o775)

    if pub is not None:
        pub = int(pub)
        pub = str(pub)

        if os.path.exists(pub_filename):
            if os.access(pub_filename, os.W_OK) != True:
                raise OSError('cannot write to cache file: ' + pub_filename)

        pub_file = open(pub_filename, 'w')
        pub_file.write(pub + '\n')
        pub_file.close()

    if req is not None:
        req = int(req)
        req = str(req)

        if os.path.exists(req_filename):
            if os.access(req_filename, os.W_OK) != True:
                raise OSError('cannot write to cache file: ' + req_filename)

        req_file = open(req_filename, 'w')
        req_file.write(req + '\n')
        req_file.close()



def used():
    ''' Return a set of port numbers that were previously in use on this host.
    '''

    base_directory = Config.File.directory()
    port_directory = os.path.join(base_directory, 'daemon', 'port')

    ports = set()
    targets = list()
    targets.append(port_directory)

    if os.path.exists(port_directory):
        pass
    else:
        return ports

    for target in targets:
        if os.path.isdir(target):
            contents = os.listdir(target)
            for thing in contents:
                targets.append(os.path.join(target, thing))
            continue

        port = open(target, 'r').read()
        port = port.strip()
        port = int(port)

        ports.add(port)

    return ports



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
