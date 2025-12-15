""" This is an implementation of a EPICS proxy, enabling full mKTL commands
    to a EPICS channel.
"""

import mktl
import epics
from itertools import product
import pdb


class Daemon(mktl.Daemon):

    def __init__(self, store, alias=None, *args, **kwargs):

        # Generate the configuration matching this KTL service. Since this
        # configuration is not in the default location it must be declared
        # prior to initializing the Daemon.
        # store is the mktl store name for the epics object (i.e. k1:mySystem:myDevice)
        # alias is the name mKTL can use if you don't want to use pvname (i.e. myDevice)
        mktl.Daemon.__init__(self, store, alias, *args, **kwargs)

    def setup(self):
        """ The only reason this method exists is to create a EPICS.Item
            instance for each and every channel being proxied by this
            daemon, as opposed to letting them be the default mktl.Item.
        """
        config = self.config[self.uuid]
        items = config['items']
        keys = items.keys()

        for key in keys:
            self.add_item(Item, key)


    def setup_final(self):
        """ This is the last step before broadcasts go out. This is the
            right time to fire up monitoring of all EPICS PVs.
        """
        pass


# end of class Store



class Item(mktl.Item):

    def __init__(self, *args, **kwargs):
        mktl.Item.__init__(self, *args, **kwargs)

        # We want the EPICS channels to be the sole source of broadcast
        # events. mKTL defaults to publishing a new value when a SET operation
        # completes successfully; this attribute inhibits that behavior.
        self.pvname = self.full_key.replace('.', ':')
        service = "".join(self.full_key.split('.')[:-1])
        self.pvname = service + ':' + self.key.upper()

        self.publish_on_set = False

    def publish_broadcast(self, ):
        """ This method is registered as a KTL callback; take any/all KTL
            broadcast events and publish them as mKTL events.
        """
        pv = epics.PV(self.pvname)
        slice = pv.get_with_metadata(as_string=True)
        timestamp = slice.get('timestamp')
        value = slice.get('value')
        bvalue = self.convert_string_to_binary(value)

        self.publish(bvalue, timestamp)


    def perform_get(self):
        """ Wrap an incoming GET request to a Epics channel get. This method
            is only invoked on synchronous GET requests, normally it would
            also be invoked when local polling occurs, but this wrapper
            relies on epics callbacks to receive asynchronous broadcasts
            (see :func:`publish_broadcast`).
        """
        pv = epics.PV(self.pvname)
        resp = pv.get_with_metadata(as_string=True) # get the value and metadata
        timestamp = resp.get('timestamp')
        value = resp.get('value')
        payload = mktl.Payload(value, timestamp)
        return payload


    def perform_set(self, new_value):
        """ Wrap an incoming SET request to a Epics channel put. This method
            is expected to block until completion of the request. The values
            presented at this level are the equivalent of the KTL binary
            value, and this needs to be asserted explicitly at the KTL level
            to ensure they are interpreted (or not interpreted, as the case
            may be) properly.
        """
        pv = epics.PV(self.pvname)
        pv.put(new_value, wait=True)

# end of class Item


def describeChannel(name):
    """ Construct an mKTL configuration block to describe the named Epics channel.
    """
    pv = epics.PV(name)
    slice = pv.get_with_metadata(as_string=True)  # populate metadata
    return slice 


def describePV(pv: epics.PV):
    """ Construct an item-specific mKTL configuration block for a single
        Epics channel.
    """

    keyword_dict = dict()

    type = pv.type
    type = type_mapping[type.upper()]
    keyword_dict['type'] = type
    enumerators = None

    try:
        enumerators = pv['enum_strs']
    except:
        pass

    if enumerators: # ignore empty enumerators
        rebuilt = dict()
        for key in range(len(enumerators)):
            enumerator = enumerators[key]
            if enumerator == '':
                continue
            else:
                rebuilt[key] = enumerator

        enumerators = rebuilt

    for attribute in ('units', 'info'):
        try:
            value = getattr(pv, attribute)
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
            keyword_dict[attribute] = value

    # make range attribute
    try:
        lower = getattr(pv, 'lower_ctrl_limit')
        upper = getattr(pv, 'upper_ctrl_limit')
    except ValueError:
        pass
    else:
        keyword_dict['range'] = {"minimum": lower, "maximum": upper}

    for attribute in ('key', 'read_access', 'write_access'):
        try:
            if attribute == 'key':
                value = pv.pvname
            else:
                value = getattr(pv, attribute)
        except ValueError:
            value = None

        if value is False:
            keyword_dict[attribute] = value

    if enumerators is not None:
        keyword_dict['enumerators'] = enumerators

    return keyword_dict


# Translate Epics data types to mKTL types.

type_mapping = dict()
epics_types = ['double', 'float', 'int', 'string', 'short', 'enum', 'char', 'long']
epics_variants = ['', 'ctrl', 'time']
for v, t in product(epics_variants, epics_types):
    if v == '':
        epics_type = t.upper()
    else:
        epics_type = f'{v.upper()}_{t.upper()}'
    if t in ['double', 'float']:
        mktl_type = 'numeric'
    elif t in ['int', 'char', 'long']:
        mktl_type = 'numeric'
    elif t == 'string':
        mktl_type = 'string'
    elif t == 'enum':
        mktl_type = 'enumerated'
    type_mapping[epics_type] = mktl_type

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
