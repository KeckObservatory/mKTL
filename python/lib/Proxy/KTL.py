
import json
import threading
import time

from . import Subprocess

try:
    import ktl
except ModuleNotFoundError:
    ktl = None

class KTL(Subprocess.Base):

    def __init__(self, req, pub, name):

        if ktl is None:
            raise ModuleNotFoundError("cannot import the 'ktl' module")

        self.name = name
        Subprocess.Base.__init__(self, req, pub)

        service = ktl.cache(name)

        for name in service:
            keyword = service[name]

            if keyword['broadcasts'] == True:
                keyword.callback(self.relay)
                keyword.monitor(wait=False)


    def req_config(self, request):
        service_dict = describeService(self.name)

        hash = self.hash(service_dict['keys'])
        service_dict['hash'] = hash
        service_dict['time'] = time.time()

        return service_dict


    def req_get(self, request):
        name = request['name']
        keyword = ktl.cache(name)

        if keyword['monitored'] != True:
            keyword.read()

        slice = keyword.history[-1]
        timestamp = slice.time
        ascii = slice.ascii
        binary = slice.binary

        payload = dict()
        payload['asc'] = ascii
        payload['bin'] = binary

        return payload


    def req_set(self, request):

        name = request['name']
        keyword = ktl.cache(name)

        new_value = request['data']
        keyword.write(new_value)


    def relay(self, keyword):

        try:
            slice = keyword.history[-1]
        except IndexError:
            return

        timestamp = slice.time
        ascii = slice.ascii
        binary = slice.binary

        payload = dict()
        payload['asc'] = ascii
        payload['bin'] = binary

        pub_id = self.pub_id_next()

        broadcast_dict = dict()
        broadcast_dict['message'] = 'PUB'
        broadcast_dict['id'] = pub_id
        broadcast_dict['time'] = timestamp
        broadcast_dict['name'] = keyword.full_name
        broadcast_dict['data'] = payload

        broadcast_json = json.dumps(broadcast_dict)

        broadcast_bytes = keyword.full_name + ' ' + broadcast_json
        broadcast_bytes = broadcast_bytes.encode()

        self.publish(broadcast_bytes)


# end of class KTL



def describeService(name):
    service = ktl.cache(name)
    service_dict = dict()
    service_dict['name'] = name

    keywords = list()
    for keyword in service:
        keyword_dict = describeKeyword(keyword)
        keywords.append(keyword_dict)

    service_dict['keys'] = keywords
    return service_dict


def describeKeyword(keyword):
    keyword_dict = dict()
    keyword_dict['name'] = keyword.name

    type = keyword['type']
    type = type_mapping[type]
    keyword_dict['type'] = type

    try:
        enumerators = keyword['enumerators']
    except ValueError:
        enumerators = None
    else:
        rebuilt = list()
        for key in range(len(enumerators)):
            enumerator = enumerators[key]
            if enumerator == '':
                continue
            else:
                rebuilt.append({key: enumerator})

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
                    units['asc'] = value
                    units['bin'] = binary_units

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


# Translate KTL data types to POT types.

type_mapping = dict()
type_mapping['KTL_BOOLEAN'] = 'boolean'
type_mapping['KTL_DOUBLE_ARRAY'] = 'double array'
type_mapping['KTL_DOUBLE'] = 'double'
type_mapping['KTL_ENUM'] = 'enumerated'
type_mapping['KTL_ENUMM'] = 'enumerated'
type_mapping['KTL_FLOAT_ARRAY'] = 'double array'
type_mapping['KTL_FLOAT'] = 'double'
type_mapping['KTL_INT64_ARRAY'] = 'integer array'
type_mapping['KTL_INT64'] = 'integer'
type_mapping['KTL_INT_ARRAY'] = 'integer array'
type_mapping['KTL_INT'] = 'integer'
type_mapping['KTL_MASK'] = 'mask'
type_mapping['KTL_STRING'] = 'string'


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
