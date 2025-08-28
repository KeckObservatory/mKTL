
import hashlib
import os
import uuid

from . import json


_cache_by_key = dict()
_cache_by_uuid = dict()
_hashes = dict()

py_list = list


def add(store, data, persist=True):
    """ Add a configuration block to the local cache. The *store* name is
        a simple string; *data* can either be a bare configuration block,
        or a dictionary of uuid-keyed configuration blocks. If *persist* is
        set to True any additions will be written back out to the local
        cache on disk.
    """

    try:
        blocks = _cache_by_uuid[store]
    except KeyError:
        blocks = dict()
        _cache_by_uuid[store] = blocks

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
            block['hash'] = generate_hash(block['items'])


    # The update() call will replace any matching UUID keys with new blocks,
    # or add them if the UUID is unique.

    blocks.update(data)

    ## What about duplicate keys? Or is something upstream in the configuration
    ## handling chain handling that before this method gets called?

    _rebuild(store)
    if persist == True:
        save(store, blocks)



def add_provenance(block, hostname, req, pub=None):
    """ Add the provenance of this daemon to the supplied configuration
        block. The block is provided as a Python dictionary; the hostname
        and port definitions provide potential clients with enough information
        to initiate connections with further requests.

        The newly added provenance stratum is returned for convenient access,
        though the provided configuration block has already been modified to
        include the new stratum.
    """

    try:
        full_provenance = block['provenance']
    except KeyError:
        full_provenance = py_list()
        block['provenance'] = full_provenance

    stratum = -1
    for provenance in full_provenance:
        if provenance['stratum'] > stratum:
            stratum = provenance['stratum']

    provenance = create(stratum + 1, hostname, req, pub)

    block['provenance'].append(provenance)
    return provenance



def contains_provenance(block, provenance):
    """ Does this configuration block contain this provenance? The stratum
        field of the provenance is ignored for this check.
    """

    try:
        full_provenance = block['provenance']
    except KeyError:
        full_provenance = py_list()
        block['provenance'] = full_provenance

    # A simple 'if provenence in full' won't get the job done, because
    # the stratum may not be set in the provided provenance.

    hostname = provenance['hostname']
    req = provenance['req']

    for known in full_provenance:
        if known['hostname'] == hostname and known['req'] == req:
            return True

    return False



def create_provenance(stratum, hostname, req, pub=None):
    """ Create a provenance entry, which is a dictionary.
    """

    provenance = dict()

    if stratum is None:
        pass
    else:
        provenance['stratum'] = stratum

    provenance['hostname'] = str(hostname)
    provenance['req'] = int(req)
    if pub is not None:
        provenance['pub'] = int(pub)

    return provenance



def directory(default=None):
    """ Return the directory location where we should be loading and/or saving
        configuration files. This defaults to ``$HOME/.mKTL``, but can be
        overridden by calling this method with a valid path, or by setting
        the ``MKTL_HOME`` environment variable. Note that changes to the
        environment variable will be ignored unless it is set prior to calling
        this method.
    """

    if default is not None:
        default = str(default)
        default = os.path.expandvars(default)

        if os.path.isabs(default):
            pass
        else:
            raise ValueError('the default directory must be an absolute path')

        if os.path.exists(default):
            pass
        else:
            os.makedirs(default, mode=0o775)

        os.environ['MKTL_HOME'] = default
        directory.found = default


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
        raise RuntimeError('MKTL_HOME and HOME environment variables not set, cannot determine mKTL configuration directory')

    found = os.path.join(home, '.mKTL')

    directory.found = found
    return found

directory.found = None



def generate_hash(dumpable):
    """ Convert the supplied Python list or dictionary to JSON, hash the
        results, and return the hash. The mKTL protocol description limits
        the hash to 32 hexadecimal integers, but the specific hash type is
        unspecified, and allowed to vary between implementations-- as long
        as it is consistent.
    """

    raw_json = json.dumps(dumpable)

    hash = hashlib.shake_256(raw_json)
    hash = int(hash.hexdigest(16), 16)
    return hash



def get(store=None, by_uuid=True, by_key=False, hashes=False):
    """ Retrieve the locally cached configuration for a given *store*.
        A KeyError exception is raised if there are no locally cached
        configuration blocks for that store. A typical client will only
        interact with :func:`mktl.get`, which in turn calls this method.

        The *by_uuid*, *by_key*, and *hashes* arguments indicate which
        type of dictionary is being requested: configuration blocks keyed
        by UUID, per-item configurations keyed by the item key, or hashes
        of configuration blocks, also keyed by UUID.
    """

    if store is None and hashes == False:
        raise RuntimeError('must specify a store name')

    if hashes == True:
        return get_hashes(store)

    if by_key == True:
        try:
            cached = _cache_by_key[store]
        except KeyError:
            cached = dict()
            _cache_by_key[store] = cached

    elif by_uuid == True:
        try:
            cached = _cache_by_uuid[store]
        except KeyError:
            cached = dict()
            _cache_by_uuid[store] = cached

    else:
        raise RuntimeError('must request one of by_uuid, by_key, or hashes')

    if len(cached) == 0:
        raise KeyError('no local configuration for ' + repr(store))

    return cached



def get_hashes(store=None):
    """ Retrieve known hashes for a store's cached configuration blocks. Return
        all known hashes if no *store* is specified. The hashes are always
        returned as a dictionary, keyed first by store name, then by UUID for
        the associated configuration block.
    """

    if store is None:
        hashes = _hashes
    else:
        try:
            hashes = _hashes[store]
        except KeyError:
            raise KeyError('no local configuration for ' + repr(store))

    return dict(hashes)



def list():
    """ Return a list of all store names present in the local cache.
    """

    names = _cache_by_uuid.keys()
    results = py_list()

    for name in names:
        blocks = _cache_by_uuid[name]
        if len(blocks) > 0:
            results.append(name)

    return results



def load(store, specific=None):
    """ Load the configuration from disk for the specified store name. If
        *specific* is not None it is expected to be the unique string
        corresponding to a single configuration file, either a unique string
        of the caller's choice for a locally authoritative configuration (the
        'alias'), or the UUID for a cached file. Results are returned as a
        dictionary, keyed by the UUID, and the configuration contents as the
        value. The returned contents already translated from JSON.
    """

    store = store.lower()

    if specific is not None:
        return _load_one(store, specific)

    base_directory = directory()

    if base_directory is None:
        raise RuntimeError('cannot determine location of mKTL configuration files')


    # The daemon context will know what it is looking for and provide a
    # 'specific' argument, and get caught by the condition above. The remainder
    # of this method will ignore the daemon directory.

    cache_directory = os.path.join(base_directory, 'client', 'cache', store)

    if os.path.isdir(cache_directory):
        pass
    else:
        raise ValueError('no locally stored configuration for ' + repr(store))

    filenames = py_list()

    # The contents of a store's cache directory will include a single file
    # for each UUID in the store. Load all such files and return them.

    try:
        cache_directory_files = os.listdir(cache_directory)
    except FileNotFoundError:
        cache_directory_files = tuple()

    for cache_directory_file in cache_directory_files:
        filename = os.path.join(cache_directory, cache_directory_file)
        filenames.append(filename)


    results = dict()
    for filename in filenames:
        loaded = _load_one(store, filename)
        new_uuid = py_list(loaded.keys())[0]
        results.update(loaded)

    return results



def _load_client(store, filename):
    """ Load a single client configuration file; this method is called by
        :func:`_load_one` as a final processing step.
    """

    base_filename = filename[:-5]
    target_uuid = os.path.basename(base_filename)

    raw_json = open(filename, 'r').read()
    configuration = json.loads(raw_json)
    configuration['uuid'] = target_uuid

    results = dict()
    results[target_uuid] = configuration

    return results



def _load_daemon(store, filename):
    """ Load a single daemon configuration file; this method is called by
        :func:`_load_one` as a final processing step.
    """

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
    items = json.loads(raw_json)

    configuration['name'] = store
    configuration['uuid'] = target_uuid
    configuration['items'] = items

    results = dict()
    results[target_uuid] = configuration

    return results



def _load_one(store, specific):
    """ Similar to :func:`load`, except only ingesting a single file. A lot of
        checks will be bypassed if *specific* is provided as an absolute path;
        it is assumed the caller knows exactly which file they want, and have
        provided the full and correct path.
    """

    store = store.lower()

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
                return _load_daemon(store, specific)
            elif cache_directory in specific:
                return _load_client(store, specific)
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
            return _load_daemon(store, daemon_filename)
        elif os.path.exists(cache_filename):
            return _load_client(store, cache_filename)
        else:
            raise ValueError("file not found in %s: %s" % (base_directory, repr(specific)))



def match_provenance(full_provenance1, full_provenance2):
    """ Check the two provided provenance lists, and return True if they match.
        This check allows for one provenance to be longer than the other; if
        they are aligned from stratum 0 up to the full length of the shorter
        provenance, that is considered a match.
    """

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
        # stratum, hostname, req, and pub (if present).

        if provenance1 != provenance2:
            return False

        matched = True
        index += 1



def _rebuild(store):
    """ Rebuild any/all secondary caches for the specified *store*.
    """

    config = get(store)
    uuids = config.keys()
    by_key = dict()

    for uuid in uuids:
        # Cache the reported hash of each configuration block. No attempt
        # is made to verify the hash.

        block = config[uuid]
        hash = block['hash']

        try:
            cached = _hashes[store]
        except KeyError:
            cached = dict()
            _hashes[store] = cached

        cached[uuid] = hash

        # Enforce case-insensitivity.

        items = block['items']
        for key in items.keys():
            lower = key.lower()
            if key != lower:
                item = items[key]
                del items[key]
                items[lower] = item

        # Regenerate the by-key configuration cache, which is what gets
        # used by mktl.Item instances.

        items = block['items']
        for key in items.keys():
            item = items[key]

            # A fresh dictionary is made here so we don't modify what's stored
            # in the Cache, which is supposed to be representative of the
            # on-the-wire representation. We want the daemon's UUID and
            # provenance to be present in the per-item configuration for use
            # within the Item class.

            copied = dict(item)
            copied['uuid'] = uuid

            try:
                ### Should this also be a copy?
                copied['provenance'] = block['provenance']
            except KeyError:
                pass

            by_key[key] = copied

    _cache_by_key[store] = by_key



def remove(store, uuid):
    """ Remove the cache file associated with this store name and UUID.
        Takes no action and throws no errors if the file does not exist.
    """

    base_directory = directory()
    json_filename = uuid + '.json'

    cache_directory = os.path.join(base_directory, 'client', 'cache', name)
    target_filename = os.path.join(cache_directory, json_filename)

    try:
        os.remove(target_filename)
    except FileNotFoundError:
        pass



def _remove_cache(store, data, cleanup=True):
    """ Remove a configuration block from the local cache. Matches are
        determined via UUID.
    """

    try:
        blocks = _cache_by_uuid[store]
    except KeyError:
        raise KeyError('no local configuration for ' + repr(store))

    target_uuid = data['uuid']

    try:
        del(blocks[target_uuid])
    except KeyError:
        raise KeyError('no matching block for UUID ' + repr(target_uuid))

    if cleanup == True:
        remove(store, target_uuid)
        _rebuild(store)



def save(store, configuration, alias=None):
    """ Save a configuration block to the cache directory. If the *alias*
        argument is set this method will instead save the configuration block
        to the daemon directory, using *alias* as the base for the filename.
    """

    if alias is None:
        _save_client(store, configuration)
    else:
        _save_daemon(store, configuration, alias)



def _save_client(store, configuration):
    """ Save a configuration block to the cache directory.
    """

    try:
        configuration['name']
    except KeyError:
        # Assume this is a dictionary of configuration blocks, as you might
        # get() would return by default.
        for uuid in configuration.keys():
            block = configuration[uuid]
            save(store, block)
        return

    try:
        block_uuid = configuration['uuid']
    except KeyError:
        raise KeyError("the 'uuid' field must be in each configuration block")

    base_directory = directory()
    base_filename = block_uuid
    json_filename = base_filename + '.json'

    cache_directory = os.path.join(base_directory, 'client', 'cache', store)

    if os.path.exists(cache_directory):
        pass
    else:
        os.makedirs(cache_directory, mode=0o775)

    if os.access(cache_directory, os.W_OK) != True:
        raise OSError('cannot write to cache directory: ' + cache_directory)

    raw_json = json.dumps(configuration)

    target_filename = os.path.join(cache_directory, json_filename)

    try:
        os.remove(target_filename)
    except FileNotFoundError:
        pass

    writer = open(target_filename, 'wb')
    writer.write(raw_json)
    writer.close()

    os.chmod(target_filename, 0o664)



def _save_daemon(store, configuration, alias):
    """ Save a configuration block to the daemon directory. This is only
        relevant if a daemon is generating its configuration at runtime,
        or as an entry point for external tools that generate the configuration
        contents and want it stored in the correct location.

        The *configuration* should be a dictionary of items, matching the
        expected structure of the daemon-side configuration contents.
    """

    base_directory = directory()
    json_filename = alias + '.json'

    daemon_directory = os.path.join(base_directory, 'daemon', 'store', store)

    if os.path.exists(daemon_directory):
        pass
    else:
        os.makedirs(daemon_directory, mode=0o775)

    if os.access(daemon_directory, os.W_OK) != True:
        raise OSError('cannot write to daemon directory: ' + daemon_directory)

    raw_json = json.dumps(configuration)

    target_filename = os.path.join(daemon_directory, json_filename)

    try:
        os.remove(target_filename)
    except FileNotFoundError:
        pass

    writer = open(target_filename, 'wb')
    writer.write(raw_json)
    writer.close()

    os.chmod(target_filename, 0o664)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
