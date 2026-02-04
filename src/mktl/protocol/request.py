""" Classes and methods implemented here implement the request/response
    aspects of the client/server API.
"""

import atexit
import concurrent.futures
import itertools
import queue
import socket
import sys
import threading
import time
import traceback
import zmq

from .. import json
from . import message

minimum_port = 10079
maximum_port = 13679
zmq_context = zmq.Context()


class Client:
    """ Issue requests via a ZeroMQ DEALER socket and receive responses.
        Maintains a persistent connection to a single server; the *address*
        and *port* number must be specified.
    """

    timeout = 0.1

    def __init__(self, address, port):

        port = int(port)
        self.port = port
        self.address = address

        server = "tcp://%s:%d" % (address, port)
        identity = "request.Client.%d" % (id(self))

        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.set_hwm(0)
        self.socket.identity = identity.encode()
        self.socket.connect(server)

        # This queue may need to come from the multiprocessing module in
        # the future, but the message.Request class would need to be modified
        # such that its notification mechanism is no longer a threading.Event.

        try:
            # Available in Python 3.7+.
            self.requests = queue.SimpleQueue()
        except AttributeError:
            self.requests = queue.Queue()

        # Similar to the above comment, this may need to be an ipc socket
        # instead of inproc if there's a need to support full multiprocessing.
        # That, or an additional background thread to sit on the multiprocessing
        # queue, and use this inproc signal to trigger the send/recv thread.

        internal = "inproc://request.Client:signal:%s:%d" % (address, port)
        self.request_address = internal
        self.request_receive = zmq_context.socket(zmq.PAIR)
        self.request_receive.bind(internal)

        self.request_signal = zmq_context.socket(zmq.PAIR)
        self.request_signal.connect(internal)

        self.pending = dict()
        self.pending_thread = threading.Thread(target=self.run)
        self.pending_thread.daemon = True
        self.pending_thread.start()


    def _rep_incoming(self, parts):
        """ A client only receives two types of messages from the remote side:
            an ACK, or a REP. The response payload, if any, is handed back to
            the relevant :class:`mktl.protocol.message.Request` instance for
            any further handling by the original caller.
        """

        their_version = parts[0]

        if their_version == message.version:
            response_type = parts[2]
            target = parts[3]
            payload = parts[4]
            bulk = parts[5]
        else:
            error = dict()
            error['type'] = 'RuntimeError'
            error['text'] = "message is mKTL protocol %s, recipient expects %s" % (repr(their_version), repr(message.version))
            payload = message.Payload(None, error=error)
            payload = payload.encapsulate()
            response_type = 'REP'
            target = '???'
            bulk = None

        # This could still blow up if the version doesn't match-- the id may
        # be in a different message part-- but we have to try, otherwise
        # there's no way to pass the error back to the original caller.

        response_id = parts[1]

        try:
            pending = self.pending[response_id]
        except KeyError:
            # The original caller's request is gone, no further processing
            # is possible.
            return

        if response_type == b'ACK':
            pending._complete_ack()
            return

        if bulk == b'':
            bulk = None

        if payload == b'':
            payload = None
        else:
            payload = json.loads(payload)
            try:
                payload = message.Payload(**payload, bulk=bulk)
            except TypeError:
                # Weird stuff in the payload. Don't fail on the conversion,
                # allow it to pass, assuming the users know what they're doing.
                pass

        response = message.Message('REP', target, payload, id=response_id)
        pending._complete(response)
        del self.pending[response_id]


    def _req_outgoing(self):
        """ Clear one request notification and send one pending request.
        """

        self.request_receive.recv(flags=zmq.NOBLOCK)
        message = self.requests.get(block=False)

        parts = tuple(message)
        self.pending[message.id] = message

        # A lock around the ZeroMQ socket is necessary in a multithreaded
        # application; otherwise, if two different threads both invoke
        # send_multipart(), the message parts can and will get mixed
        # together. However, this send_multipart() call is now only called
        # from a single thread handling all send/recv calls, so the
        # lock is no longer in place.

        self.socket.send_multipart(parts)


    def run(self):
        """ All send() and recv() calls are sequestered to this thread
            in order to satisfy ZeroMQ. Even with a lock around the socket
            it will sometimes seg fault when multiple threads act on a
            single socket; in particular, if other threads (like client
            operations) call send() while a background thread (like this
            thread) is running poll() and recv(). Thus, all incoming local
            requests are filtered through a queue, with notification happening
            on a PAIR socket to allow a single poll() call to wake up the
            thread for either type of event.

            Example reference:

            https://github.com/zeromq/libzmq/issues/1108
        """

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self.request_receive, zmq.POLLIN)

        while True:
            sockets = poller.poll(10000) # milliseconds
            for socket, flag in sockets:

                if self.request_receive == socket:
                    self._req_outgoing()

                elif self.socket == socket:
                    parts = self.socket.recv_multipart()
                    self._rep_incoming(parts)


    def send(self, message):
        """ A *message* is a fully populated
            :class:`mktl.protocol.message.Request` instance,
            which normalizes the arguments that will be sent via this method
            as a multi-part message. The message instance will also be used for
            notification of any/all responses from the remote end; this method
            will block while waiting for the ACK request, but will never block
            waiting for the full response; the caller is free to decide whether
            to block or wait for the full response, using the methods in the
            :class:`mktl.protocol.message.Request` instance.
        """

        self.requests.put(message)
        self.request_signal.send(b'')

        try:
            silent = message.payload.silent
        except:
            silent = False

        if silent:
            return

        ack = message.wait_ack(self.timeout)

        if ack == False:
            error = '%s @ %s:%d: no response received in %.2f sec'
            args = (message.type, self.address, self.port, self.timeout)
            error = error % args
            raise zmq.ZMQError(error)


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

    worker_count = 128

    def __init__(self, hostname=None, port=None, avoid=set()):

        # The hostname is set and stored, but not used, as we are going to
        # listen on every available interface.

        if hostname is None:
            hostname = socket.getfqdn()

        self.hostname = hostname
        self.socket = zmq_context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.set_hwm(0)

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

        try:
            # Available in Python 3.7+.
            self.responses = queue.SimpleQueue()
        except AttributeError:
            self.responses = queue.Queue()

        internal = "inproc://request.Server:signal:%s:%d" % (hostname, self.port)
        self.response_address = internal
        self.response_receive = zmq_context.socket(zmq.PAIR)
        self.response_receive.bind(internal)

        self.response_signal = zmq_context.socket(zmq.PAIR)
        self.response_signal.connect(internal)

        self.shutdown = False
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

        # The use of worker threads and a synchronization primitive is something
        # like a 10-20% hit in performance compared to using a single thread.
        # Multiple worker threads allow for a request to block until completion,
        # without blocking all other request handling. A ThreadPoolExecutor is
        # an easy way to achieve the same performance without rolling our own
        # queueing and handling.

        # Using a deque and a synchronization construct (such as a Condition)
        # is similar in performance to using a SimpleQueue. Using a fast
        # Condition implementation might make it worth the trouble, but the
        # implementation in the threading module is slow enough that it's not
        # any better.

        # Using ZeroMQ sockets to implement a multithreaded queue was much
        # slower, it's not clear whether full multiprocessing would help.

        self.workers = concurrent.futures.ThreadPoolExecutor(max_workers=self.worker_count)


    def req_ack(self, request):
        """ Acknowledge the incoming request. The client is expecting an
            immediate ACK for all request types, including errors; this is
            how a client knows whether a daemon is online to respond to its
            request.
        """

        response = message.Message('ACK', id=request.id)
        response.prefix = request.prefix

        self.send(response)


    def req_handler(self, request):
        """ The default request handler is for debug purposes only, and is
            effectively a no-op. :class:`mktl.Daemon` leverages a
            custom subclass of :class:`Server` that properly handles specific
            types of requests, since it needs to be aware of the actual
            structure of what's happening in the daemon code.
        """

        try:
            silent = request.payload.silent
        except:
            silent = False

        if silent:
            return

        self.req_ack(request)

        response = message.Message('REP', target, id=request.id)
        response.prefix = request.prefix

        self.send(response)

        # This default handler returns None, which indicates to req_incoming()
        # that it should not issue a response of its own.


    def req_incoming(self, parts):
        """ All inbound requests are filtered through this method. It will
            parse the request as JSON into a Python dictionary, and hand it
            off to :func:`req_handler` for further processing. Error handling
            is managed here; if :func:`req_handler` raises an exception it
            will be packaged up and returned to the client as an error.

            :func:`req_handler` is expected to call :func:`req_ack` to
            acknowledge the incoming request; if :func:`req_handler` is
            returning a simple payload it will be packged into a REP response.
            No response will be issued if :func:`req_handler` returns None.
        """

        ### This all needs to move into a try/except block so that any
        ### exceptions are passed back to the originator of the request.
        ### Presumably that means calling something like _req_incoming().

        ident = parts[0]
        their_version = parts[1]

        if their_version != message.version:
            raise ValueError("message is mKTL protocol %s, recipient is %s" % (repr(their_version), repr(message.version)))

        req_id = parts[2]
        req_type = parts[3]
        target = parts[4]
        payload = parts[5]
        bulk = parts[6]

        req_type = req_type.decode()
        target = target.decode()

        if bulk == b'':
            bulk = None

        if payload == b'':
            payload = None
        else:
            payload = json.loads(payload)
            try:
                payload = message.Payload(**payload, bulk=bulk)
            except TypeError:
                # Weird stuff in the payload. Don't fail on the conversion,
                # allow it to pass, assuming the users know what they're doing.
                pass

        request = message.Request(req_type, target, payload, id=req_id)
        request.prefix = (ident,)
        payload = None
        error = None

        try:
            payload = self.req_handler(request)
        except:
            e_class, e_instance, e_traceback = sys.exc_info()
            error = dict()
            error['type'] = e_class.__name__
            error['text'] = str(e_instance)
            error['debug'] = traceback.format_exc()

        if payload is None and error is None:
            # The handler should only return None when no response is
            # immediately forthcoming-- the handler has invoked some
            # other processing chain that will issue a proper response,
            # or the client explicitly requested no response.
            return

        if error is not None:
            if payload is None:
                payload = message.Payload(None)
                payload.error = error
            elif payload.error is None:
                payload.error = error

        response = message.Message('REP', target, payload, id=req_id)
        response.prefix = request.prefix

        self.send(response)


    def run(self):

        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self.response_receive, zmq.POLLIN)

        while self.shutdown == False:
            sockets = poller.poll(10000) # milliseconds
            for active, flag in sockets:

                if self.response_receive == active:
                    self._rep_outgoing()

                elif self.socket == active:
                    parts = self.socket.recv_multipart()
                    # Calling submit() will block if a worker is not available.
                    # Note that for high frequency operations this can result
                    # in out-of-order handling of requests, for example, if a
                    # stream of SET requests are inbound for a single item.
                    self.workers.submit(self.req_incoming, parts)


        self.workers.shutdown()


    def _rep_outgoing(self):
        """ Clear one request notification and send one pending response.
        """

        self.response_receive.recv(flags=zmq.NOBLOCK)
        response = self.responses.get(block=False)

        parts = tuple(response)
        self.socket.send_multipart(parts)


    def send(self, response):
        """ Queue a response to be sent back to the original requestor.
        """

        self.responses.put(response)
        self.response_signal.send(b'')


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



def send(address, port, request):
    """ Use :func:`client` to connect to the specified *address* and *port*,
        and send the specified :class:`mktl.protocol.message.Request` instance.
        This method blocks until the completion of the request.
    """

    connection = client(address, port)
    connection.send(request)
    request.wait()

    payload = request.response.payload
    return payload


def shutdown():
    client_connections.clear()


atexit.register(shutdown)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
