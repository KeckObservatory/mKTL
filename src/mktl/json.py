""" Wrapper module to select the most performant available library to handle
    the equivalent of :func:`json.loads` and :func:`json.dumps`.
"""

dumps = None
loads = None


def use_json():

    import json
    global dumps
    global loads

    # The msgspec 'encode' operation returns bytes, as does orjson.dumps(). To
    # maintain alignment all dumps() methods need to do so as well. The loads()
    # methods in each implementation will accept bytes as input.

    def json_dumps(*args, **kwargs):
        return json.dumps(*args, **kwargs).encode()

    # One could use cached instances of json.JSONEncoder and json.JSONDecoder
    # here, but it doesn't appear to be any more efficient than calling the
    # top-level methods directly. The JSONDecoder also won't accept bytes
    # for decoding, but json.loads() will.

    dumps = json_dumps
    loads = json.loads


def use_msgspec():

    import msgspec
    global dumps
    global loads

    encoder = msgspec.json.Encoder()
    decoder = msgspec.json.Decoder()
    dumps = encoder.encode
    loads = decoder.decode


def use_orjson():

    import orjson
    global dumps
    global loads

    dumps = orjson.dumps
    loads = orjson.loads


# The loader methods are specified in order of descending performance of
# their respective JSON implementations.

loaders = (use_msgspec, use_orjson, use_json)

for loader in loaders:
    try:
        loader()
    except ImportError:
        continue
    else:
        break

# It is assumed that use_json() will always be available.

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
