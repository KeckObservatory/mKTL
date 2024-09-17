
import itertools
import json
import sys
import threading
import time
import traceback
import zmq

zmq_context = zmq.Context()


class Base:
    ''' The :class:`Base` proxy establishes a few common routines and
        the template for what any subclasses need to implement in order
        to successfully communicate with a standard client.
    '''

    pub_id_min = 0
    pub_id_max = 0xFFFFFFFF

    worker_count = 10

    def __init__(self, req, pub):
        ''' The *req* and *pub* values are interprocess addresses that the
            controlling daemon will use to communicate with this proxy instance.
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


    def publish(self, bytes):
        ''' Publish bytes on the wire.
        '''

        self.pub_socket.send(bytes)


    def pub_id_next(self):
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

        id = request['id']

        ack = dict()
        ack['message'] = 'ACK'
        ack['id'] = id
        ack['time'] = time.time()
        ack = json.dumps(ack)
        ack = ack.encode()

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
        ''' There are two ident values as a result of the daisy-chaining of
            ROUTER/DEALER connections: one is from the subprocess interface,
            the second is from the worker pool interface.
        '''

        error = None
        payload = None

        try:
            request = json.loads(request)
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

        response = json.dumps(response)
        response = response.encode()
        socket.send_multipart((ident, response))


    def req_set(self, key, value):
        ''' Set the value of a key. This routine is expected to block until
            completion of the request.
        '''

        raise NotImplmentedError('must be implemented by the subclass')


    def worker_main(self):

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
