''' Classes and methods implemented here implement the request/response
    aspects of the client/server API.
'''

import atexit
import threading
import weakref
import zmq
import zmq.utils.monitor


default_port = 10111
zmq_context = zmq.Context()


class Client:
    ''' Issue requests via a ZeroMQ DEALER socket and receive responses.
        Maintains a persistent connection to a single server; the default
        behavior is to connect to localhost on the default port.
    '''

    port = default_port
    timeout = 50

    def __init__(self, address=None, port=None):

        if address is None:
            address = 'localhost'

        if port is None:
            port = self.port

        port = str(port)
        server = "tcp://%s:%s" % (address, port)
        identity = "Request.Client.%d" % (id(self))

        self.connected = False
        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.identity = identity.encode()

        self.monitor = self.socket.get_monitor_socket()
        self.monitor_thread = threading.Thread(target=self.checkSocket)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        self.socket.connect(server)


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


    def send(self, request):
        ''' Send a string request to the connected server, and return the
            server's response.
        '''

        try:
            request = request.encode()
        except AttributeError:
            if hasattr(request, 'decode'):
                # Assume it's already bytes.
                pass
            else:
                raise

        self.socket.send(request)
        print('Request.Client sent: ' + repr(request))

        result = self.socket.poll(self.timeout)
        if result == 0:
            raise zmq.ZMQError("no response received in %d ms" % (self.timeout))

        response = self.socket.recv()
        print('Request.Client recv: ' + repr(response))

        completion = self.socket.recv()
        print('Request.Client recv: ' + repr(completion))

        return response


# end of class Client



class Server:
    ''' Receive requests via a ZeroMQ ROUTER socket, and respond to them. The
        default behavior is to listen for incoming requests on all available
        addresses on the default port.
    '''

    port = default_port
    instances = list()

    def __init__(self, port=None):

        if port is None:
            port = self.port

        # See the ZeroMQ man page for zmq_inproc for a full description of
        # the connection type. Example URL:
        #
        # http://api.zeromq.org/4-2:zmq-inproc
        #
        # The usage here is analagous to a socketpair.

        port = 'tcp://*:' + str(port)
        notify_port = 'inproc://Request.Server.' + str(id(self))

        self.socket = zmq_context.socket(zmq.ROUTER)
        self.socket.bind(port)

        self.notify_out = zmq_context.socket(zmq.PAIR)
        self.notify_in = zmq_context.socket(zmq.PAIR)

        self.notify_out.bind(notify_port)
        self.notify_in.connect(notify_port)

        self.shutdown = False
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

        Server.instances.append(weakref.ref(self))


    def run(self):

        counter = 0
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self.notify_in, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    ident, request = self.socket.recv_multipart()

                    print('Request.Server message from: ' + repr(ident))
                    print('Request.Server received: ' + repr(request))

                    response = "Request %d received" % (counter)
                    response = response.encode()
                    self.socket.send_multipart((ident, response))

                    response = "Request %d complete" % (counter)
                    response = response.encode()
                    self.socket.send_multipart((ident, response))
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


    def wake(self):
        self.notify_out.send_string('hello')


# end of class Server



def send(request, address=None, port=None):
    ''' Creates a :class:`Client` instance and invokes the :func:`Client.send`
        method.
    '''

    client = Client(address, port)
    response = client.send(request)
    return response


def shutdown():
    instances = Server.instances
    Server.instances = list()

    for reference in instances:
        instance = reference()

        if instance is not None:
            instance.stop()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
