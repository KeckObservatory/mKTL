''' Classes and methods implemented here implement the request/response
    aspects of the client/server API.
'''

import atexit
import socket
import threading
import zmq
import zmq.utils.monitor


default_port = 10111
zmq_context = zmq.Context()


class Client:
    ''' Issue requests via a ZeroMQ REQ socket and receive responses. Maintains
        a persistent connection to a single server; the default behavior is to
        connect to localhost on the default port.
    '''

    port = default_port
    grace = 5

    def __init__(self, address=None, port=None):

        if address is None:
            address = 'localhost'

        if port is None:
            port = self.port

        port = str(port)
        server = "tcp://%s:%s" % (address, port)

        self.socket = zmq_context.socket(zmq.REQ)
        self.socket.connect(server)


    def send(self, request):
        ''' Send a string request to the connected server, and return the
            server's response.
        '''

        socket = self.socket

        ### This needs to check whether the client is properly connected,
        ### and raise an exception if it is not.

        socket.send_string(request)
        print('Request.Client sent: ' + repr(request))
        response = socket.recv()
        print('Request.Client recv: ' + repr(response))

        return response


# end of class Client



class Server:
    ''' Receive requests via a ZeroMQ REP socket, and respond to them. The
        default behavior is to listen for incoming requests on all available
        addresses on the default port.
    '''

    port = default_port
    instances = list()

    def __init__(self, port=None):

        if port is None:
            port = self.port

        port = 'tcp://*:' + str(port)
        notify_port = 'inproc://Client_' + str(id(self))

        self.socket = zmq_context.socket(zmq.REP)
        self.socket.bind(port)

        self.notify_in = zmq_context.socket(zmq.PAIR)
        self.notify_out = zmq_context.socket(zmq.PAIR)
        self.notify_out.bind(notify_port)
        self.notify_in.connect(notify_port)

        self.shutdown = False
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

        Server.instances.append(self)


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
                    print('Request.Server received: ' + repr(request))
                    self.socket.send_string("Request %d received" % (counter))
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
    for instance in Server.instances:
        instance.stop()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
