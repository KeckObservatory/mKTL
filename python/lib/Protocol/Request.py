''' Classes and methods implemented here implement the request/response
    aspects of the client/server API.
'''

import atexit
import itertools
import queue
import sys
import threading
import time
import traceback
import zmq

from . import Json


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
        self.address = address
        self.port = port

        self.pending = dict()

        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.identity = identity.encode()
        self.socket.connect(server)
        self.socket_lock = threading.Lock()

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

                    # Check for bulk data first, since it cannot be processed
                    # as JSON.

                    if response[:5] == b'bulk:':
                        topic, response_id, bulk = response.split(maxsplit=2)
                        response_id = int(response_id)

                        try:
                            pending = self.pending[response_id]
                        except KeyError:
                            # No further processing required.
                            continue

                        pending.partial(bulk=bulk)
                        continue


                    # All other responses are expected to be JSON.

                    response_dict = Json.loads(response)
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
                        try:
                            bulk = response_dict['bulk']
                        except KeyError:
                            bulk = False

                        if bulk == True:
                            done = pending.partial(response=response_dict)
                            if done == True:
                                del self.pending[response_id]
                        else:
                            pending.complete(response_dict)
                            del self.pending[response_id]


    def send(self, request, response=True):
        ''' A *request* is a Python dictionary ready to be converted to a JSON
            byte string and sent to the connected server. If *response* is True
            a :class:`Pending` instance will be returned that a client can use
            to wait on for further notification. Set *response* to any other
            value to indicate a return response is not of interest.

            The 'id' field in the *request*, if specified, will be overwritten.

            If the 'bulk' field is present in the *request* it must be a byte
            sequence, and will be sent as a separate message to the connected
            daemon.
        '''

        req_id = self.req_id_next()
        name = request['name']

        if response == True:
            pending = Pending()
            self.pending[req_id] = pending

        request['id'] = req_id

        try:
            bulk = request['bulk']
        except KeyError:
            bulk = None
        else:
            request['bulk'] = True

        request = Json.dumps(request)
        self.socket_lock.acquire()
        self.socket.send(request)

        if bulk is not None:
            prefix = 'bulk:' + name + ' ' + str(req_id) + ' '
            prefix = prefix.encode()

            bulk_request = prefix + bulk
            self.socket.send(bulk_request)
        self.socket_lock.release()


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



class Pending:
    ''' The :class:`Pending` provides a very thin wrapper around a
        :class:`threading.Event` that can be used to signal the internal
        caller that the request has been handled. It also provides a vehicle
        for the response to be passed to the caller.
    '''

    def __init__(self):
        self.ack = None
        self.bulk = None
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


    def partial(self, response=None, bulk=None):
        ''' A response may come in two pieces. This is effectively a two-step
            version of :func:`complete`, where there should be two calls to
            :func:`partial` before a request is complete. This method will
            return True when both responses have been received.
        '''

        if response is not None:
            self.rep = response

            if self.ack is None:
                self.ack = response
                self.event_ack.set()

        if bulk is not None:
            self.bulk = bulk

        if self.rep is not None and self.bulk is not None:
            self.rep['bulk'] = self.bulk
            self.event_rep.set()
            return True


    def wait_ack(self, timeout):
        self.event_ack.wait(timeout)
        return self.ack


    def wait(self, timeout=60):
        ''' The invoker of the :class:`Pending` will call :func:`wait`
            to block until the request has been handled.
        '''

        self.event_rep.wait(timeout)
        return self.rep


# end of class Pending



class Server:
    ''' Receive requests via a ZeroMQ ROUTER socket, and respond to them. The
        default behavior is to listen for incoming requests on all available
        addresses on the default port.
    '''

    port = default_port
    worker_count = 10

    def __init__(self, port=None):

        if port is None:
            port = self.port

        port = 'tcp://*:' + str(port)

        self.socket = zmq_context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.bind(port)
        self.socket_lock = threading.Lock()

        # The use of worker threads and a synchronization primitive is something
        # like a 10-20% hit in performance compared to using a single thread.
        # Multiple worker threads allow for a request to block until completion.

        # Using a deque and a synchronization construct (such as a Condition)
        # is similar in performance to using a SimpleQueue. Using a fast
        # Condition implementation might make it worth the trouble, but the
        # one in the threading module is slow enough that it's not any better.

        # Using ZeroMQ sockets to implement a multithreaded queue was much
        # slower (in the absence of multiprocessing). The use of a lock is
        # necessary when sharing a ZeroMQ socket across threads as ZeroMQ
        # makes no attempt to be thread-safe.

        self.queue = queue.SimpleQueue()

        self.shutdown = False
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

        self.workers = list()
        for thread_number in range(self.worker_count):
            thread = threading.Thread(target=self.worker_main)
            thread.daemon = True
            thread.start()
            self.workers.append(thread)


    def req_ack(self, socket, lock, ident, request):
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
        ack = Json.dumps(ack)

        lock.acquire()
        socket.send_multipart((ident, ack))
        lock.release()


    def req_handler(self, socket, lock, ident, request):
        ''' The default request handler is for debug purposes only, and is
            effectively a no-op.
        '''

        self.req_ack(socket, lock, ident, request)

        response = dict()
        response['message'] = 'REP'
        response['id'] = request['id']
        response['time'] = time.time()
        response = Json.dumps(response)

        lock.acquire()
        socket.send_multipart((ident, response))
        lock.release()

        # This default handler returns None, which indicates to req_incoming()
        # that it should not issue a response of its own.


    def req_incoming(self, socket, lock, ident, request):
        ''' All inbound requests are filtered through this method. It will
            parse the request as JSON into a Python dictionary, and hand it
            off to :func:`req_handler` for further processing. Error handling
            is managed here; if :func:`req_handler` raises an exception it
            will be packaged up and returned to the client as an error.

            :func:`req_handler` is expected to call :func:`req_ack` to
            acknowledge the incoming request; if :func:`req_handler` is
            returning a simple payload it will be packged into a REP response;
            the payload is always a dictionary, containing at minimum a 'data'
            value, and an optional 'bulk' value. No response will be issued if
            :func:`req_handler` returns None.
        '''

        error = None
        payload = None

        try:
            request = Json.loads(request)
            payload = self.req_handler(socket, lock, ident, request)
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
            response['data'] = payload['data']

            try:
                bulk = payload['bulk']
            except KeyError:
                pass
            else:
                response['bulk'] = True
                name = request['name']
                id = str(response['id'])
                prefix = 'bulk:' + name + ' ' + id + ' '
                prefix = prefix.encode()

                bulk_response = prefix + bulk
                lock.acquire()
                self.socket.send_multipart((ident, bulk_response))
                lock.release()


        response = Json.dumps(response)
        lock.acquire()
        self.socket.send_multipart((ident, response))
        lock.release()


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    ident, request = self.socket.recv_multipart()
                    self.queue.put((self.socket, self.socket_lock, ident, request))


    def worker_main(self):
        ''' This is the 'main' method for the worker threads responsible for
            handling incoming requests. The task of a worker thread is limited:
            receive a request, and feed it to :func:`req_incoming` for
            processing. Multiple threads are allocated to this function to
            allow for long-duration requests to be handled gracefully without
            jamming up the processing of subsequent requests; simple round-robin
            allocation of threads, as done by ROUTER/DEALER and PUSH/PULL, do
            not alter their allocation of inbound messages if a thread is
            already busy.
        '''

        while self.shutdown == False:
            try:
                dequeued = self.queue.get(timeout=300)
            except queue.Empty:
                continue

            if dequeued is None:
                continue

            try:
                self.req_incoming(*dequeued)
            except:
                ### Proper error handling needs to go here.
                print(traceback.format_exc())

        # Make sure the queue has something in it to wake up the other
        # worker threads if we're doing a controlled shutdown.

        self.queue.put(None)


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



def send(request, address=None, port=None):
    ''' Creates a :class:`Client` instance and invokes the :func:`Client.send`
        method. This method blocks until the completion of the request.
    '''

    connection = client(address, port)
    pending = connection.send(request)
    response = pending.wait()
    return response


def shutdown():
    client_connections.clear()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
