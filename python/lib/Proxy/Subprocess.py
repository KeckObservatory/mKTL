''' Common routines and classes for use as part of a proxy subprocess. The
    subprocess is responsible for handling incoming requests managed by the
    proxy daemon; this is where the translation to any other protocol, such
    as KTL or EPICS, will occur.
'''

import itertools
import sys
import threading
import time
import traceback
import uuid
import zmq

from ..Protocol import Json
from ..Config import Hash

zmq_context = zmq.Context()


class Base:
    ''' The :class:`Base` proxy establishes a few common routines and a template
        for any subclasses focused on a specific protocol.

        The parent daemon establishes a pair of ZeroMQ sockets for our use;
        the PUB/SUB component is simple, any events published here are proxied
        directly out to external connections by the parent daemon. The REQ/REP
        component involves a worker pool to service incoming requests; this is
        a neat match for the DEALER/ROUTER ZeroMQ socket type, and results in
        round-robin handling of requests among the worker pool.
    '''

    pub_id_min = 0
    pub_id_max = 0xFFFFFFFF

    worker_count = 10

    def __init__(self, req, pub):
        ''' The *req* and *pub* values are interprocess addresses that the
            proxy daemon will estalbish for communication with this subprocess.
        '''

        self.pub = pub
        self.pub_id_lock = threading.Lock()
        self.pub_id_reset()
        self.pub_socket = zmq_context.socket(zmq.PUB)
        self.pub_socket.bind(pub)

        self.req = req

        self.worker_shutdown = False

        for thread_number in range(self.worker_count):
            thread = threading.Thread(target=self.worker_main)
            thread.daemon = True
            thread.start()


    def hash(self, keys):
        return Hash.hash(keys)


    def publish(self, message, bulk=None):
        ''' A *message* is a Python dictionary ready to be converted to a
            JSON byte string and broadcast.

            The 'id' field in the *message*, if specified, will be overwritten.

            If the *bulk* field is provided it must be a byte sequence that
            will be sent as a separate message to the connected daemon.
        '''

        pub_id = self.pub_id_next()
        topic = message['name']

        message['id'] = pub_id
        if bulk is not None:
            message['bulk'] = True

        prefix = topic + ' '
        prefix = prefix.encode()
        message = prefix + Json.dumps(message)

        self.pub_socket.send(message)

        if bulk is not None:
            prefix = 'bulk:' + topic + ' ' + str(pub_id) + ' '
            prefix = prefix.encode()

            bulk_payload = prefix + bulk
            self.pub_socket.send(bulk_payload)


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


    def req_ack(self, socket, ident, request):
        ''' Acknowledge the incoming request. The client is expecting an
            immediate ACK for all request types, including errors; this is how a
            client knows whether a daemon is online to respond to its request.
            The proxy daemon expects any requests destined for a subprocess to
            be acknowledged by that subprocess, not by the parent daemon.

            This method closely mirrors :func:`Request.Server.req_ack`, though
            in the :class:`Base` case the socket is a required argument, since
            it is owned by a worker background thread.
        '''

        id = request['id']

        ack = dict()
        ack['message'] = 'ACK'
        ack['id'] = id
        ack['time'] = time.time()
        ack = Json.dumps(ack)

        socket.send_multipart((ident, ack))


    def req_config(self, name):
        ''' Retrieve the current configuration of this store.
        '''

        raise NotImplmentedError('must be implemented by the subclass')


    def req_get(self, key):
        ''' Retrieve the value of a key. Return the value as a tuple: the first
            component is the value dictionary, the second is a data blob. Both
            components will be translated to bytes by the calling routine.
        '''

        raise NotImplmentedError('must be implemented by the subclass')


    def req_handler(self, socket, ident, request):
        ''' Acknowledge the incoming request. The client is expecting an
            immediate ACK for all request types, including errors; any daemon
            passing a request to a subprocess expects that subprocess to
            generate all further messages destined for the requesting client.
        '''

        self.req_ack(socket, ident, request)

        type = request['request']

        if type == 'GET':
            payload = self.req_get(request)
        elif type == 'SET':
            payload = self.req_set(request)
        elif type == 'CONFIG':
            payload = self.req_config(request)
        else:
            raise ValueError('unhandled request type: ' + type)

        return payload


    def req_incoming(self, socket, ident, request):
        ''' All inbound requests are filtered through this method. It will
            parse the request as JSON into a Python dictionary, and hand it
            off to :func:`req_handler` for further processing. Error handling
            is managed here; if :func:`req_handler` raises an exception it
            will be packaged up and returned to the client as an error.

            :func:`req_handler` is expected to call :func:`req_ack` to
            acknowledge the incoming request; if :func:`req_handler` is
            returning a simple payload it will be packged into a REP response;
            no response will be issued if :func:`req_handler` returns None.

            This method closely mirrors :func:`Request.Server.req_incoming`,
            though in the :class:`Base` case the socket is a required argument,
            since it is owned by a worker background thread.
        '''

        error = None
        payload = None

        try:
            request = Json.loads(request)
            payload = self.req_handler(socket, ident, request)
        except:
            e_class, e_instance, e_traceback = sys.exc_info()
            error = dict()
            error['type'] = e_class.__name__
            error['text'] = str(e_instance)
            error['debug'] = traceback.format_exc()


        response = dict()
        response['message'] = 'REP'
        response['id'] = request['id']
        response['time'] = time.time()

        if error is not None:
            response['error'] = error
        if payload is not None:
            response['data'] = payload

        response = Json.dumps(response)
        socket.send_multipart((ident, response))


    def req_set(self, key, value):
        ''' Set the value of a key. This routine is expected to block until
            completion of the request; this will wholly occupy one worker
            thread for the duration of the request.
        '''

        raise NotImplmentedError('must be implemented by the subclass')


    def uuid(self, identifier):
        ''' Generate a deterministic UUID based on the provided *identifier*.
            For any given *identifier*, the returned UUID is always the same;
            it is effectively a hash of the identifier.
        '''

        return str(uuid.uuid5(uuid.NAMESPACE_DNS, identifier))


    def worker_main(self):
        ''' This is the 'main' method for the worker threads responsible for
            handling incoming requests. With the way the ROUTER/DEALER sockets
            are connected, each request will be allocated to a worker on a
            round-robin basis; first request goes to thread 1, second to
            thread 2, and so on.

            The task of a worker thread is limited: receive a request, and
            feed it to :func:`req_incoming` for processing.
        '''

        socket = zmq_context.socket(zmq.ROUTER)
        socket.connect(self.req)

        poller = zmq.Poller()
        poller.register(socket, zmq.POLLIN)

        while True:
            if self.worker_shutdown == True:
                break

            sockets = poller.poll(10000)

            for active,flag in sockets:
                if socket == active:
                    request = socket.recv_multipart()

                    try:
                        self.req_incoming(socket, *request)
                    except:
                        ### Proper error handling needs to go here.
                        print(traceback.format_exc())


# end of class Base


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
