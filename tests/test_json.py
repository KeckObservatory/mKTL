import json
import mktl


def test_json_encode_and_decode():
    encode_and_decode(json.dumps, json.loads, dump_is_bytes=False)


def test_mktl_encode_and_decode():
    encode_and_decode(mktl.json.dumps, mktl.json.loads)


def encode_and_decode(dumps, loads, dump_is_bytes=True):

    input_dictionary = dict()
    input_dictionary['list'] = [1, 2, 3, 'a', 'b', None, 'c', 'z']
    input_dictionary['dict'] = {1: 'one', 'two': 2}
    input_dictionary['none'] = None
    input_dictionary['true'] = True
    input_dictionary['false'] = False

    encoded = dumps(input_dictionary)

    if dump_is_bytes:
        assert isinstance(encoded, bytes)
    else:
        assert isinstance(encoded, str)

    # It won't do to compare the encoded JSON against a pre-set notion of
    # what the encoded output should look like, as there is variance in
    # the handling of whitespace between the different modules used by mKTL.

    decoded = loads(encoded)
    assert isinstance(decoded, dict)

    # JSON will not use bare integers as dictionary keys, they get translated
    # to strings upon encoding. The decoding step has no way to know that the
    # original input was an integer. So, the decoded JSON should not match the
    # original input dictionary.

    assert decoded != input_dictionary

    # If we fix that one item in the nested dictionary it should match.

    del decoded['dict']['1']
    decoded['dict'][1] = 'one'
    assert decoded == input_dictionary


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
