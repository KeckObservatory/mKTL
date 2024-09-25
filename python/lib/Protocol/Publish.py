''' Classes and methods implemented here implement the publish/subscribe
    aspects of the client/server API.
'''

import atexit
import json
import threading
import traceback
import zmq
import zmq.utils.monitor

from .. import WeakRef

default_port = 10133
zmq_context = zmq.Context()


class Client:
    ''' Establish a ZeroMQ SUB connection to a ZeroMQ PUB socket and receive
        broadcasts; the default behavior is to connect to localhost on the
        default port.
    '''

    instances = list()
    port = default_port
    timeout = 5

    def __init__(self, address=None, port=None):

        if address is None:
            address = 'localhost'

        if port is None:
            port = self.port

        port = str(port)
        server = "tcp://%s:%s" % (address, port)
        notify_port = 'inproc://Publish.Client.' + str(id(self))

        self.connected = False
        self.socket = zmq_context.socket(zmq.SUB)

        self.notify_out = zmq_context.socket(zmq.PAIR)
        self.notify_in = zmq_context.socket(zmq.PAIR)

        self.notify_out.bind(notify_port)
        self.notify_in.connect(notify_port)

        self.monitor = self.socket.get_monitor_socket()
        self.monitor_thread = threading.Thread(target=self.checkSocket)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        self.callback_all = list()
        self.callback_specific = dict()

        self.shutdown = False
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

        self.socket.connect(server)

        Client.instances.append(WeakRef.ref(self))


    def checkSocket(self):
        ''' This isn't quite as definitive as one might like-- in particular,
            it can't really tell you whether the server is out there, waiting
            to receive a request. It will happily tell you once you're
            connected, but even if you aren't connected, it might just be that
            you haven't tried yet.
        '''

        while True:
            self.monitor.poll()
            event = zmq.utils.monitor.recv_monitor_message(self.monitor)
            event_code = event['event']

            if event_code == zmq.EVENT_CONNECTED:
                self.connected = True
            elif event_code == zmq.EVENT_HANDSHAKE_SUCCEEDED:
                self.connected = True
            else:
                self.connected = False

            if event_code == zmq.EVENT_MONITOR_STOPPED:
                break

        self.monitor.close()


    def propagate(self, message):
        ''' Invoke any/all callbacks registered via :func:`register` for
            a newly arrived message.
        '''

        # Do nothing if nobody is listening.

        if self.callback_all or self.callback_specific:
            pass
        else:
            return

        # A message is either JSON-formatted or a binary blob. Parse any JSON
        # now so that it only has to happen once; callbacks are expecting to
        # receive a Python dictionary representing the parsed JSON.

        topic, message = message.split(maxsplit=1)

        if topic[-4:] == b'bulk':
            pass
        else:
            message = message.decode()
            message = json.loads(message)

        # Handle the case where a callback is registered for any/all messages.

        invalid = list()
        references = self.callback_all

        for reference in references:
            callback = reference()

            if callback is None:
                invalid.append(reference)

            try:
                callback(message)
            except:
                print(traceback.format_exc())
                continue

        for reference in invalid:
            references.remove(reference)


        # Handle the case where a callback is registered for a specific topic.
        # If there are no topic-specific callbacks, no further processing is
        # required.

        if self.callback_specific:
            pass
        else:
            return

        try:
            references = self.callback_specific[topic]
        except KeyError:
            return

        invalid = list()

        for reference in references:
            callback = reference()

            if callback is None:
                invalid.append(reference)

            try:
                callback(message)
            except:
                print(traceback.format_exc())
                continue

        for reference in invalid:
            references.remove(reference)

        if len(references) == 0:
            del self.callback_specific[topic]


    def register(self, callback, topic=None):
        ''' Register a callback that will be invoked every time a new broadcast
            message arrives. If no topic is specified the callback will be
            invoked for all broadcast messages. The topic is case-sensitive and
            must be an exact match.

            :func:`subscribe` will be invoked for any/all topics registered
            with a callback.
        '''

        if callable(callback):
            pass
        else:
            raise TypeError('callback must be callable')

        reference = WeakRef.ref(callback)

        if topic is None:
            self.callback_all.append(reference)
            self.subscribe('')
        else:
            topic = str(topic)
            topic = topic.strip()
            topic = topic.encode()

            try:
                callbacks = self.callback_specific[topic]
            except:
                callbacks = list()
                self.callback_specific[topic] = callbacks

            callbacks.append(reference)
            self.subscribe(topic)


    def run(self):

        ### Does this need to be fed into a pool of threads via a DEALER
        ### socket? So that one bad propagation doesn't bring it all down?

        ### The notify_in construct probably needs to go. Fine proof of
        ### concept, but doesn't appear to be critical here (so far).

        counter = 0
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self.notify_in, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    message = self.socket.recv()
                    self.propagate(message)
                else:
                    self.snooze()

                counter += 1


    def snooze(self):
        while True:
            try:
                message = self.notify_in.recv()
            except ValueError:
                break


    def stop(self):
        self.shutdown = True
        self.wake()


    def subscribe(self, topic):
        ''' ZeroMQ subscriptions are based on a topic. Filtering of messages
            happens on the server side, depending on what a client is subscribed
            to. A client can subscribe to all messages by providing the empty
            string as the topic.
        '''

        try:
            topic.decode
        except AttributeError:
            topic = str(topic)
            topic = topic.encode()

        self.socket.setsockopt(zmq.SUBSCRIBE, topic)


    def wake(self):
        self.notify_out.send_string('hello')


# end of class Client



class Server:
    ''' Send broadcasts via a ZeroMQ PUB socket. The default behavior is to
        set up a listener on all available network interfaces on the default
        port.
    '''

    port = default_port

    def __init__(self, port=None):

        if port is None:
            port = self.port

        port = 'tcp://*:' + str(port)

        self.socket = zmq_context.socket(zmq.PUB)
        self.socket.bind(port)


    def publish(self, message):

        try:
            message = message.encode()
        except AttributeError:
            if hasattr(message, 'decode'):
                # Assume it's already bytes.
                pass
            else:
                raise

        self.socket.send(message)


# end of class Server



client_connections = dict()

def client(address=None, port=None):
    ''' Factory function for a :class:`Client` instance.
    '''

    try:
        instance = client_connections[(address, port)]
    except KeyError:
        instance = Client(address, port)
        client_connections[(address, port)] = instance

    return instance



def shutdown():

    client_connections.clear()

    instances = Client.instances
    Client.instances = list()

    for reference in instances:
        instance = reference()

        if instance is not None:
            instance.stop()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
