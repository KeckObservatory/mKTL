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
    message = mktl.protocol.message.Message('REP', b'key', payload)
    message = mktl.protocol.message.Message('REP', 'key', payload, id=test_id)

    message.id = None

    with pytest.raises(RuntimeError):
        message._finalize()

    # The message ID is supposed to be translated automatically if it is set
    # to something like a bare integer.

    message.id = 44
    message._finalize()
    parts = tuple(message)
    assert parts[1] == test_id

    # Reset the ID to the on-the-wire format for the rest of the checks.

    message.id = test_id

    repr(message)
    message.log()

    # Exercise the custom logging behavior triggered by the presence of the
    # lengthy origin metadata.

    payload.add_origin()
    message = mktl.protocol.message.Message('REP', 'key', payload, id=test_id)
    message.log()

    parts = tuple(message)
    assert len(parts) == 6
    reconstructed = mktl.protocol.message.Message.reconstruct(parts)
    assert message.id == reconstructed.id
    assert message.payload.value == reconstructed.payload.value

    too_many_parts = parts * 2
    with pytest.raises(ValueError):
        mktl.protocol.message.Message.reconstruct(too_many_parts)

    message = mktl.protocol.message.Message('REP', 'key', id=test_id)
    parts = tuple(message)
    reconstructed = mktl.protocol.message.Message.reconstruct(parts)

    assert reconstructed.payload is None

    bad_version = (b'invalid version',) + parts[1:]
    with pytest.raises(ValueError):
        mktl.protocol.message.Message.reconstruct(bad_version)


    message = mktl.protocol.message.Message('REP', 'key', payload, id=test_id)
    prefix = (b'a prefix',)
    message.prefix = prefix
    parts = tuple(message)

    assert len(parts) == 7

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('BAD', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('GET', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('SET', 'key', payload)

    with pytest.raises(ValueError):
        mktl.protocol.message.Message('PUB', 'key', payload)

    # Limited exercise of the bulk payload. This is not a properly described
    # bulk data payload, but it's enough to hit conditions specific to that
    # aspect of the multipart message format.

    now = time.time()
    bulk = b'29764735490930841093'
    bulk_payload = mktl.protocol.message.Payload(value=55, time=now, bulk=bulk)

    assert bulk_payload.bulk is not None

    message = mktl.protocol.message.Message('REP', 'key', bulk_payload, id=test_id)
    parts = tuple(message)

    assert len(parts) == 7


def test_broadcast():

    payload = mktl.protocol.message.Payload(value=5, time=time.time())

    broadcast = mktl.protocol.message.Broadcast('PUB', 'key')
    broadcast = mktl.protocol.message.Broadcast('PUB', b'key.')
    broadcast = mktl.protocol.message.Broadcast('PUB', 'key', payload)

    repr(broadcast)
    broadcast.log()

    parts = tuple(broadcast)
    reconstructed = mktl.protocol.message.Broadcast.reconstruct(parts)
    assert broadcast.payload.value == reconstructed.payload.value

    broadcast = mktl.protocol.message.Broadcast('PUB', b'key.')
    parts = tuple(broadcast)
    reconstructed = mktl.protocol.message.Broadcast.reconstruct(parts)
    assert reconstructed.payload is None

    now = time.time()
    bulk = b'29764735490930841093'
    bulk_payload = mktl.protocol.message.Payload(value=55, time=now, bulk=bulk)

    broadcast = mktl.protocol.message.Broadcast('PUB', 'key', bulk_payload)
    parts = tuple(broadcast)
    reconstructed = mktl.protocol.message.Broadcast.reconstruct(parts)
    assert reconstructed.payload.bulk == bulk

    bad_version = (parts[0],) + (b'invalid version',) + parts[2:]
    with pytest.raises(ValueError):
        mktl.protocol.message.Broadcast.reconstruct(bad_version)

    too_many_parts = parts * 2
    with pytest.raises(ValueError):
        mktl.protocol.message.Broadcast.reconstruct(too_many_parts)

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

    assert request.poll() == False
    assert request.wait(0.00001) == None
    assert request.wait_ack(0.00001) == False
    request._complete_ack()
    assert request.wait_ack(None) == True
    request._complete('535')
    assert request.wait(None) == '535'
    assert request.poll() == True

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

    flags = 0
    request = mktl.protocol.message.Request('SET', 'key', payload, flags=flags)

    assert request.ack == True
    assert request.reply == True

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

    parts = tuple(request)
    reconstructed = mktl.protocol.message.Request.reconstruct(parts)
    assert request.flags == reconstructed.flags


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
