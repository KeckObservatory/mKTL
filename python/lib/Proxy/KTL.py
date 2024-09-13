
import hashlib
import json
import threading
import time

from . import Common

try:
    import ktl
except ModuleNotFoundError:
    ktl = None

class KTL(Common.Base):

    def __init__(self, req, pub, name):

        if ktl is None:
            raise ModuleNotFoundError("cannot import the 'ktl' module")

        Proxy.Base.__init__(self, req, pub)

        self.name = name
        service = ktl.cache(name)

        for name in service:
            keyword = service[name]

            if keyword['broadcasts'] == True:
                keyword.callback(self.relay)
                keyword.monitor(wait=False)


    def req_config(self, request):
        service_dict = describeService(self.name)

        ### Probably makes sense to break out the hash and timestamp handling
        ### to common code.

        keywords_json = json.dumps(service_dict['keys'])
        keywords_json = keywords_json.encode()
        keywords_hash = hashlib.shake_256(keywords_json)

        service_dict['hash'] = int(keywords_hash.hexdigest(16), 16)
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

        slice = keyword.history[-1]
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

    for attribute in ('units', 'range', 'help', 'enumerators'):
        try:
            value = keyword[attribute]
        except ValueError:
            value = None

        if value is not None:
            if attribute == 'help':
                attribute = 'description'
            keyword_dict[attribute] = value

    for attribute in ('broadcasts', 'reads', 'writes'):
        try:
            value = keyword[attribute]
        except ValueError:
            value = None

        if value is False:
            keyword_dict[attribute] = value

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
