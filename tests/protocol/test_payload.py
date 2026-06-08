import mktl
import pytest
import time

def test_basics():

    start = time.time()

    for test_value in (44, True, None, 35.5, (1,2,3), {1: 'one'}, 'string'):
        payload = mktl.protocol.message.Payload(value=test_value, time=time.time())
        assert payload.value is test_value
        assert payload.time > start

        # The 'new' Payload only has attributes for the keyword arguments
        # set when it is instantiated.

        with pytest.raises(AttributeError):
            payload.bulk
        with pytest.raises(AttributeError):
            payload.dtype
        with pytest.raises(AttributeError):
            payload.error
        with pytest.raises(AttributeError):
            payload.refresh
        with pytest.raises(AttributeError):
            payload.shape

        payload.encapsulate()


def test_encapsulate():

    test_value = 44
    for test_value in (44, True, None, 35.5, [1,2,3], 'string'):
        payload = mktl.protocol.message.Payload(value=test_value, time=time.time())

        encapsulated = payload.encapsulate()
        assert isinstance(encapsulated, bytes)

        decoded = mktl.json.loads(encapsulated)
        assert isinstance(decoded, dict)

        assert 'time' in decoded
        assert 'value' in decoded
        assert decoded['value'] == test_value


    bad_payload = mktl.protocol.message.Payload(value={None: 'none'})

    with pytest.raises(TypeError):
        bad_payload.encapsulate()


def test_kwargs():

    payload = mktl.protocol.message.Payload(value='something', testing='testing', time=time.time())
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

    payload = mktl.protocol.message.Payload(payload='something')
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
