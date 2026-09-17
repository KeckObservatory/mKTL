import json
import mktl

# The test methods are defined here in significant order, in case there are
# lingering impacts to the mktl import for future tests; each module is tested
# in order of increasing efficiency, similar to how they are imported in
# mKTL's json.py.

def test_json():
    mktl.json.use_json()
    encode_and_decode()


def test_orjson():
    try:
        mktl.json.use_orjson()
    except ImportError:
        return

    encode_and_decode()


def test_msgspec():
    try:
        mktl.json.use_msgspec()
    except ImportError:
        return

    encode_and_decode()


def encode_and_decode():

    input_dictionary = dict()
    input_dictionary['list'] = [1, 2, 3, 'a', 'b', None, 'c', 'z']
    input_dictionary['dict'] = {1: 'one', 'two': 2}
    input_dictionary['none'] = None
    input_dictionary['true'] = True
    input_dictionary['false'] = False

    try:
        encoded = mktl.json.dumps(input_dictionary)
    except TypeError:
        # The orjson module throws an exception rather than silently translate
        # the offending key to a string.
        del input_dictionary['dict'][1]
        input_dictionary['dict']['1'] = 'one'
        encoded = mktl.json.dumps(input_dictionary)

    assert isinstance(encoded, bytes)

    # It won't do to compare the encoded JSON against a pre-set notion of
    # what the encoded output should look like, as there is variance in
    # the handling of whitespace between the different modules used by mKTL.

    decoded = mktl.json.loads(encoded)
    assert isinstance(decoded, dict)

    # JSON will not use bare integers as dictionary keys, they get translated
    # to strings upon encoding. The decoding step has no way to know that the
    # original input was an integer. So, the decoded JSON should not match the
    # original input dictionary.

    if 1 in input_dictionary['dict']:
        assert decoded != input_dictionary
    else:
        assert decoded == input_dictionary


    # If we fix that one item in the nested dictionary it should match.

    try:
        del input_dictionary['dict'][1]
    except KeyError:
        # We must be testing orjson, see the above try/except.
        pass

    input_dictionary['dict']['1'] = 'one'
    assert decoded == input_dictionary


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
