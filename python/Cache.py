''' Routines for interacting with the local cache of service data.
'''

import os
import tempfile


def directory():
    ''' Return the expected cache directory location.
    '''

    found = directory.found

    if found is not None:
        return found

    ## TODO: Read the configuration file first.

    try:
        home = os.environ['HOME']
    except KeyError:
        return

    found = os.path.join(home, '.pot', 'cache')

    directory.found = found
    return found


directory.found = None



def id(service):
    ''' Return the last known configuration identifier for the requested
        service. If the service has no data or identifier, return None.
    '''

    cache_dir = directory()

    if cache_dir is None:
        return

    service_dir = os.path.join(cache_dir, service)
    service_id = os.path.join(service_dir, 'data.id')

    try:
        id_contents = open(service_id, 'r').read()
    except (OSError, FileNotFoundError):
        id_contents = None
    else:
        id_contents = id_contents.strip()
        if id_contents == '':
            id_contents = None

    return id_contents



def retrieve(service):
    ''' Retrieve the cached configuration for the designated *service*. Return
        None if no cached contents are available; otherwise, the cached contents
        are returned as a three-item dictionary, with keys hostname, id, and
        data; the hostname and id values are both handled as strings.
    '''

    ### TODO: should this just call each of three different methods? id(),
    ### hostname(), data()?

    cache_dir = directory()

    if cache_dir is None:
        return

    service_dir = os.path.join(cache_dir, service)

    hostname_filename = 'host'
    id_filename = 'data.id'
    data_filename = 'data'

    hostname_filename = os.path.join(service_dir, hostname_filename)
    id_filename = os.path.join(service_dir, id_filename)
    data_filename = os.path.join(service_dir, data_filename)

    try:
        hostname = open(hostname_filename, 'r').read()
    except (OSError, FileNotFoundError):
        return None

    try:
        id = open(id_filename, 'r').read()
    except (OSError, FileNotFoundError):
        return None

    try:
        data = open(data_filename, 'r').read()
    except (OSError, FileNotFoundError):
        return None

    hostname = hostname.strip()
    id = id.strip()
    data = data.strip()

    results = dict()
    results['hostname'] = hostname
    results['id'] = id
    results['data'] = data

    return results



def store(service, hostname, id, data):
    ''' Store the cached configuration for the designated *service*. The
        *hostname* reflects the source host for the data; the *id* is the
        unique identifier for the data; the *data* is the configuration for
        the service in question.
    '''

    cache_dir = directory()

    if cache_dir is None:
        raise RuntimeError('cannot determine cache directory location')

    service_dir = os.path.join(cache_dir, service)

    if os.path.exists(service_dir):
        pass
    else:
        os.makedirs(service_dir)

    cached_id = id(service)
    if cached_id == id:
        return

    writable = os.access(service_dir, os.W_OK)
    if writable != True:
        raise OSError('cannot write to cache directory ' + service_dir)


    hostname_filename = 'host'
    id_filename = 'data.id'
    data_filename = 'data'

    hostname_filename = os.path.join(service_dir, hostname_filename)
    id_filename = os.path.join(service_dir, id_filename)
    data_filename = os.path.join(service_dir, data_filename)

    new_hostname_filename = hostname_filename + '.new'
    new_id_filename = id_filename + '.new'
    new_data_filename = data_filename + '.new'

    hostname_file = open(new_hostname_filename, 'w')
    hostname_file.write(hostname)
    hostname_file.close()

    id_file = open(new_id_filename, 'w')
    id_file.write(id)
    id_file.close()

    data_file = open(new_data_filename, 'w')
    data_file.write(data)
    data_file.close()

    os.remove(hostname_filename)
    os.remove(id_filename)
    os.remove(data_filename)

    os.rename(new_hostname_filename, hostname_filename)
    os.rename(new_id_filename, id_filename)
    os.rename(new_data_filename, data_filename)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
