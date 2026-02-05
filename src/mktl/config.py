
import hashlib
import os
import sys
import threading
import time
import uuid

# Importing pint is expensive, representing something like 30% of the
# user runtime for a simple mKTL command. It will be imported on a
# just-in-time basis for unit conversions. If it's already imported
# there's no need for this extra handling.

if 'pint' in sys.modules:
    import pint
else:
    pint = None

from . import json
from . import protocol


_cache = dict()
_cache_lock = threading.Lock()


class Configuration:
    """ A convenience class to represent mKTL configuration data. To first
        order an instance acts like a dictionary, returning the configuration
        for a single key, or the full configuration block for a single UUID or
        unique alias.

        In addition to acting as a repository for the description of all items,
        the Configuration instance also provides translation routines for some
        item values; the behavior of these translations is fully driven by the
        configuration, and does not depend on custom :class:`mktl.Item`
        subclasses.
    """

    def __init__(self, store, alias=None):

        self.store = store.lower()
        self.alias = alias
        self.authoritative_uuid = None
        self.authoritative_block = None
        self.authoritative_items = None
        self._by_uuid = dict()
        self._by_alias = dict()
        self._by_key = dict()

        if store in _cache:
            raise ValueError('Configuration class is a singleton')

        if pint is None:
            self._unit_registry = None
            self.convert_units = self._convert_units_setup
        else:
            # Conversion setup is fast if the pint module is already imported.
            # Might as well get it out of the way.
            self._convert_units_setup()

        try:
            self.load()
        except ValueError:
            pass


    def __contains__(self, key):
        return key in self._by_uuid or key in self._by_alias or key in self._by_key


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

        try:
            block = self._by_alias[key]
        except KeyError:
            pass
        else:
            return block

        raise KeyError('key not found: ' + str(key))


    def __len__(self):
        return len(self._by_uuid)


    def _convert_units_setup(self, *args, **kwargs):
        """ The pre-requisites for unit conversion are not part of the
            standard library, nor are they inexpensive to import. Only
            import them when actively being used.
        """

        global pint
        import pint

        self._unit_registry = pint.UnitRegistry()
        self.convert_units = self._convert_units

        if args or kwargs:
            return self._convert_units(*args, **kwargs)


    def _convert_units(self, value, old, new):
        """ Use the :mod:`pint` module to convert the provided *value* from
            *old* units to *new* units. The value as a :class:`pint.Quantity`
            instance will be returned if *new* is set to None.
        """

        old = self._unit_registry.parse_units(old)
        quantity = value * old

        if new is None:
            return quantity

        new = self._unit_registry.parse_units(new)
        converted = quantity.to(new)
        return converted.magnitude


    convert_units = _convert_units


    def from_format(self, key, value):
        """ Translate the provided *value* according to the configuration of
            the item identified by the supplied *key*. For example, if the
            item is enumerated, this method will enable one-way mapping from
            string values to integers; for example, 'Off' to 0, 'On' to 1, etc.

            This is the inverse of :func:`to_format`.
        """

        item_config = self[key]
        unformatted = None

        try:
            type = item_config['type']
        except KeyError:
            type = None

        if type == 'boolean' or type == 'enumerated':
            unformatted = self.from_format_enumerated(key, value)

        elif type == 'mask':
            unformatted = self.from_format_mask(key, value)

        elif type == 'numeric':
            unformatted = self.from_format_numeric(key, value)

        if unformatted is None:
            return value
        else:
            return unformatted


    def from_format_enumerated(self, key, value):
        """ Return the integer representation corresponding to the specified
            formatted string value. Raise a KeyError if there is no matching
            enumerator. This comparison will be done in a case-insensitive
            fashion.
        """

        item_config = self[key]
        value = str(value)
        value = value.lower()
        enumerators = item_config['enumerators']

        unformatted = None

        # The mapping between keys and names could be established in advance
        # to make this linear search unnecesary, enabling the use of a
        # dictionary lookup instead. If there was a sensible place to store
        # a derived mapping, perhaps it could be generated on a just-in-time
        # basis.

        for key,name in enumerators.items():
            name = name.lower()
            if value == name:
                key = int(key)
                unformatted = key
                break

        if unformatted is None:
            raise KeyError('invalid enumerator: ' + repr(value))

        return unformatted


    def from_format_mask(self, key, value):
        """ Return the integer representation for a comma-separated set of
            active mask bits. The comparison will be done on a case-insensitive
            basis.
        """

        item_config = self[key]
        value = str(value)
        value = value.lower()

        if value == '' or value == 'none':
            return 0

        enumerators = item_config['enumerators']
        lowered = dict()

        for bit,name in enumerators.items():
            if bit == 'None':
                continue

            name = name.lower()
            bit = int(bit)
            bit_value = 1 << bit
            lowered[name] = bit_value

        unformatted = 0
        bit_names = value.split(',')

        for name in bit_names:
            name = name.strip()
            name = name.lower()

            try:
                bit_value = lowered[name]
            except KeyError:
                raise KeyError('invalid bit name in mask value: ' + repr(name))

            unformatted = unformatted | bit_value

        return unformatted


    def from_format_numeric(self, key, value):
        """ Return a Python-native number (either integer or floating point)
            after undoing the configured formatting for this numeric value.
            This includes converting the number to the units specific to the
            unformatted value.
        """

        item_config = self[key]

        try:
            format = item_config['format']
        except KeyError:
            format = '%s'

        if ':' in format:
            unformatted = self.from_format_sexagesimal(key, value)
        else:
            # An integer is preferred whenever an integer is appropriate.

            if isinstance(value, int):
                pass
            elif isinstance(value, str):
                try:
                    value = int(value)
                except:
                    value = float(value)
            else:
                value = float(value)

            unformatted = self.from_format_units(key, value)

        return unformatted


    def from_format_sexagesimal(self, key, value):
        """ Convert a numeric value from a sexagesimal representation to
            a numeric value corresponding to the unformatted units. Both
            hours-minutes-seconds and degrees-minutes-seconds representations
            are handled.
        """

        item_config = self[key]

        try:
            units = item_config['units']
        except KeyError:
            return value

        try:
            formatted = units['formatted']
            unformatted = units['']
        except (TypeError, KeyError):
            return value

        value = str(value)
        fields = value.split(':')

        result = 0
        exponent = 0

        first = float(fields[0])
        if first < 0:
            negative = True
            fields[0] = abs(first)
        else:
            negative = False

        for field in fields:
            field = float(field)
            contribution = field / (60 ** exponent)
            exponent += 1
            result += contribution

        if negative:
            result = -result

        degrees = set(('d', 'deg', 'degs', 'degree', 'degrees'))
        hours = set(('h', 'hour', 'hours'))

        formatted = formatted.lower()

        if formatted in degrees:
            pass
        elif formatted in hours:
            result = result * 360 / 24
        else:
            raise ValueError('unrecognized target units: ' + formatted)

        if pint is None:
            self._convert_units_setup()

        degrees = self._unit_registry.parse_units('degrees')
        quantity = result * degrees
        unformatted = self.from_quantity(key, quantity)
        return unformatted


    def from_format_units(self, key, value):
        """ Convert a numeric value from its formatted units to the unformatted
            units.
        """

        item_config = self[key]

        try:
            units = item_config['units']
        except KeyError:
            return value

        try:
            formatted = units['formatted']
        except (KeyError, TypeError):
            return value

        unformatted = units['']

        if formatted == unformatted:
            return value
        else:
            return self.convert_units(value, formatted, unformatted)


    def from_quantity(self, key, quantity):
        """ Translate the provided :class:`pint.Quantity` instance to the
            unformatted representation appropriate for the item identified
            by the supplied *key*. This is only relevant for numeric types
            that have defined units; a TypeError exception will be raised
            for items that do not have units.
        """

        item_config = self[key]

        try:
            units = item_config['units']
        except:
            units = None
        else:
            try:
                unformatted = units['']
            except (TypeError, KeyError):
                pass
            else:
                units = unformatted

        if units is None:
            raise TypeError('item ' + repr(key) + ' does not have units')


        if pint is None:
            self._convert_units_setup()

        units = self._unit_registry.parse_units(units)
        converted = quantity.to(units)
        return converted.magnitude


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
            return the keys for locally authoritative items; any keys with
            a leading underscore (built-in items) will be omitted from the
            reported authoritative set.
        """

        if authoritative == True:
            if self.authoritative_items is None:
                return tuple()
            else:
                keys = list()
                for key in self.authoritative_items.keys():
                    if key[0] != '_':
                        keys.append(key)
                return keys
        else:
            return self._by_key.keys()


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


    def _reject_units(self, *args, **kwargs):
        """ The 'pint' Python module is required in order to translate between
            units.
        """

        raise ImportError('pint module not available')


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

        alias = block['alias']
        items = block['items']

        for key in items.keys():
            del self._by_key[key]

        del self._by_alias[alias]
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


    def to_format(self, key, value):
        """ Translate the provided *value* according to the configuration of
            the item identified by the supplied *key*. For example, if the
            item is enumerated, this method will enable one-way mapping from
            integer values to representative strings; for example, 0 to 'Off',
            1 to 'On', etc.

            This is the inverse of :func:`from_format`.
        """

        item_config = self[key]
        formatted = None

        try:
            type = item_config['type']
        except KeyError:
            type = None

        if type == 'boolean' or type == 'enumerated':
            formatted = self.to_format_enumerated(key, value)

        elif type == 'mask':
            formatted = self.to_format_mask(key, value)

        elif type == 'numeric':
            formatted = self.to_format_numeric(key, value)

        if formatted is None:
            return str(value)
        else:
            return formatted


    def to_format_enumerated(self, key, value):
        """ Return the string representation corresponding to the specified
            integer value. Return the original value, potentially after being
            cast to a string, if there is no matching enumerator.
        """

        item_config = self[key]
        enumerators = item_config['enumerators']

        # The JSON representation of the enumerators has the integer keys as
        # strings. For example:

        # {"0": "No", "1": "Yes", "2": "Unknown"}

        value = str(value)

        try:
            formatted = enumerators[value]
        except KeyError:
            formatted = value

        return formatted


    def to_format_mask(self, key, value):
        """ Return a comma-separated list of active bits for the specified
            integer value. If no bits are active, return the string representing
            no bits being set.
        """

        item_config = self[key]
        enumerators = item_config['enumerators']

        # Similar to the enumerated case, the mask bits are defined in the
        # JSON as strings. But we have to treat the unformmatted value as
        # an intger in order to do bit-wise operations. The expected value
        # when none of the bits are active is represented by the 'None' key.
        # For example:

        # {"None": "OK", "0": "Timeout", "1": "Error", "2": "Warning"}

        value = int(value)
        formatted = list()

        for bit,name in enumerators.items():
            if bit == 'None':
                continue

            bit = int(bit)
            bit_value = 1 << bit
            if value & bit_value:
                formatted.append(name)

        if len(formatted) == 0:
            try:
                formatted = enumerators['None']
            except KeyError:
                formatted = ''
        else:
            formatted = ', '.join(formatted)

        return formatted


    def to_format_numeric(self, key, value):
        """ Return a string representing the configured formatting for this
            numeric value. This includes any printf-style directives about
            decimal places and/or padding, as well as converting the number
            to the units specific to the formatted value.
        """

        item_config = self[key]

        if isinstance(value, int):
            pass
        else:
            value = float(value)

        try:
            format = item_config['format']
        except KeyError:
            format = '%s'

        if ':' in format:
            formatted = self.to_format_sexagesimal(key, value)
        else:
            value = self.to_format_units(key, value)

            if 'd' in format:
                # Eliminate floating point uncertainty by rounding. Reporting
                # 34 if the value is 34.999999 is not desirable.
                value = int(value + 0.5)

            formatted = format % (value)

        return formatted


    def to_format_sexagesimal(self, key, value):
        """ Convert a numeric value from its unformatted units to a sexagesimal
            representation. Both hours-minutes-seconds and
            degrees-minutes-seconds representations are handled.
        """

        item_config = self[key]

        try:
            units = item_config['units']
        except KeyError:
            return str(value)

        try:
            formatted = units['formatted']
            unformatted = units['']
        except (TypeError, KeyError):
            return str(value)

        value = float(value)

        if value < 0:
            negative = True
        else:
            negative = False

        degrees = set(('d', 'deg', 'degs', 'degree', 'degrees'))
        hours = set(('h', 'hour', 'hours'))

        quantity = self.to_quantity(key, value)
        value = quantity.to('degrees').magnitude

        formatted = formatted.lower()
        format = item_config['format']
        fields = format.split(':')

        values = list()

        if formatted in degrees:
            pass
        elif formatted in hours:
            value = value * 24 / 360
        else:
            raise ValueError('unrecognized target units: ' + formatted)

        if value < 0:
            remainder = value % -1
        elif value > 0:
            remainder = value % 1
        else:
            remainder = 0

        values.append(value)

        for field in fields[1:]:
            value = remainder * 60
            if value < 0:
                remainder = value % -1
            elif value > 0:
                remainder = value % 1
            else:
                value = 0
            values.append(abs(value))

        remainder = abs(remainder)
        if remainder < 1.000001 and remainder > 0.999999 and len(fields) == 3:
            # Possible floating point underflow.

            if values[2] > 59.999:
                values[2] = 0
                values[1] += 1/60

                if values[1] >= 60:
                    values[1] = 0
                    if negative:
                        values[0] -= 1/60
                    else:
                        values[0] += 1/60

        results = list()
        for index in range(len(fields)):
            results.append(fields[index] % (values[index]))

        if negative:
            if results[0][0] != '-':
                results[0] = '-' + results[0].strip()

        return ':'.join(results)


    def to_format_units(self, key, value):
        """ Convert a numeric value from its unformatted units to the formatted
            units.
        """

        item_config = self[key]

        try:
            units = item_config['units']
        except KeyError:
            return value

        # Defining the 'formatted' units requires representing the units
        # as a dictionary with both '' and 'formatted' as keys. A simple
        # string representation of the units implies no additional unit
        # specific formatting is available.

        try:
            formatted = units['formatted']
        except (TypeError, KeyError):
            return value

        try:
            unformatted = units['']
        except KeyError:
            raise KeyError('unformatted units are not defined for ' + key)

        if formatted == unformatted:
            return value
        else:
            return self.convert_units(value, unformatted, formatted)


    def to_quantity(self, key, value, units=None):
        """ Translate the provided *value* according to the configuraton of
            the item identified by the supplied *key* to a
            :class:`pint.Quantity` instance. This is only relevant for numeric
            types that have defined units; a TypeError exception will be raised
            for items that do not have units. The returned quantity will
            be translated to the specified *units*, if any, otherwise the
            default 'unformatted' units are used.
        """

        item_config = self[key]

        try:
            default = item_config['units']
        except:
            default = None

        if default is not None:
            try:
                default = default['']
            except (TypeError, KeyError):
                try:
                    default = default['formatted']
                except (TypeError, KeyError):
                    pass

        if default is None:
            default = 'dimensionless'

        quantity = self.convert_units(value, default, None)

        if units:
            quantity = quantity.to(units)

        return quantity


    def update(self, block, save=True):
        """ Update the locally cached configuration to include any/all contents
            in the provided *block*. A configuration block is a Python
            dictionary in the on-disk client format, minimally including the
            keys 'store', 'uuid', and 'items'.
        """

        store = block['store']
        alias = block['alias']
        items = block['items']
        uuid = block['uuid']

        if self.alias:
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

        # Allow for the possibility that a boolean item does not include
        # enumerators in its description. This check is only necessary
        # for authoritative blocks.

        if uuid == self.authoritative_uuid:
            for key in items.keys():
                item_config = items[key]

                try:
                    type = item_config['type']
                except KeyError:
                    continue

                if type == 'boolean':
                    try:
                        enumerators = item_config['enumerators']
                    except KeyError:
                        enumerators = dict()
                        item_config['enumerators'] = enumerators

                    try:
                        enumerators['0']
                    except:
                        enumerators['0'] = 'False'

                    try:
                        enumerators['1']
                    except:
                        enumerators['1'] = 'True'


        # It's possible the contents of the local authoritative block changed.
        # Update the hash and configuration timestamp if that is the case.

        if uuid == self.authoritative_uuid:
            new_hash = generate_hash(items)

            try:
                old_hash = block['hash']
            except KeyError:
                old_hash = None

            if old_hash != new_hash:
                block['hash'] = new_hash
                block['time'] = time.time()

        else:
            # The block should always have a hash; provide one if, for some
            # unknown reason, it is not already present.

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
                    new_time = block['time']
                except KeyError:
                    new_time = 0

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

                if new_time >= known_time:
                    # Get rid of the previous block, and process the newer one.
                    self.remove(known_uuid)
                else:
                    # Get rid of this block, and discontinue processing.
                    self.remove(uuid)
                    raise ValueError(collision + " in store %s, and this block is older" % (store))


        # Done with validity checks. The cache/save the block for future
        # reference.

        try:
            self._by_uuid[uuid].update(block)
        except KeyError:
            self._by_uuid[uuid] = block

        try:
            self._by_alias[alias].update(block)
        except KeyError:
            self._by_alias[alias] = block

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

    brokers = protocol.discover.search(wait=True)

    for address,port in brokers:
        try:
            payload = protocol.request.send(address, port, message)
        except TimeoutError:
            continue

        error = payload.error
        if error is None or error == '':
            continue

        # The broker daemon will return errors for a variety of circumstances,
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
        authoritative daemon. This is the expected entry point for a daemon
        that generates or otherwise provides its own JSON configuration via
        custom routines.
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

    if store == '':
        raise ValueError('store name cannot be the empty string')

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
