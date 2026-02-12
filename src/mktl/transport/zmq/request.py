"""ZeroMQ request/response transport.

This is the historical mKTL ROUTER/DEALER request channel, rewritten so that
the *protocol* is transport-agnostic.

Public surface area intentionally mirrors the old module:
    - Client / Server classes
    - client(address, port) cache helper
    - send(address, port, message)
"""

from __future__ import annotations

import atexit
import concurrent.futures
import queue
import socket as pysocket
import threading
from typing import Dict, Optional, Tuple

import zmq

from ...protocol.message import Message
from ...protocol.wire import pack_frame, unpack_frame
from ...transport import TransportTimeout, TransportPortError
from ..session import RequestSession, RequestServer, PendingRequest


minimum_port = 10079
maximum_port = 13679
zmq_context = zmq.Context()


class Client(RequestSession):
    """Issue requests via a ZeroMQ DEALER socket and receive responses."""

    timeout = 0.1

    def __init__(self, address: str, port: int):
        self.port = int(port)
        self.address = address

        server = f"tcp://{address}:{self.port}"
        identity = f"request.Client.{id(self)}".encode()

        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.identity = identity
        self.socket.connect(server)

        try:
            self._outbox = queue.SimpleQueue()
        except AttributeError:
            self._outbox = queue.Queue()

        internal = f"inproc://request.Client:signal:{address}:{self.port}"
        self._signal_rx = zmq_context.socket(zmq.PAIR)
        self._signal_rx.bind(internal)
        self._signal_tx = zmq_context.socket(zmq.PAIR)
        self._signal_tx.connect(internal)

        self._pending: Dict[str, PendingRequest] = {}
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def _handle_outgoing(self) -> None:
        # Clear one signal and send one request.
        self._signal_rx.recv(flags=zmq.NOBLOCK)
        pending: PendingRequest = self._outbox.get(block=False)

        self._pending[pending.id] = pending
        self.socket.send(pack_frame(pending.req))

    def run(self) -> None:
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self._signal_rx, zmq.POLLIN)

        while True:
            for active, _flag in poller.poll(10000):
                if active == self._signal_rx:
                    self._handle_outgoing()
                elif active == self.socket:
                    msg = unpack_frame(self.socket.recv())
                    self._handle_incoming(msg)

    def send(self, msg: Message) -> PendingRequest:
        pending = PendingRequest(msg)
        self._outbox.put(pending)
        self._signal_tx.send(b"")

        ack = pending.wait_ack(self.timeout)
        if not ack:
            raise TransportTimeout(
                f"{msg.env.type} @ {self.address}:{self.port}: no ACK in {self.timeout:.2f} sec"
            )
        return pending


class Server(RequestServer):
    """Receive requests via a ZeroMQ ROUTER socket, respond to them."""

    port = None  # auto

    def __init__(self, address: Optional[str] = None, port: Optional[int] = None, avoid: Optional[set] = None):
        self.address = address or pysocket.getfqdn()
        self.port = int(port) if port is not None else None
        self.avoid = set(avoid or set())

        self.socket = zmq_context.socket(zmq.ROUTER)
        self.socket.setsockopt(zmq.LINGER, 0)

        if self.port is None:
            self.port = self._bind_any()
        else:
            try:
                self.socket.bind(f"tcp://{self.address}:{self.port}")
            except zmq.ZMQError as exc:
                raise TransportPortError(
                    f"port already in use: {self.port}"
                ) from exc

        # Response queue for thread-safe sending
        try:
            self._responses = queue.SimpleQueue()
        except AttributeError:
            self._responses = queue.Queue()

        internal = f"inproc://request.Server:signal:{self.address}:{self.port}"
        self._signal_rx = zmq_context.socket(zmq.PAIR)
        self._signal_rx.bind(internal)
        self._signal_tx = zmq_context.socket(zmq.PAIR)
        self._signal_tx.connect(internal)

        self.shutdown = False
        self.workers = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def _bind_any(self) -> int:
        for port in range(minimum_port, maximum_port + 1):
            if port in self.avoid:
                continue
            try:
                self.socket.bind(f"tcp://{self.address}:{port}")
                return port
            except zmq.ZMQError:
                continue
        raise TransportPortError(
            f"no ports available in range {minimum_port}:{maximum_port}"
        )

    def send(self, response: Message) -> None:
        self._responses.put(response)
        self._signal_tx.send(b"")

    def _rep_outgoing(self) -> None:
        self._signal_rx.recv(flags=zmq.NOBLOCK)
        response: Message = self._responses.get(block=False)
        identity = response.env.meta.get("zmq_prefix", (b"",))[0]
        self.socket.send_multipart([identity, pack_frame(response)])

    def run(self) -> None:
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self._signal_rx, zmq.POLLIN)

        while not self.shutdown:
            for active, _flag in poller.poll(10000):
                if active == self._signal_rx:
                    self._rep_outgoing()
                elif active == self.socket:
                    identity, wire_bytes = self.socket.recv_multipart()
                    msg = unpack_frame(wire_bytes)
                    msg.env.meta["zmq_prefix"] = (identity,)
                    self.workers.submit(self._req_incoming, msg)


_client_cache: Dict[Tuple[str, int], Client] = {}
_client_lock = threading.Lock()


def client(address: str, port: int) -> Client:
    key = (address, int(port))
    with _client_lock:
        c = _client_cache.get(key)
        if c is None:
            c = Client(address, int(port))
            _client_cache[key] = c
        return c


def send(address: str, port: int, message: Message) -> Message:
    c = client(address, port)
    pending = c.send(message)
    response = pending.wait(timeout=60)
    if response is None:
        raise TransportTimeout("no response received")
    return response


def _cleanup() -> None:
    try:
        zmq_context.term()
    except Exception:
        pass


atexit.register(_cleanup)
