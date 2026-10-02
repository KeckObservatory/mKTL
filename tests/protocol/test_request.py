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


def test_client():

    server = mktl.protocol.request.Server()

    # Relying on 'localhost' here may not be appropriate.
    client = mktl.protocol.request.Client('localhost', server.port)



def test_client_factory():

    server = mktl.protocol.request.Server()

    client1 = mktl.protocol.request.client('localhost', server.port)
    client2 = mktl.protocol.request.client('localhost', server.port)

    assert client1 is client2

    with pytest.raises(RuntimeError):
        mktl.protocol.request.Client('localhost', server.port)

    mktl.protocol.request.shutdown()



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
