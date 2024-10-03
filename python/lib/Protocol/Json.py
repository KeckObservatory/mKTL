''' Wrapper module to select the most performant available library to handle
    the equivalent of :func:`json.loads` and :func:`json.dumps`.
'''

# The business about conditionally importing the libraries is intended to
# avoid importing less efficient libraries if they are not available. With
# the right build process this could be determined at build time, instead
# of at run time.

msgspec = None
orjson = None
json = None

try:
    import msgspec
except ImportError:
    pass

if msgspec is None:
    try:
        import orjson
    except ImportError:
        pass

if msgspec is None and orjson is None:
    import json


# The msgspec 'encode' operation returns bytes, as does orjson.dumps. To
# maintain alignment all 'dumps' methods need to do so as well.

def json_dumps(*args, **kwargs):
    return json.dumps(*args, **kwargs).encode()

if msgspec is not None:
    encoder = msgspec.json.Encoder()
    decoder = msgspec.json.Decoder()
    dumps = encoder.encode
    loads = decoder.decode
elif orjson is not None:
    dumps = orjson.dumps
    loads = orjson.loads
else:
    dumps = json_dumps
    loads = json.loads

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
