
import os
import uuid

from ..Protocol import Json


def directory():
    ''' Return the directory location where we should be loading and/or saving
        configuration files.
    '''

    found = directory.found

    if found is not None:
        return found

    try:
        found = os.environ['MKTL_HOME']
    except KeyError:
        pass
    else:
        directory.found = found
        return found

    try:
        home = os.environ['HOME']
    except KeyError:
        return None

    found = os.path.join(home, '.mKTL')

    directory.found = found
    return found

directory.found = None



def load(name, specific=None):
    ''' Load the configuration for the specified store name. If *specific* is
        not None, it is expected to be the unique string corresponding to a
        single configuration file, either a unique string of the caller's
        choice for a locally authoritative configuration, or the UUID for a
        cached file. Results are returned as a dictionary, keyed by the UUID,
        and the configuration contents as the value. The configuration contents
        are fully parsed from their on-disk JSON format.
    '''

    if specific is not None:
        return load_one(name, specific)

    base_directory = directory()

    if base_directory is None:
        raise RuntimeError('cannot determine location of mKTL configuration files')

    daemon_directory = os.path.join(base_directory, 'daemon', 'store', name)
    cache_directory = os.path.join(base_directory, 'client', 'cache', name)

    if os.path.isdir(daemon_directory) or os.path.isdir(cache_directory):
        pass
    else:
        raise ValueError('no locally stored configuration for ' + repr(name))

    files = list()

    try:
        daemon_files = os.listdir(daemon_directory)
    except FileNotFoundError:
        daemon_files = tuple()

    for daemon_file in daemon_files:
        file = os.path.join(daemon_directory, daemon_file)
        files.append(file)

    try:
        cache_files = os.listdir(cache_directory)
    except FileNotFoundError:
        cache_files = tuple()

    for cache_file in cache_files:
        file = os.path.join(cache_directory, cache_file)
        files.append(file)


    results = dict()
    for file in files:
        loaded = load_one(name, file)
        new_uuid = list(loaded.keys())[0]
        if new_uuid in results:
            pass
        else:
            results.update(loaded)

    return results



def load_one(store, specific):
    ''' Similar to :func:`load`, except only ingesting a single file. A lot of
        checks will be bypassed if *specific* is provided as an absolute path;
        it is assumed the caller knows exactly which file they want, and have
        provided the full and correct path.
    '''

    # Some of these checks are redundant if we got here via the load() method,
    # but it's unavoidable that we need the information in both places.

    base_directory = directory()

    if base_directory is None:
        raise RuntimeError('cannot determine location of mKTL configuration files')

    daemon_directory = os.path.join(base_directory, 'daemon', 'store', store)
    cache_directory = os.path.join(base_directory, 'client', 'cache', store)


    if os.path.isabs(specific):
        if os.path.exists(specific):
            target_filename = specific
        else:
            raise ValueError('file not found: ' + repr(specific))

    else:
        if specific[-5:] != '.json':
            base_filename = specific
            json_filename = base_filename + '.json'
        else:
            base_filename = specific[:-5]
            json_filename = specific

        daemon_filename = os.path.join(daemon_directory, json_filename)
        cache_filename = os.path.join(cache_directory, json_filename)

        if os.path.exists(daemon_filename):
            target_filename = daemon_filename
        elif os.path.exists(cache_filename):
            target_filename = cache_filename
        else:
            raise ValueError("file not found in %s: %s" % (base_directory, repr(specific)))

        return load_one(store, target_filename)


    # After passing through the above conditions we have an absolute path
    # to the filename that should be loaded. Still need to do the check
    # for the adjacent UUID file if this is a daemon load of an authoritative
    # configuration file.

    base_filename = target_filename[:-5]

    if daemon_directory in target_filename:
        uuid_filename = base_filename + '.uuid'

        if os.path.exists(uuid_filename):
            target_uuid = open(uuid_filename, 'r').read()
            target_uuid = target_uuid.strip()
        else:
            target_uuid = str(uuid.uuid4())
            writer = open(uuid_filename, 'w')
            writer.write(target_uuid)
            writer.close()

    elif cache_directory in target_filename:
        # This should always be true if we sailed through all the previous
        # conditions.

        target_uuid = os.path.basename(base_filename)

    else:
        raise ValueError("file not found in %s: %s" % (base_directory, repr(specific)))

    raw_json = open(target_filename, 'r').read()
    configuration = Json.loads(raw_json)
    configuration['uuid'] = target_uuid

    results = dict()
    results[target_uuid] = configuration

    return results



def remove(store, uuid):
    ''' Remove the cache file associated with this store name and UUID.
        Takes no action and throws no errors if the file does not exist.
    '''

    base_directory = directory()
    json_filename = uuid + '.json'

    cache_directory = os.path.join(base_directory, 'client', 'cache', name)
    target_filename = os.path.join(cache_directory, json_filename)

    try:
        os.remove(target_filename)
    except FileNotFoundError:
        pass



def save(name, configuration):
    ''' Save a configuration block to the cache directory. There are no
        provisions here for saving to the local directory, which is where
        configuration contents would be populated for an authoritative daemon.
    '''

    base_directory = directory()

    try:
        configuration['name']
    except KeyError:
        # Assume this is a dictionary of configuration blocks, as you might
        # get from Config.Cache.
        for uuid in configuration.keys():
            block = configuration[uuid]
            save(name, block)
        return

    try:
        block_uuid = configuration['uuid']
    except KeyError:
        raise KeyError("the 'uuid' field must be in each configuration block")

    base_directory = directory()
    base_filename = block_uuid
    json_filename = base_filename + '.json'

    cache_directory = os.path.join(base_directory, 'client', 'cache', name)

    if os.path.exists(cache_directory):
        pass
    else:
        os.makedirs(cache_directory, mode=0o775)

    if os.access(cache_directory, os.W_OK) != True:
        raise OSError('cannot write to cache directory: ' + cache_directory)

    raw_json = Json.dumps(configuration)

    target_filename = os.path.join(cache_directory, json_filename)

    try:
        os.remove(target_filename)
    except FileNotFoundError:
        pass

    writer = open(target_filename, 'wb')
    writer.write(raw_json)
    writer.close()

    os.chmod(target_filename, 0o664)



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
