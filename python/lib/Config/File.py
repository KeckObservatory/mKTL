
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


    # The generic "load" method is only used by clients, the daemon context
    # will know what it is looking for and provide a 'specific' argument.
    # The remaining checks here will ignore the daemon directory.

    cache_directory = os.path.join(base_directory, 'client', 'cache', name)

    if os.path.isdir(cache_directory):
        pass
    else:
        raise ValueError('no locally stored configuration for ' + repr(name))

    files = list()

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
        results.update(loaded)

    return results



def load_client(store, filename):
    ''' Load a single client configuration file; this method is called by
        :func:`load_one` as a final processing step.
    '''

    base_filename = filename[:-5]
    target_uuid = os.path.basename(base_filename)

    raw_json = open(filename, 'r').read()
    configuration = Json.loads(raw_json)
    configuration['uuid'] = target_uuid

    results = dict()
    results[target_uuid] = configuration

    return results



def load_daemon(store, filename):
    ''' Load a single daemon configuration file; this method is called by
        :func:`load_one` as a final processing step.
    '''

    base_filename = filename[:-5]
    uuid_filename = base_filename + '.uuid'

    if os.path.exists(uuid_filename):
        target_uuid = open(uuid_filename, 'r').read()
        target_uuid = target_uuid.strip()
    else:
        target_uuid = str(uuid.uuid4())
        writer = open(uuid_filename, 'w')
        writer.write(target_uuid)
        writer.close()

    configuration = dict()

    raw_json = open(filename, 'r').read()
    try:
        items = Json.loads(raw_json)
    except:
        print(repr(raw_json))
        raise

    configuration['name'] = store
    configuration['uuid'] = target_uuid
    configuration['items'] = items

    results = dict()
    results[target_uuid] = configuration

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
            if daemon_directory in specific:
                return load_daemon(store, specific)
            elif cache_directory in specific:
                return load_client(store, specific)
            else:
                raise ValueError('file is not within ' + base_directory)
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
            return load_daemon(store, daemon_filename)
        elif os.path.exists(cache_filename):
            return load_client(store, cache_filename)
        else:
            raise ValueError("file not found in %s: %s" % (base_directory, repr(specific)))



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
