''' How to generate a hash of a configuration block.
'''

import hashlib

from ..Protocol import Json

def hash(self, dumpable):
    ''' Convert the supplied Python list or dictionary to JSON, hash the
        results, and return the hash. The mKTL protocol description limits
        the hash to 32 hexadecimal integers, but the specific hash type is
        unspecified, and allowed to vary between implementations-- as long
        as it is consistent.
    '''

    json = Json.dumps(dumpable)

    hash = hashlib.shake_256(json)
    hash = int(hash.hexdigest(16), 16)
    return hash


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
