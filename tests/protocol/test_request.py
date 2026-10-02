import mktl
import pytest
import time


def test_server():

    server = mktl.protocol.request.Server()

    port_plus = server.port + 1
    server_plus = mktl.protocol.request.Server(port=port_plus)

    avoid = set((server.port, server_plus.port))
    server_avoid = mktl.protocol.request.Server(avoid=avoid)

    assert server_avoid.port != server.port
    assert server_avoid.port != server_plus.port

    with pytest.raises(ConnectionError):
        mktl.protocol.request.Server('localhost', server.port)


def test_client():

    server = mktl.protocol.request.Server()

    # Relying on 'localhost' here may not be appropriate.
    client = mktl.protocol.request.Client('localhost', server.port)

    request = mktl.protocol.message.Request('GET', 'some_topic')
    assert request.response is None

    client.send(request)

    acknowledged = request.wait_ack(timeout=0.5)
    assert acknowledged == True

    responded = request.wait(timeout=0.5)
    assert responded == True

    assert request.response is not None
    assert isinstance(request.response.payload, mktl.protocol.message.Payload)

    flags = mktl.protocol.message.NO_ACK_OR_REP
    request = mktl.protocol.message.Request('GET', 'some_topic', flags=flags)

    client.send(request)

    acknowledged = request.wait_ack(timeout=0.5)
    assert acknowledged == False
    assert request.poll() is False
    assert request.response is None


def test_client_factory():

    server = mktl.protocol.request.Server()

    client1 = mktl.protocol.request.client('localhost', server.port)
    client2 = mktl.protocol.request.client('localhost', server.port)

    assert client1 is client2

    with pytest.raises(ConnectionError):
        mktl.protocol.request.Client('localhost', server.port)

    request = mktl.protocol.message.Request('GET', 'some_topic')
    payload = mktl.protocol.request.send(server.hostname, server.port, request)

    assert payload is not None

    mktl.protocol.request.shutdown()



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
