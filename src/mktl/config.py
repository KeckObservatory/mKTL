
import hashlib
import os
import threading
import time
import uuid

from . import json
from . import protocol


_cache = dict()
_cache_lock = threading.Lock()


class Configuration:
    """ A convenience class to represent mKTL configuration data. To first
        order an instance acts like a dictionary, returning the configuration
        block for a single key at a time.
    """

    def __init__(self, store, alias=None):

        self.store = store.lower()
        self.alias = alias
        self.authoritative_uuid = None
        self.authoritative_block = None
        self.authoritative_items = None
        self._by_uuid = dict()
        self._by_key = dict()

        if store in _cache:
            raise ValueError('Configuration class is a singleton')

        try:
            self.load()
        except ValueError:
            pass


    def __contains__(self, key):
        return key in self._by_uuid or key in self._by_key


    def __getitem__(self, key):

        # This relies on the assumption that there will never be a key name
        # matching a UUID. This seems like a safe assumption...

        key = key.lower()

        try:
            item = self._by_key[key]
        except KeyError:
            pass
        else:
            return item

        try:
            block = self._by_uuid[key]
        except KeyError:
            pass
        else:
            return block

        raise KeyError('key not found: ' + str(key))


    def __len__(self):
        return len(self._by_uuid)


    def format(self, key, value):
        """ Translate the provided *value* according to the configuration of
            the item identified by the supplied *key*. For example, if the
            item is enumerated, this method will enable one-way mapping from
            integer values to representative strings; for example, 0 to 'Off',
            1 to 'On', etc.

            This is the inverse of :func:`unformat`.
        """

        item = self[key]

        try:
            type = item['type']
        except KeyError:
            return value

        if type == 'boolean' or type == 'enumerated':
            return self.format_enumerated(item, value)

        if type == 'mask':
            return self.format_mask(item, value)

        if type == 'numeric':
            try:
                item['format']
            except KeyError:
                return value
            else:
                return self.format_numeric(item, value)

        return value


    def format_enumerated(self, item, value):
        ### TODO
        return value


    def format_mask(self, item, value):
        ### TODO
        return value


    def format_numeric(self, item, value):
        ### This is just a stub. The format handling needs to be richer than
        ### this; there needs to be a way to convert between numeric types
        ### (radians to degrees), and to more exotic formats like sexagesimal.

        format = item['format']
        value = float(value)

        if 'd' in format:
            value = int(value)

        formatted = format % (value)

        return formatted


    def hashes(self):
        """ Retrieve known hashes for this store's known configuration blocks.
            The hashes are always returned as a dictionary, keyed by UUID for
            each configuration block.
        """

        hashes = dict()
        for uuid,block in self._by_uuid.items():
            hashes[uuid] = block['hash']

        return hashes


    def keys(self, authoritative=False):
        """ Return an iterable sequence of keys for the items represented in
            this configuration. If *authoritative* is set to True, only
            return the keys for locally authoritative items.
        """

        if authoritative == True:
            if self.authoritative_items is None:
                return ()
            else:
                return self.authoritative_items.keys()
        else:
            return tuple(self._by_key.keys())


    def load(self):
        """ Load the configuration from disk for this store, and alias,
            if provided.
        """

        base_dir = directory()

        if base_dir is None:
            raise RuntimeError('cannot determine location of mKTL configuration files')

        cache_dir = os.path.join(base_dir, 'client', 'cache', self.store)
        daemon_dir = os.path.join(base_dir, 'daemon', 'store', self.store)

        if self.alias:
            if os.path.exists(daemon_dir):
                pass
            else:
                os.makedirs(daemon_dir, mode=0o775)

            filename = os.path.join(daemon_dir, self.alias + '.json')

            block,uuid = self._load_daemon(filename)
            if block:
                self.update(block, save=False)
            else:
                self.authoritative_uuid = uuid

        if os.path.isdir(cache_dir):
            pass
        elif self.alias is None:
            raise ValueError('no locally stored configuration for ' + repr(self.store))

        filenames = list()

        # The contents of a store's cache directory will include a single file
        # for each UUID in the store. Load all such files.

        try:
            cache_dir_files = os.listdir(cache_dir)
        except FileNotFoundError:
            cache_dir_files = tuple()

        for cache_dir_file in cache_dir_files:
            filename = os.path.join(cache_dir, cache_dir_file)
            filenames.append(filename)

        for filename in filenames:
            loaded = self._load_client(filename)
            try:
                self.update(loaded, save=False)
            except ValueError:
                # update() removed the unwanted file.
                continue


    def _load_client(self, filename):
        """ Load a single client configuration file.
        """

        base_filename = filename[:-5]
        target_uuid = os.path.basename(base_filename)

        raw_json = open(filename, 'r').read()
        configuration = json.loads(raw_json)
        return configuration


    def _load_daemon(self, filename):
        """ Load a single daemon configuration file.
        """

        base_filename = filename[:-5]
        uuid_filename = base_filename + '.uuid'

        if os.path.exists(uuid_filename):
            target_uuid = open(uuid_filename, 'r').read()
            target_uuid = target_uuid.strip()
        else:
            target_uuid = str(uuid.uuid4())
            target_uuid = target_uuid.lower()
            writer = open(uuid_filename, 'w')
            writer.write(target_uuid)
            writer.close()

        try:
            raw_json = open(filename, 'r').read()
        except FileNotFoundError:
            configuration = None
        else:
            configuration = dict()

            configuration['store'] = self.store
            configuration['uuid'] = target_uuid
            configuration['items'] = json.loads(raw_json)

        return configuration,target_uuid


    def remove(self, uuid):
        """ Remove any/all cached information associated with the provided
            UUID, and remove any on-disk contents likewise belonging to that
            UUID.
        """

        # Remove the file, if it exists.
        remove(self.store, uuid)

        try:
            block = self._by_uuid[uuid]
        except KeyError:
            return

        items = block['items']

        for key in items.keys():
            del self._by_key[key]

        del self._by_uuid[uuid]


    def save(self):
        """ Save the contents of this :class:`Configuration` instance
            to the local disk cache for future client access.
        """

        for uuid,block in self._by_uuid.items():
            self._save_client(block)


    def _save_client(self, block):
        """ Save a configuration block to the cache directory.
        """

        store = self.store

        try:
            block_uuid = block['uuid']
        except KeyError:
            raise KeyError("the 'uuid' field must be present")

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

        raw_json = json.dumps(block)

        target_filename = os.path.join(cache_directory, json_filename)

        try:
            os.remove(target_filename)
        except FileNotFoundError:
            pass

        writer = open(target_filename, 'wb')
        writer.write(raw_json)
        writer.close()

        os.chmod(target_filename, 0o664)


    def unformat(self, key, value):
        """ Translate the provided *value* according to the configuration of
            the item identified by the supplied *key*. For example, if the
            item is enumerated, this method will enable one-way mapping from
            string values to integers; for example, 'Off' to 0, 'On' to 1, etc.

            This is the inverse of :func:`format`.
        """

        key = key.lower()
        pass


    def update(self, block, save=True):
        """ Update the locally cached configuration to include any/all contents
            in the provided *block*. A configuration block is a Python
            dictionary in the on-disk client format, minimally including the
            keys 'store', 'uuid', and 'items'.
        """

        store = block['store']
        items = block['items']
        uuid = block['uuid']

        if self.alias:
            try:
                alias = block['alias']
            except KeyError:
                pass
            else:
                if alias != self.alias:
                    raise ValueError('not ready to handle two aliases in a single daemon')
                if self.authoritative_uuid and self.authoritative_uuid != uuid:
                    raise ValueError('UUID in our authoritative block changed')

                self.authoritative_uuid = uuid
                self.authoritative_block = block
                self.authoritative_items = block['items']

        # Enforce case-insensitivity for keys. Doing this for every
        # configuration block may not be necessary, it should only be
        # necessary for blocks originating with a daemon.

        fixes = list()
        for key in items.keys():
            lower = key.lower()
            if key != lower:
                fixes.append(key)

        for key in fixes:
            lower = key.lower()
            item = items[key]
            del items[key]
            items[lower] = item

        try:
            block['hash']
        except KeyError:
            block['hash'] = generate_hash(items)


        # Done with pre-processing. Look for potential conflicts before
        # accepting this update. For example, there might be UUID mismatch
        # that needs to be cleared from the local cache.

        hash = block['hash']
        for known_uuid in self.uuids():
            if uuid == known_uuid:
                # Replacing the config block for the same UUID is fine.
                break

            collision = None

            # Check for hash collisions.

            known_block = self._by_uuid[known_uuid]
            known_hash = known_block['hash']
            if hash == known_hash:
                collision = 'hash collision'


            # Check for duplicate keys.

            if collision is None:
                known_items = known_block['items']
                for key in items.keys():
                    if key in known_items:
                        collision = 'duplicate key: ' + key
                        break

            if collision:
                # Keep the most recent block if a collision occured.

                try:
                    time = block['time']
                except KeyError:
                    time = 0

                try:
                    known_time = known_block['time']
                except KeyError:
                    # Maybe it doesn't make sense to give the first-seen
                    # block an edge in this case. It's not like the files
                    # on disk are stored in some significant order. But
                    # every configuration should have a timestamp, so the
                    # odds of reaching a condition where both configurations
                    # are missing their timestamp should be vanishingly low.
                    known_time = 1

                if time >= known_time:
                    # Get rid of the previous block, and process the newer one.
                    self.remove(known_uuid)
                else:
                    # Get rid of this block, and discontinue processing.
                    self.remove(uuid)
                    raise ValueError(collision + ', and this block is older')


        # Done with validity checks. The cache/save the block for future
        # reference.

        try:
            self._by_uuid[uuid].update(block)
        except KeyError:
            self._by_uuid[uuid] = block

        # Regenerate the by-key configuration cache, which is what gets
        # used by mktl.Item instances.

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

            self._by_key[key] = copied

        if save == True:
            self._save_client(block)


    def uuids(self, authoritative=False):
        """ Return an iterable sequence of UUIDs represented in this
            configuration. If *authoritative* is set to True, only
            return the authoritative UUID.
        """

        if authoritative == True:
            if self.authoritative_uuid:
                return (self.authoritative_uuid,)
            else:
                return tuple()
        else:
            return tuple(self._by_uuid.keys())


# end of class Configuration



def to_block(store, alias, uuid, items):
    """ Generate a block dictionary appropriate for the store, alias, uuid,
        and items provided. This is only relevant for a daemon, a client will
        always receive full blocks.
    """

    block = dict()
    block['store'] = store
    block['alias'] = alias
    block['uuid'] = uuid
    block['time'] = time.time()
    block['hash'] = generate_hash(items)
    block['items'] = items

    return block



def add_provenance(block, hostname, rep, pub=None):
    """ Add the provenance of this daemon to the supplied configuration
        block. The block is provided as a Python dictionary; the hostname
        and port definitions provide potential clients with enough information
        to initiate connections with further requests.

        The newly added provenance entry is returned for convenient access,
        though the provided configuration block will be modified to include
        the new entry.
    """

    try:
        existing_provenance = block['provenance']
    except KeyError:
        existing_provenance = list()
        block['provenance'] = existing_provenance

    def get_stratum(provenance):
        return provenance['stratum']

    existing_provenance.sort(key=get_stratum)

    # Stratum numbers must monotonically increase.

    try:
        last_provenance = existing_provenance[-1]
    except IndexError:
        stratum = 0
    else:
        stratum = last_provenance['stratum'] + 1

    new_provenance = create_provenance(stratum, hostname, rep, pub)
    existing_provenance.append(new_provenance)
    return new_provenance



def announce(config, uuid, override=False):
    """ Announce an authoritative configuration to the local network.
        Raise an exception if a conflict is detected. Setting *override*
        to True will request any/all available recipients update their
        local cache to clear any conflicting data.
    """

    store = config.store
    block = config[uuid]
    block = dict(block)

    if override == True:
        block['override'] = True

    payload = protocol.message.Payload(block)
    message = protocol.message.Request('CONFIG', store, payload)

    ### This needs to receive errors from the remote guides; should we rely
    ### on them to raise an exception, and we thus see it in the error response?
    ### Or should the 'announce' process be proactive, and search configs before
    ### putting them out there?

    ### There needs to be an option for additional flags: some way to force the
    ### receiving entity to clear its conflicting notions and adopt what we're
    ### providing. This 'force' attempt should fail if the conflicting daemon
    ### is still on the network.

    ### Leaning towards the handling being on the guide side.

    guides = protocol.discover.search(wait=True)

    for address,port in guides:
        try:
            payload = protocol.request.send(address, port, message)
        except zmq.error.ZMQError:
            continue

        error = payload.error
        if error is None or error == '':
            continue

        # The guide daemon will return errors for a variety of circumstances,
        # but in every case the immediate meaning is the same: do not proceed.

        e_type = error['type']
        e_text = error['text']

        ### This debug print should be removed.
        try:
            print(error['debug'])
        except KeyError:
            pass

        ### The exception type here could be something unique
        ### instead of a RuntimeError.
        raise RuntimeError("CONFIG announce failed: %s: %s" % (e_type, e_text))



def authoritative(store, alias, items):
    """ Declare an authoritative configuration block for use by a local
        authoritative daemon.
    """

    config = get(store, alias)
    block = to_block(store, alias, config.authoritative_uuid, items)
    config.update(block)



def contains_provenance(block, provenance):
    """ Does this configuration block contain this provenance? The stratum
        field of the provenance is ignored for this check.
    """

    try:
        full_provenance = block['provenance']
    except KeyError:
        full_provenance = list()
        block['provenance'] = full_provenance

    # A simple 'if provenence in full' won't get the job done, because
    # the stratum may not be set in the provided provenance.

    hostname = provenance['hostname']
    rep = provenance['rep']

    for known in full_provenance:
        if known['hostname'] == hostname and known['rep'] == rep:
            return True

    return False



def create_provenance(stratum, hostname, rep, pub=None):
    """ Create a new provenance entry.
    """

    provenance = dict()

    if stratum is None:
        pass
    else:
        provenance['stratum'] = stratum

    provenance['hostname'] = str(hostname)
    provenance['rep'] = int(rep)
    if pub is not None:
        provenance['pub'] = int(pub)

    return provenance



def directory(default=None):
    """ Return the directory location where we should be loading and/or saving
        configuration files. This defaults to ``$HOME/.mKTL``, but can be
        overridden by calling this method with a valid path, or by setting
        the ``MKTL_HOME`` environment variable. Note that changes to the
        environment variable will be ignored unless it is set prior to the
        first invocation of this method.
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



def get(store, alias=None):
    """ Retrieve the locally cached :class:`Configuration` instance for
        the specified *store*.
        A KeyError exception is raised if there are no locally cached
        configuration blocks for that store. A typical client will only
        interact with :func:`mktl.get`, which in turn calls this method.
    """

    store = store.lower()

    try:
        config = _cache[store]
    except KeyError:
        _cache_lock.acquire()

        try:
            config = _cache[store]
        except KeyError:
            config = Configuration(store, alias)
            _cache[store] = config
        finally:
            _cache_lock.release()

    if alias and config.alias is None:
        config.alias = alias

    elif alias and alias != config.alias:
        raise ValueError('not ready to handle two aliases in a single daemon')

    return config



def get_hashes(store=None):
    """ Retrieve known hashes for a store's cached configuration blocks. Return
        all known hashes if no *store* is specified. The hashes are always
        returned as a dictionary, keyed first by store name, then by UUID for
        the associated configuration block.
    """

    hashes = dict()
    requested_store = store

    if store is None:
        stores = _cache.keys()
    else:
        stores = (store,)

    for store in stores:
        config = get(store)
        config_hashes = config.hashes()

        if len(config_hashes) > 0:
            hashes[store] = config_hashes

    if requested_store and len(hashes) == 0:
        raise KeyError('no local configuration for ' + repr(requested_store))

    return hashes



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
        # stratum, hostname, rep, and pub (if present).

        if provenance1 != provenance2:
            return False

        matched = True
        index += 1



def remove(store, uuid):
    """ Remove the cache file associated with this store name and UUID.
        Takes no action and throws no errors if the file does not exist.
    """

    base_directory = directory()
    json_filename = uuid + '.json'

    cache_directory = os.path.join(base_directory, 'client', 'cache', store)
    target_filename = os.path.join(cache_directory, json_filename)

    try:
        os.remove(target_filename)
    except FileNotFoundError:
        pass


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
