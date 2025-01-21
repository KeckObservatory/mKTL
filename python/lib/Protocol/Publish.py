''' Classes and methods implemented here implement the publish/subscribe
    aspects of the client/server API.
'''

import atexit
import itertools
import threading
import traceback
import zmq

from . import Json
from .. import WeakRef

default_port = 10139
zmq_context = zmq.Context()


class Client:
    ''' Establish a ZeroMQ SUB connection to a ZeroMQ PUB socket and receive
        broadcasts; the default behavior is to connect to localhost on the
        default port.
    '''

    port = default_port

    def __init__(self, address=None, port=None):

        if address is None:
            address = 'localhost'

        if port is None:
            port = self.port

        port = str(port)
        server = "tcp://%s:%s" % (address, port)

        self.socket = zmq_context.socket(zmq.SUB)
        self.socket.connect(server)

        self.callback_all = list()
        self.callback_specific = dict()
        self.shutdown = False

        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def propagate(self, topic, message):
        ''' Invoke any/all callbacks registered via :func:`register` for
            a newly arrived message.
        '''

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

        ### Does this need to be fed into a pool of threads?
        ### So that one bad propagation doesn't slow everything?

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        pending = dict()

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    message = self.socket.recv()

                    # A message is either JSON-formatted or a binary blob.
                    # Parse any JSON now so that it only has to happen once;
                    # callbacks are expecting to receive a Python dictionary
                    # representing the parsed JSON.

                    # We could receive the two pieces of a bulk message in
                    # either order; in either case the message needs to be
                    # reconstructed from its two parts before being propagated
                    # to any subscribed clients.

                    topic, message = message.split(maxsplit=1)

                    if topic[:5] == b'bulk:':
                        message_id, bulk = message.split(maxsplit=1)
                        message_id = int(message_id)

                        topic = topic[5:]
                        key = (topic, message_id)

                        try:
                            previous = pending[key]
                        except KeyError:
                            pending[key] = bulk
                            continue
                        else:
                            # Reconstitute the final message.
                            message = previous
                            message['bulk'] = bulk
                            del pending[key]

                    else:
                        message = message.decode()
                        message = Json.loads(message)

                        try:
                            bulk = message['bulk']
                        except KeyError:
                            bulk = False

                        if bulk == True:
                            key = (topic, message['id'])
                            try:
                                previous = pending[key]
                            except KeyError:
                                pending[key] = message
                                continue
                            else:
                                # Reconstitute the final message.
                                message['bulk'] = bulk
                                del pending[key]

                    self.propagate(topic, message)


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

        # Someone that knows whether a given item has a bulk component should
        # decide whether to subscribe to the bulk-specific topic. We could
        # do it here, for every subscribed channel regardless of whether it
        # actually has a bulk component, but that seems inefficient.

        ### self.socket.setsockopt(zmq.SUBSCRIBE, b'bulk:' + topic)


# end of class Client



class Server:
    ''' Send broadcasts via a ZeroMQ PUB socket. The default behavior is to
        set up a listener on all available network interfaces on the default
        port.
    '''

    port = default_port
    pub_id_min = 0
    pub_id_max = 0xFFFFFFFF

    def __init__(self, port=None):

        if port is None:
            port = self.port

        port = 'tcp://*:' + str(port)

        self.socket = zmq_context.socket(zmq.PUB)
        self.socket.bind(port)

        self.pub_id_lock = threading.Lock()
        self.pub_id_reset()


    def pub_id_next(self):
        ''' Return the next publication identification number for subroutines to
            use when constructing a broadcast message.
        '''

        self.pub_id_lock.acquire()
        pub_id = next(self.pub_id)

        if pub_id >= self.pub_id_max:
            self.pub_id_reset()

            if pub_id > self.pub_id_max:
                # This shouldn't happen, but here we are...
                pub_id = self.pub_id_min
                next(self.pub_id)

        self.pub_id_lock.release()
        return pub_id


    def pub_id_reset(self):
        ''' Reset the publication identification number to the minimum value.
        '''

        self.pub_id = itertools.count(self.pub_id_min)


    def publish(self, message):
        ''' A *message* is a Python dictionary ready to be converted to a
            JSON byte string and broadcast.

            The 'id' field in the *message*, if specified, will be overwritten.

            If the 'bulk' field is present in the *message* it must be a byte
            sequence, and will be sent as a separate message to any listeners.
        '''

        pub_id = self.pub_id_next()
        topic = message['name']

        message['id'] = pub_id

        try:
            bulk = message['bulk']
        except KeyError:
            bulk = None
        else:
            message['bulk'] = True

        prefix = topic + ' '
        prefix = prefix.encode()

        message = prefix + Json.dumps(message)
        self.socket.send(message)

        if bulk is not None:
            prefix = 'bulk:' + topic + ' ' + str(pub_id) + ' '
            prefix = prefix.encode()

            bulk_payload = prefix + bulk
            self.socket.send(bulk_payload)


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


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
