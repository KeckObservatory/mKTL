""" This is an implementation of a KTL proxy, enabling full mKTL commands
    to a KTL service.
"""

import ktl
import mktl


class Daemon(mktl.Daemon):

    def __init__(self, store, alias, *args, **kwargs):

        # Generate the configuration matching this KTL service. Since this
        # configuration is not in the default location it must be declared
        # prior to initializing the Daemon.

        items = describeService(store)
        mktl.config.authoritative(store, alias, items)
        mktl.Daemon.__init__(self, store, alias, *args, **kwargs)


    def setup(self):
        """ The only reason this method exists is to create a KTL.Item
            instance for each and every KTL keyword being proxied by this
            daemon, as opposed to letting them be the default mktl.Item.
        """

        keys = self.config.keys(authoritative=True)

        for key in keys:
            self.add_item(Item, key)


    def setup_final(self):
        """ This is the last step before broadcasts go out. This is the
            right time to fire up monitoring of all KTL keywords.
        """

        service = ktl.cache(self.store.name)

        for keyword in service:

            if keyword['broadcasts'] == True:
                item = self.store[keyword.name]
                keyword.callback(item.publish_ktl_broadcast)
                keyword.monitor(wait=False)


# end of class Daemon



class Item(mktl.Item):

    def __init__(self, *args, **kwargs):
        mktl.Item.__init__(self, *args, **kwargs)

        # We want the KTL dispatchers to be the sole source of broadcast
        # events. mKTL defaults to publishing a new value when a SET operation
        # completes successfully; this attribute inhibits that behavior.

        self.publish_on_set = False


    def publish_ktl_broadcast(self, keyword):
        """ This method is registered as a KTL callback; take any/all KTL
            broadcast events and publish them as mKTL events.
        """

        try:
            slice = keyword.history[-1]
        except IndexError:
            return

        timestamp = slice.time
        #ascii = slice.ascii
        binary = slice.binary

        # This method could assign self.value = binary, but that wouldn't
        # preserve the timestamp. Call self.publish() instead to preserve
        # both pieces of information.

        self.publish(binary, timestamp)


    def perform_get(self):
        """ Wrap an incoming GET request to a KTL keyword read. This method
            is only invoked on synchronous GET requests, normally it would
            also be invoked when local polling occurs, but this wrapper
            relies on KTL callbacks to receive asynchronous broadcasts
            (see :func:`publish_ktl_broadcast`).
        """

        keyword = ktl.cache(self.full_key)
        keyword.read()

        slice = keyword.history[-1]
        timestamp = slice.time
        binary = slice.binary

        payload = mktl.Payload(binary, timestamp)
        return payload


    def perform_set(self, new_value):
        """ Wrap an incoming SET request to a KTL keyword write. This method
            is expected to block until completion of the request. The values
            presented at this level are the equivalent of the KTL binary
            value, and this needs to be asserted explicitly at the KTL level
            to ensure they are interpreted (or not interpreted, as the case
            may be) properly.
        """

        keyword = self.full_key
        keyword = ktl.cache(keyword)
        keyword.write(new_value, binary=True)


# end of class Item



def describeService(name):
    """ Construct an mKTL configuration block to describe the named KTL service.
    """

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
    """ Construct an item-specific mKTL configuration block for a single
        KTL keyword.
    """

    keyword_dict = dict()

    type = keyword['type']
    type = type_mapping[type]
    keyword_dict['type'] = type
    enumerators = None

    try:
        enumerators = keyword['enumerators']
    except:
        pass

    if enumerators is None:
        try:
            enumerators = keyword['keys']
        except:
            pass
        else:
            if len(enumerators) == 0:
                enumerators = None

    if enumerators:
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
        except:
            # CAke throws a lot of nonsense exceptions when you ask it
            # questions it isn't prepared to receive. Unfortunately,
            # that means catching _all_ exceptions here, rather than a
            # targeted set.
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

    if type == 'numeric':
        # Some KTL client types abuse the 'units' field to include sprintf
        # style formatting. Grab that if it is available; there is no KTL
        # API call to get at this information directly.

        unit_abuse = keyword.ktlc.units()

        if len(unit_abuse) > 2:
            format = unit_abuse[2]
            if format != '':
                keyword_dict['format'] = format

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
