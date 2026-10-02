import mktl
import pytest
import time


def test_server():

    server = mktl.protocol.publish.Server()

    payload = mktl.protocol.message.Payload(value=True, time=time.time())
    message = mktl.protocol.message.Broadcast('PUB', 'some_topic', payload)

    server.publish(message)

    port_plus = server.port + 1
    server_plus = mktl.protocol.publish.Server(port=port_plus)

    avoid = set((server.port, server_plus.port))
    server_avoid = mktl.protocol.publish.Server(avoid=avoid)

    assert server_avoid.port != server.port
    assert server_avoid.port != server_plus.port


def test_client():

    server = mktl.protocol.publish.Server()
    port = server.port

    # Relying on 'localhost' here may not be appropriate.
    client = mktl.protocol.publish.Client('localhost', port)

    client.subscribe('topic_as_string')
    client.subscribe(b'topic_as_bytes')

    # Calls like the following are not expected to be valid use cases,
    # but they are also not expressly forbidden. Everything gets cast
    # to a string if it is not already bytes.

    client.subscribe(44)
    client.subscribe(True)
    client.subscribe(None)

    with pytest.raises(TypeError):
        client.register('not callable', 'a_topic')


    def callback(*args, **kwargs):
        callback.called = True

    def publish_flood(flood_callback, topic):
        publish_flood.success = False
        flood_callback.called = False

        now = time.time()
        timeout = now + 1
        while now < timeout:
            if flood_callback.called == True:
                publish_flood.success = True
                break

            payload = mktl.protocol.message.Payload(value=True, time=now)
            message = mktl.protocol.message.Broadcast('PUB', topic, payload)

            server.publish(message)
            time.sleep(0.01)
            now = time.time()

    # There are presently no registered callbacks. The publish_flood() attempt
    # should fail.

    publish_flood(callback, 'a_topic')
    assert publish_flood.success == False

    client.register(callback, 'a_topic')

    # The exact timing of when a client is fully subscribed is not
    # deterministic. It may take several attempts to send a message
    # before the client sees it. Hence, another flood.

    publish_flood(callback, 'a_topic')
    assert publish_flood.success == True

    client.unregister(callback, 'not_subscribed')
    client.unregister(callback, 'a_topic')

    def bad_callback(*args, **kwargs):
        bad_callback.called = True
        raise RuntimeError('generic uncaught exception')

    client.register(bad_callback, 'bad_topic')
    publish_flood(bad_callback, 'bad_topic')
    assert publish_flood.success == True

    # Trigger the handling of callbacks that are no longer valid.

    del bad_callback
    payload = mktl.protocol.message.Payload(value=True, time=time.time())
    message = mktl.protocol.message.Broadcast('PUB', 'bad_topic', payload)
    server.publish(message)

    payload = mktl.protocol.message.Payload(value=True, time=time.time())
    message = mktl.protocol.message.Broadcast('PUB', 'bad_topic', payload)
    server.publish(message)

    payload = mktl.protocol.message.Payload(value=True, time=time.time())
    message = mktl.protocol.message.Broadcast('PUB', 'bad_topic', payload)
    server.publish(message)


def test_client_factory():

    server = mktl.protocol.publish.Server()

    client1 = mktl.protocol.publish.client('localhost', server.port)
    client2 = mktl.protocol.publish.client('localhost', server.port)

    assert client1 is client2

    with pytest.raises(ConnectionError):
        mktl.protocol.publish.Client('localhost', server.port)

    mktl.protocol.publish.shutdown()


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
