import mktl
import pytest
import time

def test_basics():

    start = time.time()

    for test_value in (44, True, None, 35.5, (1,2,3), {1: 'one'}, 'string'):
        payload = mktl.protocol.message.Payload(test_value)
        assert payload.value is test_value
        assert payload.time > start
        assert payload.bulk == None
        assert payload.dtype == None
        assert payload.error == None
        assert payload.refresh == None
        assert payload.shape == None
        ## Pull request is pending
        ##assert payload.reply == True
        payload.encapsulate()


def test_encapsulate():

    test_value = 44
    for test_value in (44, True, None, 35.5, [1,2,3], 'string'):
        payload = mktl.protocol.message.Payload(test_value)

        encapsulated = payload.encapsulate()
        assert isinstance(encapsulated, bytes)

        decoded = mktl.json.loads(encapsulated)
        assert isinstance(decoded, dict)

        assert 'time' in decoded
        assert 'value' in decoded
        assert decoded['value'] == test_value


    bad_payload = mktl.protocol.message.Payload({None: 'none'})

    with pytest.raises(TypeError):
        bad_payload.encapsulate()


def test_kwargs():

    payload = mktl.protocol.message.Payload('something', testing='testing')
    assert payload.testing == 'testing'

    encapsulated = payload.encapsulate()
    decoded = mktl.json.loads(encapsulated)

    assert 'time' in decoded
    assert 'value' in decoded
    assert 'testing' in decoded

    payload.omit.add('testing')

    encapsulated = payload.encapsulate()
    decoded = mktl.json.loads(encapsulated)

    assert not 'testing' in decoded


def test_origin():

    payload = mktl.protocol.message.Payload('something')
    payload.add_origin()

    encapsulated = payload.encapsulate()
    decoded = mktl.json.loads(encapsulated)

    assert '_user' in decoded
    assert '_hostname' in decoded
    assert '_pid' in decoded
    assert '_ppid' in decoded
    assert '_executable' in decoded
    assert '_argv' in decoded


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
