''' Classes and methods implemented here implement the publish/subscribe
    aspects of the client/server API.
'''

import atexit
import threading
import weakref
import zmq
import zmq.utils.monitor


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

        self.shutdown = False
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

        self.socket.connect(server)

        Client.instances.append(weakref.ref(self))


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


    def run(self):

        counter = 0
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self.notify_in, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    request = self.socket.recv()
                    print('Publish.Client received: ' + repr(request))
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
        ''' ZeroMQ subscriptions are based on a "topic" number. The number
            is an integer.
        '''

        topic = int(topic)
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
        print('Publish.Server sent: ' + repr(message))


    def wake(self):
        self.notify_out.send_string('hello')


# end of class Server



def shutdown():
    instances = Client.instances
    Client.instances = list()

    for reference in instances:
        instance = reference()

        if instance is not None:
            instance.stop()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
