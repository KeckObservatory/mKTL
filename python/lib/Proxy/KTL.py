
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
        uuid = self.uuid('ktl.' + self.name)

        configuration = dict()
        configuration['name'] = self.name
        configuration['uuid'] = uuid
        configuration['time'] = time.time()
        configuration['keys'] = describeService(self.name)
        hash = self.hash(configuration['keys'])
        configuration['hash'] = hash

        return configuration


    def req_get(self, request):
        name = request['name']
        keyword = ktl.cache(name)

        try:
            refresh = request['refresh']
        except KeyError:
            refresh = False
        else:
            if refresh == None or refresh == '':
                refresh = False

        if keyword['monitored'] != True or refresh == True:
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

        broadcast = dict()
        broadcast['message'] = 'PUB'
        broadcast['time'] = timestamp
        broadcast['name'] = keyword.full_name
        broadcast['data'] = payload

        self.publish(broadcast)


# end of class KTL



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
