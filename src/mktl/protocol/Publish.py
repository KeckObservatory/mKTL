""" Classes and methods implemented here implement the publish/subscribe
    aspects of the client/server API.
"""

import atexit
import itertools
import threading
import traceback
import zmq

from . import Json
from . import Message
from .. import WeakRef

minimum_port = 10139
maximum_port = 13679
zmq_context = zmq.Context()


class Client:
    """ Establish a ZeroMQ SUB connection to a ZeroMQ PUB socket and receive
        broadcasts.
    """

    def __init__(self, address, port):

        port = int(port)
        self.port = port
        server = "tcp://%s:%d" % (address, port)

        self.socket = zmq_context.socket(zmq.SUB)
        self.socket.connect(server)

        self.callback_all = list()
        self.callback_specific = dict()
        self.shutdown = False

        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def propagate(self, topic, message):
        """ Invoke any/all callbacks registered via :func:`register` for
            a newly arrived message.
        """

        # Do nothing if nobody is listening.

        if self.callback_all or self.callback_specific:
            pass
        else:
            return


        # Handle the case where a callback is registered for any/all messages.

        invalid = list()
        references = self.callback_all

        for reference in references:
            callback = reference()

            if callback is None:
                invalid.append(reference)
                continue

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
                continue

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
        """ Register a callback that will be invoked every time a new broadcast
            message arrives. If no topic is specified the callback will be
            invoked for all broadcast messages. The topic is case-sensitive and
            must be an exact match. Any callbacks registered in this fashion
            should be as lightweight as possible, as there is a single thread
            processing all arriving broadcast messages.

            :func:`subscribe` will be invoked for any/all topics registered
            with a callback, it does not need to be called separately.
        """

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
            topic = topic + '.'
            topic = topic.encode()

            try:
                callbacks = self.callback_specific[topic]
            except:
                callbacks = list()
                self.callback_specific[topic] = callbacks

            callbacks.append(reference)
            self.subscribe(topic)


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    parts = self.socket.recv_multipart()
                    self._pub_incoming(parts)


    def _pub_incoming(self, parts):

        topic = parts[0]
        their_version = parts[1]

        if their_version != Message.version:
            ### Maybe we should occasionally log a version mismatch.
            ### For now it's being dropped on the floor.
            return

        payload = parts[2]
        bulk = parts[3]

        if payload == b'':
            payload = None
        else:
            payload = Json.loads(payload)

        if bulk == b'':
            bulk = None

        broadcast = Message.Message(None, 'PUB', topic, payload, bulk)
        self.propagate(topic, broadcast)


    def subscribe(self, topic):
        """ ZeroMQ subscriptions are based on a topic. Filtering of messages
            happens on the server side, depending on what a client is subscribed
            to. A client can subscribe to all messages by providing the empty
            string as the topic.
        """

        try:
            topic.decode
        except AttributeError:
            topic = str(topic)
            topic = topic.encode()

        self.socket.setsockopt(zmq.SUBSCRIBE, topic)


# end of class Client



class Server:
    """ Send broadcasts via a ZeroMQ PUB socket. The default behavior is to
        set up a listener on all available network interfaces on the first
        available automatically assigned port. The *avoid* set enumerates port
        numbers that should not be automatically assigned; this is ignored if a
        fixed *port* is specified.

        The port variables associated with a :class:`Server` instance is a key
        pieces of the provenance for an mKTL daemon.

        :ivar port: The port on which this server is listening for connections.
    """

    def __init__(self, port=None, avoid=set()):

        self.socket = zmq_context.socket(zmq.PUB)

        # If the port is set, use it; otherwise, look for the first available
        # port within the default range.

        if port is None:
            minimum = minimum_port
            maximum = maximum_port
        else:
            port = int(port)
            minimum = port
            maximum = port

        avoided = list()
        trial = minimum
        while trial <= maximum:
            if port is None and trial in avoid:
                avoided.append(trial)
                trial += 1
                continue

            listen_address = 'tcp://*:' + str(trial)
            try:
                self.socket.bind(listen_address)
            except zmq.error.ZMQError:
                # Assume this port is in use.
                trial += 1
            else:
                break

        if trial > maximum and len(avoided) > 0:
            # There are a lot of ports in the default range; surely one of
            # them is available? Re-take something if it is not in use.

            reuse = False
            for trial in avoided:
                listen_address = 'tcp://*:' + str(trial)
                try:
                    self.socket.bind(listen_address)
                except zmq.error.ZMQError:
                    # Assume this port is in use.
                    continue
                else:
                    reuse = True
                    break

            if reuse == False:
                # No luck. Reassert the failure condition checked below.
                trial = maximum + 1


        if trial > maximum:
            if port is None:
                error = "no ports available in range %d:%d" % (minimum, maximum)
            else:
                error = 'port already in use: ' + str(port)
            raise zmq.error.ZMQError(error)

        self.port = trial


    def publish(self, message):
        """ A *message* is a :class:`Message.Message` instance intended for
            broadcast to any subscribers.
        """

        parts = message.publish_multiparts()
        self.socket.send_multipart(parts)


# end of class Server



client_connections = dict()

def client(address, port):
    """ Factory function for a :class:`Client` instance. Use of this method is
        encouraged to streamline re-use of established connections.
    """

    try:
        instance = client_connections[(address, port)]
    except KeyError:
        instance = Client(address, port)
        client_connections[(address, port)] = instance

    return instance



def shutdown():
    client_connections.clear()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
