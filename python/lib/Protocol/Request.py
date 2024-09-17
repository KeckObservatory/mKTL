''' Classes and methods implemented here implement the request/response
    aspects of the client/server API.
'''

import atexit
import json
import sys
import threading
import time
import traceback
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
        self.socket.setsockopt(zmq.LINGER, 0)
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

        result = self.socket.poll(self.timeout)
        if result == 0:
            raise zmq.ZMQError("no response received in %d ms" % (self.timeout))

        ack = self.socket.recv()
        ack_dict = json.loads(ack)
        ack_type = ack_dict['message']

        if ack_type == 'REP':
            # We were expecting an ACK, but we got the full response instead.
            # We could be hard-nosed about it and throw an exception, but the
            # intent of requiring the ACK (is the server alive?) is moot if we
            # have a proper full response.
            response = ack
            return response

        elif ack_type != 'ACK':
            raise ValueError('expected an ACK response, got ' + ack_type)

        response = self.socket.recv()
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
        # The 'inproc' usage here is analagous to a socketpair.

        port = 'tcp://*:' + str(port)
        notify_port = 'inproc://Request.Server.' + str(id(self))

        self.socket = zmq_context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.LINGER, 0)
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


    def req_ack(self, ident, request):

        id = request['id']

        ack = dict()
        ack['message'] = 'ACK'
        ack['id'] = id
        ack['time'] = time.time()
        ack = json.dumps(ack)
        ack = ack.encode()

        self.send(ident, ack)


    def req_incoming(self, ident, request):
        ''' All inbound requests are filtered through this method. It will
            parse the request as JSON into a Python dictionary, and hand it
            off to :func:`req_handler` for further processing. Error handling
            is managed here; if :func:`req_handler` raises an exception it
            will be packaged up and returned to the client as an error.

            :func:`req_handler` is expected to call :func:`req_ack` to
            acknowledge the incoming request; if :func:`req_handler` is
            returning a simple payload it will be packged into a REP response;
            no response will be issued if :func:`req_handler` returns None.
        '''

        error = None
        payload = None

        try:
            request = json.loads(request)
            payload = self.req_handler(ident, request)
        except:
            e_class, e_instance, e_traceback = sys.exc_info()
            error = dict()
            error['type'] = e_class.__name__
            error['text'] = str(e_instance)
            error['debug'] = traceback.format_exc()

        if payload is None and error is None:
            # The handler should only return None when no response is
            # immediately forthcoming-- the handler has invoked some
            # other processing chain that will issue a proper response.
            return

        response = dict()
        response['message'] = 'REP'
        response['id'] = request['id']
        response['time'] = time.time()

        if error is not None:
            response['error'] = error
        if payload is not None:
            response['data'] = payload

        response = json.dumps(response)
        response = response.encode()
        self.socket.send_multipart((ident, response))


    def req_handler(self, ident, request):
        ''' The default request handler is for debug purposes only, and is
            effectively a no-op.
        '''

        self.req_ack(ident, request)

        response = dict()
        response['message'] = 'REP'
        response['id'] = request['id']
        response['time'] = time.time()
        response = json.dumps(response)
        response = response.encode()

        self.socket.send_multipart((ident, response))

        # This default handler returns None, which indicates to req_incoming()
        # that it should not issue a response of its own.


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self.notify_in, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    ident, request = self.socket.recv_multipart()

                    try:
                        self.req_incoming(ident, request)
                    except:
                        ### Proper error handling needs to go here.
                        print(traceback.format_exc())

                else:
                    self.snooze()


    def send(self, ident, response):
        ''' Send a string response to the connected client.
        '''

        try:
            response = response.encode()
        except AttributeError:
            if hasattr(response, 'decode'):
                # Assume it's already bytes.
                pass
            else:
                raise

        self.socket.send_multipart((ident, response))


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
