""" This is an implementation of a EPICS proxy, enabling full mKTL commands
    to a EPICS channel.
"""

import mktl
import epics
import itertools


class Daemon(mktl.Daemon):

    def __init__(self, store, alias=None, *args, **kwargs):

        # Generate the configuration matching this set of EPICS channels. Since this
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
        keys = self.config.keys(authoritative=True)

        for key in keys:
            self.add_item(Item, key)


    def setup_final(self):
        """ This is the last step before broadcasts go out. This is the
            right time to fire up monitoring of all EPICS PVs.
        """
        keys = self.config.keys(authoritative=True)
        for key in keys:
            if key.startswith('_'): # may not need this anymore
                continue
            item = self.store[key]
            pvname = self.config[key]['channel'] 
            pv = epics.PV(pvname)
            pv.add_callback(item.publish_broadcast) 


# end of class Store



class Item(mktl.Item):

    def __init__(self, *args, **kwargs):
        mktl.Item.__init__(self, *args, **kwargs)

        # We want the EPICS channels to be the sole source of broadcast
        # events. mKTL defaults to publishing a new value when a SET operation
        # completes successfully; this attribute inhibits that behavior.
        self.publish_on_set = False

    def publish_broadcast(self, *args, **kwargs):
        """ This method is registered as an EPICS callback; take any/all EPICS 
            broadcast events and publish them as mKTL events.

            Epics callback functions are called with several keyword arguments. 
            you should always include **kwargs in your callback definition to
            capture all of them. Here are some example callback arguments:
                pvname   : Name of the PV that triggered the callback
                value    : Current value of the PV
                type:    : the Python type for the data
                units    : string for PV units
            See https://pyepics.github.io/pyepics/pv.html#user-supplied-callback-functions 
            for an exhaustive list of callback arguments.
        """
        try: 
            value = kwargs['value']
        except KeyError:
            return
        timestamp = self._get_timestamp(kwargs.get('timestamp'))
        self.publish(value, timestamp) # Publish will pick up the timestamp value if it is None.

    def _get_timestamp(self, timestamp, minlim=915184800):
        """Check if there is a timestamp. If it is None or before 1999-01-01,
           return None to let mKTL handle it. Otherwise return the timestamp.
        """
        if timestamp is None: 
            return None
        elif timestamp < minlim: # this is unix timestamp for 1999-01-01
            return None
        else: 
            return timestamp

    def _get_pv_with_metadata(self):
        """ Return the EPICS PV object associated with this item.
        """
        pv = epics.PV(self.config['channel'])
        resp = None
        tries = 0
        while resp is None:  # try up to 5 times to get a valid response
            resp = pv.get_with_metadata(as_string=True) # get the value and metadata
            tries += 1
            if tries >= 5:
                raise RuntimeError(f"Could not get metadata for PV {self.config['channel']}")
        return resp 


    def perform_get(self):
        """ Wrap an incoming GET request to a Epics channel get. This method
            is only invoked on synchronous GET requests, normally it would
            also be invoked when local polling occurs, but this wrapper
            relies on epics callbacks to receive asynchronous broadcasts
            (see :func:`publish_broadcast`).
        """
        if 'channel' not in self.config.keys():
            return None
        resp = self._get_pv_with_metadata()
        timestamp = self._get_timestamp(resp.get('timestamp'))
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
        if not self.config.get('settable'):
            return None
        pv = epics.PV(self.config['channel'])
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

    channel_dict = dict()

    type = pv.type
    type = type_mapping[type.upper()]
    channel_dict['type'] = type
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
            channel_dict[attribute] = value

    # make range attribute
    try:
        lower = getattr(pv, 'lower_ctrl_limit')
        upper = getattr(pv, 'upper_ctrl_limit')
    except ValueError:
        pass
    else:
        channel_dict['range'] = {"minimum": lower, "maximum": upper}

    for attribute in ('key', 'read_access', 'write_access'):
        try:
            if attribute == 'key':
                value = pv.config['channel']
            else:
                value = getattr(pv, attribute)
        except ValueError:
            value = None

        if value is False:
            channel_dict[attribute] = value

    if enumerators is not None:
        channel_dict['enumerators'] = enumerators

    return channel_dict


# Translate Epics data types to mKTL types.

type_mapping = dict()
epics_types = ['double', 'float', 'int', 'string', 'short', 'enum', 'char', 'long']
numeric_types = set(('double', 'float', 'short', 'int', 'char', 'long'))
epics_variants = ['', 'ctrl', 'time']
for v, t in itertools.product(epics_variants, epics_types):
    if v == '':
        epics_type = t.upper()
    else:
        epics_type = f'{v.upper()}_{t.upper()}'
    if t in numeric_types:
        mktl_type = 'numeric'
    elif t == 'string':
        mktl_type = 'string'
    elif t == 'enum':
        mktl_type = 'enumerated'
    type_mapping[epics_type] = mktl_type

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
