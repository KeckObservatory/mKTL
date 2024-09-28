''' Classes and methods implemented here implement the request/response
    aspects of the client/server API.
'''

import atexit
import itertools
import json
import sys
import threading
import time
import traceback
import weakref
import zmq


default_port = 10111
zmq_context = zmq.Context()


class Client:
    ''' Issue requests via a ZeroMQ DEALER socket and receive responses.
        Maintains a persistent connection to a single server; the default
        behavior is to connect to localhost on the default port.
    '''

    port = default_port
    timeout = 0.05

    req_id_min = 0
    req_id_max = 0xFFFFFFFF

    def __init__(self, address=None, port=None):

        self.req_id_lock = threading.Lock()
        self.req_id_reset()

        if address is None:
            address = 'localhost'

        if port is None:
            port = self.port

        port = str(port)
        server = "tcp://%s:%s" % (address, port)
        identity = "Request.Client.%d" % (id(self))

        self.pending = dict()

        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.identity = identity.encode()
        self.socket.connect(server)

        self.pending_thread = threading.Thread(target=self.run)
        self.pending_thread.daemon = True
        self.pending_thread.start()


    def req_id_next(self):
        ''' Return the next request identification number for subroutines to
            use when constructing a request.
        '''

        self.req_id_lock.acquire()
        req_id = next(self.req_id)

        if req_id >= self.req_id_max:
            self.req_id_reset()

            if req_id > self.req_id_max:
                # This shouldn't happen, but here we are...
                req_id = self.req_id_min
                next(self.req_id)

        self.req_id_lock.release()
        return req_id


    def req_id_reset(self):
        ''' Reset the request identification number to the minimum value.
        '''

        self.req_id = itertools.count(self.req_id_min)


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        while True:
            sockets = poller.poll(10000)
            for active, flag in sockets:
                if self.socket == active:
                    response = self.socket.recv()

                    ### This assumes the response is JSON. This won't work
                    ### in the bulk data case.

                    response_dict = json.loads(response)
                    response_id = response_dict['id']

                    try:
                        pending = self.pending[response_id]
                    except KeyError:
                        # No further processing requested.
                        continue

                    response_type = response_dict['message']
                    if response_type == 'ACK':
                        pending.complete_ack(response_dict)
                    else:
                        pending.complete(response_dict)
                        del self.pending[response_id]


    def send(self, request, response=True, bulk=None):
        ''' A *request* is a Python dictionary ready to be converted to a JSON
            byte string and sent to the connected server. If *response* is True
            a :class:`PendingRequest` instance will be returned that a client
            can use to wait on for further notification. Set *response* to any
            other value to indicate a return response is not of interest.

            The 'id' field in the *request*, if specified, will be overwritten.

            If the *bulk* field is provided it must be a byte sequence that
            will be sent as a separate message to the connected daemon.
        '''

        req_id = self.req_id_next()
        name = request['name']

        if response == True:
            pending = PendingRequest()
            self.pending[req_id] = pending

        request['id'] = req_id
        if bulk is not None:
            request['bulk'] = True

        request = json.dumps(request)
        request = request.encode()
        self.socket.send(request)

        if bulk is not None:
            prefix = name + ';bulk ' + str(req_id) + ' '
            prefix = prefix.encode()

            bulk_payload = prefix + bulk
            self.socket.send(bulk_payload)


        if response != True:
            return

        ack = pending.wait_ack(self.timeout)

        if ack is None:
            raise zmq.ZMQError("no response received in %.2fs" % (self.timeout))

        ack_type = ack['message']

        if ack_type == 'REP':
            # We were expecting an ACK, but we got the full response instead.
            # We could be hard-nosed about it and throw an exception, but the
            # intent of requiring the ACK (is the server alive?) is moot if we
            # have a proper full response.
            pending.complete(ack)

        elif ack_type != 'ACK':
            raise ValueError('expected an ACK response, got ' + ack_type)

        return pending


# end of class Client



class PendingRequest:
    ''' The :class:`PendinglRequest` provides a very thin wrapper around a
        :class:`threading.Event` that can be used to signal the internal
        caller that the request has been handled. It also provides a vehicle
        for the response to be passed to the caller.
    '''

    def __init__(self):
        self.ack = None
        self.rep = None

        self.event_ack = threading.Event()
        self.event_rep = threading.Event()


    def complete_ack(self, ack):
        self.ack = ack
        self.event_ack.set()


    def complete(self, response):
        ''' If a response to a pending request arrives the :class:`Client`
            instance will check whether the response is of interest, and if
            it is, call :func:`complete` to indicate the response has arrived.
        '''

        self.rep = response

        if self.ack is None:
            self.ack = response
            self.event_ack.set()

        self.event_rep.set()


    def wait_ack(self, timeout):
        self.event_ack.wait(timeout)
        return self.ack


    def wait(self, timeout=60):
        ''' The invoker of the :class:`PendingRequest` will call :func:`wait`
            to block until the request has been handled.
        '''

        self.event_rep.wait(timeout)
        return self.rep


# end of class PendingRequest



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

        self.socket = zmq_context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.bind(port)

        self.shutdown = False
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

        Server.instances.append(weakref.ref(self))


    def req_ack(self, ident, request):
        ''' Acknowledge the incoming request. The client is expecting an
            immediate ACK for all request types, including errors; this is
            how a client knows whether a daemon is online to respond to its
            request.
        '''

        id = request['id']

        ack = dict()
        ack['message'] = 'ACK'
        ack['id'] = id
        ack['time'] = time.time()
        ack = json.dumps(ack)
        ack = ack.encode()

        self.send(ident, ack)


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


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

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



def send(request, address=None, port=None, bulk=None):
    ''' Creates a :class:`Client` instance and invokes the :func:`Client.send`
        method. This method blocks until the completion of the request.
    '''

    connection = client(address, port)
    pending = connection.send(request, bulk)
    response = pending.wait()
    return response


def shutdown():
    client_connections.clear()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
