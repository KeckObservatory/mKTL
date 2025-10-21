""" This is an implementation of a KTL proxy, enabling full mKTL commands
    to a KTL service.
"""

import ktl
import mktl


class Daemon(mktl.Daemon):

    def __init__(self, name, *args, **kwargs):

        # Generate the configuration matching this KTL service. The base
        # Daemon.Store will want to know where it can be loaded from, and
        # it is always loading from a location on disk-- so we need to save
        # it first. This bit of indirection is only necessary because we
        # are generating the configuration at runtime.

        items = describeService(name)
        mktl.config.save(name, items, name)
        mktl.Daemon.__init__(self, name, name)


    def setup(self):

        config = self.config[self.uuid]
        items = config['items']
        keys = items.keys()

        for key in keys:
            self.add_item(Item, key)


    def setup_final(self):
        """ This is the last step before broadcasts go out. This is the
            right time to fire up monitoring of all KTL keywords.
        """

        service = ktl.cache(self.store.name)

        for keyword in service:

            if keyword['broadcasts'] == True:
                keyword.callback(self.relay)
                keyword.monitor(wait=False)


    def relay(self, keyword):

        try:
            slice = keyword.history[-1]
        except IndexError:
            return

        timestamp = slice.time
        ascii = slice.ascii
        binary = slice.binary

        key = keyword.name
        item = self.store[key]
        item.publish(binary, timestamp=timestamp)


# end of class Store



class Item(mktl.Item):

    def perform_get(self):

        keyword = ktl.cache(self.full_key)
        keyword.read()

        slice = keyword.history[-1]
        timestamp = slice.time
        binary = slice.binary

        payload = mktl.Payload(binary, timestamp)
        return payload


    def perform_set(self, new_value):

        keyword = self.full_key
        keyword = ktl.cache(keyword)
        keyword.write(new_value)


# end of class Item



def describeService(name):
    service = ktl.cache(name)

    keywords = dict()
    for keyword in service:
        # The KTL.Service iterates in alphabetical order, there is no need
        # for additional sorting in order for it to be predictable and/or
        # repeatable.
        keyword_dict = describeKeyword(keyword)
        keywords[keyword.name] = keyword_dict

    return keywords


def describeKeyword(keyword):
    keyword_dict = dict()

    type = keyword['type']
    type = type_mapping[type]
    keyword_dict['type'] = type

    try:
        enumerators = keyword['enumerators']
    except ValueError:
        enumerators = None
    else:
        rebuilt = dict()
        if type == 'mask':
           rebuilt['None'] = enumerators[0]
           enumerators = enumerators[1:]
        for key in range(len(enumerators)):
            enumerator = enumerators[key]
            if enumerator == '':
                continue
            else:
                rebuilt[key] = enumerator

        enumerators = rebuilt

    for attribute in ('units', 'range', 'help'):
        try:
            value = keyword[attribute]
        except ValueError:
            value = None

        if attribute == 'units' and enumerators is not None:
            # Keywords with enumerators overload the 'units' string in order
            # to provide the enumerators. Including the 0th enumerator again
            # here would be a mistake.
            value = None

        if value is not None:
            if attribute == 'help':
                attribute = 'description'

            if attribute == 'units':
                more_units = keyword.ktlc.units()
                binary_units = None

                if len(more_units) > 1:
                    # The fields are:
                    # 0: ascii units
                    # 1: empty string
                    # 2: printf format (asc:bin)
                    # 3: binary units

                    try:
                        binary_units = more_units[3]
                    except IndexError:
                        pass
                    else:
                        binary_units = binary_units.strip()
                        if binary_units == '':
                            binary_units = None

                if binary_units is not None:
                    units = dict()
                    units['formatted'] = value
                    units['base'] = binary_units

                    value = units

            keyword_dict[attribute] = value

    for attribute in ('broadcasts', 'reads', 'writes'):
        try:
            value = keyword[attribute]
        except ValueError:
            value = None

        if value is False:
            keyword_dict[attribute] = value

    if enumerators is not None:
        keyword_dict['enumerators'] = enumerators

    return keyword_dict


# Translate KTL data types to mKTL types.

type_mapping = dict()
type_mapping['KTL_BOOLEAN'] = 'boolean'
type_mapping['KTL_DOUBLE_ARRAY'] = 'numeric array'
type_mapping['KTL_DOUBLE'] = 'numeric'
type_mapping['KTL_ENUM'] = 'enumerated'
type_mapping['KTL_ENUMM'] = 'enumerated'
type_mapping['KTL_FLOAT_ARRAY'] = 'numeric array'
type_mapping['KTL_FLOAT'] = 'numeric'
type_mapping['KTL_INT64_ARRAY'] = 'numeric array'
type_mapping['KTL_INT64'] = 'numeric'
type_mapping['KTL_INT_ARRAY'] = 'numeric array'
type_mapping['KTL_INT'] = 'numeric'
type_mapping['KTL_MASK'] = 'mask'
type_mapping['KTL_STRING'] = 'string'


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
