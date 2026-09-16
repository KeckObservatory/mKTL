import mktl
import pytest
import time

def test_message():

    test_id = 44
    test_id = "%08x" % (test_id)
    test_id = test_id.encode()

    payload = mktl.protocol.message.Payload(value=5, time=time.time())
    message = mktl.protocol.message.Message('ACK', 'key', payload)
    message = mktl.protocol.message.Message('ACK', 'key', payload, id=test_id)
    message = mktl.protocol.message.Message('REP', 'key', payload)
    message = mktl.protocol.message.Message('REP', 'key', payload, id=test_id)

    message.id = None

    with pytest.raises(RuntimeError):
        message._finalize()

    message.id = test_id

    repr(message)
    message.log()

    parts = tuple(message)
    reconstructed = mktl.protocol.message.Message.reconstruct(parts)
    assert message.id == reconstructed.id
    assert message.payload.value == reconstructed.payload.value

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('BAD', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('GET', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('SET', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('PUB', 'key', payload)


def test_broadcast():

    payload = mktl.protocol.message.Payload(value=5, time=time.time())
    broadcast = mktl.protocol.message.Broadcast('PUB', 'key')
    broadcast = mktl.protocol.message.Broadcast('PUB', 'key', payload)

    repr(broadcast)
    broadcast.log()

    parts = tuple(broadcast)
    reconstructed = mktl.protocol.message.Broadcast.reconstruct(parts)
    assert broadcast.payload.value == reconstructed.payload.value


    with pytest.raises(ValueError):
        mktl.protocol.message.Broadcast('BAD', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Broadcast('ACK', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Broadcast('REP', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Broadcast('GET', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Broadcast('SET', 'key', payload)


def test_request():

    payload = mktl.protocol.message.Payload(value=5, time=time.time())
    request = mktl.protocol.message.Request('GET', 'key')
    request = mktl.protocol.message.Request('GET', 'key', payload)
    request = mktl.protocol.message.Request('SET', 'key')
    request = mktl.protocol.message.Request('SET', 'key', payload)

    repr(request)
    request.log()

    parts = tuple(request)
    reconstructed = mktl.protocol.message.Request.reconstruct(parts)
    assert request.id is not None
    assert request.id == reconstructed.id
    assert request.payload.value == reconstructed.payload.value

    with pytest.raises(ValueError):
        mktl.protocol.message.Request('BAD', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Request('ACK', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Request('REP', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Request('PUB', 'key', payload)


    NO_ACK = mktl.protocol.message.NO_ACK
    NO_REP = mktl.protocol.message.NO_REP
    NO_ACK_OR_REP = mktl.protocol.message.NO_ACK_OR_REP

    assert NO_ACK_OR_REP & NO_ACK == NO_ACK
    assert NO_ACK_OR_REP & NO_REP == NO_REP
    assert NO_ACK_OR_REP == NO_ACK | NO_REP

    flags = NO_ACK
    request = mktl.protocol.message.Request('SET', 'key', payload, flags=flags)

    assert request.ack == False
    assert request.reply == True

    flags = NO_REP
    request = mktl.protocol.message.Request('SET', 'key', payload, flags=flags)

    assert request.ack == True
    assert request.reply == False

    flags = NO_ACK_OR_REP
    request = mktl.protocol.message.Request('SET', 'key', payload, flags=flags)

    assert request.ack == False
    assert request.reply == False

    flags = 0
    request = mktl.protocol.message.Request('SET', 'key', payload, flags=flags)

    assert request.ack == True
    assert request.reply == True


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
