''' Wrapper module to select the most performant available library to handle
    the equivalent of :func:`json.loads` and :func:`json.dumps`.
'''

# The business about conditionally importing the libraries is intended to
# avoid importing less efficient libraries if they are not available. With
# the right build process this could be determined at build time, instead
# of at run time.

try:
    import msgspec
except ImportError:
    msgspec = None
else:
    orjson = None
    json = None

if msgspec is None:
    try:
        import orjson
    except ImportError:
        orjson = None
    else:
        json = None

if msgspec is None and orjson is None:
    import json


# msgspec returns bytes.
orjson_dumps

if msgspec is not None:
    encoder = msgspec.json.Encoder()
    decoder = msgspec.json.Decoder()
    dumps = encoder.encode
    loads = decoder.decode
elif orjson is not None:

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
