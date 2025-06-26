""" Classes and methods implemented here implement the request/response
    aspects of the client/server API.
"""

import atexit
import itertools
import queue
import socket
import sys
import threading
import time
import traceback
import zmq

from . import Json
from . import Message

minimum_port = 10079
maximum_port = 13679
zmq_context = zmq.Context()


class Client:
    """ Issue requests via a ZeroMQ DEALER socket and receive responses.
        Maintains a persistent connection to a single server; the *address*
        and *port* number must be specified.
    """

    timeout = 0.05

    def __init__(self, address, port):

        port = int(port)
        self.port = port
        self.address = address

        server = "tcp://%s:%d" % (address, port)
        identity = "Request.Client.%d" % (id(self))

        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.identity = identity.encode()
        self.socket.connect(server)
        self.socket_lock = threading.Lock()

        self.pending = dict()
        self.pending_thread = threading.Thread(target=self.run)
        self.pending_thread.daemon = True
        self.pending_thread.start()


    def _rep_incoming(self, parts):
        """ A client only receives two types of messages from the remote side:
            an ACK, or a REP. The response payload, if any, is handed back to
            the relevant :class:`Message.Request` instance for any further
            handling by the original caller.
        """

        their_version = parts[0]

        if their_version != Message.version:
            payload = dict()
            error = dict()
            error['type'] = 'RuntimeError'
            error['text'] = "message is mKTL protocol %s, recipient expects %s" % (repr(their_version), repr(Message.version))
            payload['error'] = error
            response_type = b'REP'
            bulk = b''
        else:
            response_type = parts[2]
            #target = parts[3]
            payload = parts[4]
            bulk = parts[5]

        # This could still blow up if the version doesn't match-- the id may
        # be in a different message part-- but we have to try, otherwise
        # there's no way to pass the error back to the original caller.

        response_id = parts[1]

        try:
            pending = self.pending[response_id]
        except KeyError:
            # No further processing required.
            return

        if response_type == b'ACK':
            pending._complete_ack()
            return

        ### This might be a good place to log anything other than a REP
        ### response type.

        if payload == b'':
            payload = None
        else:
            payload = Json.loads(payload)

        if bulk == b'':
            bulk = None

        pending._complete(payload, bulk)
        del self.pending[response_id]


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        while True:
            sockets = poller.poll(10000)
            for active, flag in sockets:
                if self.socket == active:
                    parts = self.socket.recv_multipart()
                    self._rep_incoming(parts)


    def send(self, message):
        """ A *message* is a fully populated class:`Message.Request` instance,
            which normalizes the arguments that will be sent via this method
            as a multi-part message. The message will also be used for
            notification of any/all responses from the remote end; this method
            will block while waiting for the ACK request, but the caller is
            free to decide whether to block or wait for the full response.
        """

        parts = message.to_parts()
        self.pending[message.id] = message

        self.socket_lock.acquire()
        self.socket.send_multipart(parts)
        self.socket_lock.release()

        ack = message.wait_ack(self.timeout)

        if ack == False:
            raise zmq.ZMQError("no response received in %.2fs" % (self.timeout))


# end of class Client



class Server:
    """ Receive requests via a ZeroMQ ROUTER socket, and respond to them. The
        default behavior is to listen for incoming requests on our locally
        known fully qualified domain name, on the first available automatically
        assigned port. The *avoid* set enumerates port numbers that should
        not be automatically assigned; this is ignored if a fixed *port* is
        specified.

        The hostname and port variables associated with a :class:`Server`
        instance are key pieces of the provenance for an mKTL daemon.

        :ivar hostname: The hostname on which this server can be contacted.
        :ivar port: The port on which this server is listening for connections.
    """

    worker_count = 10

    def __init__(self, hostname=None, port=None, avoid=set()):

        # The hostname is set and stored, but not used, as we are going to
        # listen on every available interface.

        if hostname is None:
            hostname = socket.getfqdn()

        self.hostname = hostname
        self.socket = zmq_context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket_lock = threading.Lock()

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
            thread = threading.Thread(target=self._worker_main)
            thread.daemon = True
            thread.start()
            self.workers.append(thread)


    def req_ack(self, socket, lock, ident, parts):
        """ Acknowledge the incoming request. The client is expecting an
            immediate ACK for all request types, including errors; this is
            how a client knows whether a daemon is online to respond to its
            request.
        """

        ### Maybe these routines should be passing around a Message instance?
        request_id = parts[0]

        ack = dict()
        ack['time'] = time.time()

        message = Message.Message(request_id, 'ACK', payload=ack)
        parts = (ident,) + message.to_parts()
        lock.acquire()
        socket.send_multipart(parts)
        lock.release()


    def req_handler(self, socket, lock, ident, parts):
        """ The default request handler is for debug purposes only, and is
            effectively a no-op. :class:`mktl.Daemon.Store` leverages a
            custom subclass of :class:`Server` that properly handles specific
            types of requests, since it needs to be aware of the actual
            structure of what's happening in the daemon code.
        """

        self.req_ack(socket, lock, ident, parts)

        version = Message.version
        request_id = parts[0]
        request_type = parts[1]
        target = parts[2]
        request = parts[3]
        bulk = parts[4]

        response = dict()
        response['time'] = time.time() ## This should be the value creation time

        message = Message.Message(request_id, 'REP', target, response)
        parts = (ident,) + message.to_parts()

        lock.acquire()
        socket.send_multipart(parts)
        lock.release()

        # This default handler returns None, which indicates to req_incoming()
        # that it should not issue a response of its own.


    def req_incoming(self, socket, lock, parts):
        """ All inbound requests are filtered through this method. It will
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
        """

        error = None
        payload = None

        ### This all needs to move into a try/except block so that any
        ### exceptions are passed back to the originator of the request.
        ### Presumably that means calling something like _req_incoming().

        ident = parts[0]
        their_version = parts[1]

        if their_version != Message.version:
            raise ValueError("message is mKTL protocol %s, recipient is %s" % (repr(their_version), repr(Message.version)))

        request_id = parts[2]
        request_type = parts[3]
        target = parts[4]
        request = parts[5]
        bulk = parts[6]

        request_type = request_type.decode()
        target = target.decode()

        if request == b'':
            request = None
        else:
            request = Json.loads(request)

        handled_parts = (request_id, request_type, target, request, bulk)

        try:
            payload = self.req_handler(socket, lock, ident, handled_parts)
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

        ### Does the req_handler return value need to be a special Python class?
        ### Faking the fields for now via tight coupling.

        response = dict()
        bulk = b''

        if error is not None:
            response['error'] = error
        if payload is not None:
            response['data'] = payload

            try:
                bulk = payload['bulk']
            except (KeyError, TypeError):
                pass
            else:
                del payload['bulk']

        message = Message.Message(request_id, 'REP', target, response, bulk)
        parts = (ident,) + message.to_parts()

        lock.acquire()
        self.socket.send_multipart(parts)
        lock.release()


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(1000)
            for active,flag in sockets:
                if self.socket == active:
                    parts = self.socket.recv_multipart()
                    self.queue.put((self.socket, self.socket_lock, parts))


    def send(self, ident, message):
        """ Convenience method for subclasses to fire off a message response.
            Any such subclasses are not using just the :func:`req_incoming`
            and :func:`req_handler` background thread machinery defined
            here to handle requests, and are handling asynchronous responses
            that need to be relayed back to the original caller.
        """

        parts = (ident,) + message.to_parts()

        self.socket_lock.acquire()
        self.socket.send_multipart(parts)
        self.socket_lock.release()


    def _worker_main(self):
        """ This is the 'main' method for the worker threads responsible for
            handling incoming requests. The task of a worker thread is limited:
            receive a request, and feed it to :func:`req_incoming` for
            processing. Multiple threads are allocated to this function to
            allow for long-duration requests to be handled gracefully without
            jamming up the processing of subsequent requests.
        """

        while self.shutdown == False:
            # The distribution of jobs is handled via a simple queue rather
            # than a ZeroMQ construct, as the overall throughput was higher.

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

        # self.shutdown is True. Ensure the queue has something in it to wake
        # up the other worker threads, having None in the queue too many times
        # is better than not having it there enough times.

        self.queue.put(None)


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



def send(address, port, message):
    """ Use :func:`client` to connect to the specified *address* and *port*,
        and send the specified :class:`Message.Request` instance. This method
        blocks until the completion of the request.
    """

    connection = client(address, port)
    connection.send(message)
    message.wait()

    response = message.rep_payload

    if message.rep_bulk is not None:
        response['bulk'] = message.rep_bulk

    return response


def shutdown():
    client_connections.clear()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
