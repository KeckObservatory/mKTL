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
import itertools
import queue
import socket as pysocket
import sys
import threading
import time
import traceback
from typing import Dict, Optional, Tuple

import zmq

from ...protocol.message import Message, Payload
from ...protocol.request import Request
from ...protocol.fields import ACK, REP
from ...transport import TransportTimeout, TransportPortError
from .framing import from_request_frames, to_request_frames


minimum_port = 10079
maximum_port = 13679
zmq_context = zmq.Context()


class PendingRequest:
    """Client-side helper that provides ACK/REP synchronization."""

    def __init__(self, req: Request):
        self.req = req
        self.response: Optional[Message] = None
        self.ack_event = threading.Event()
        self.rep_event = threading.Event()

    @property
    def id(self) -> bytes:
        return self.req.msg_id

    def wait_ack(self, timeout: Optional[float]) -> bool:
        return self.ack_event.wait(timeout)

    def wait(self, timeout: Optional[float] = 60) -> Optional[Message]:
        self.rep_event.wait(timeout)
        return self.response

    def _complete_ack(self) -> None:
        self.ack_event.set()

    def _complete(self, response: Message) -> None:
        self.response = response
        self.ack_event.set()
        self.rep_event.set()


class Client:
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

        self._pending: Dict[bytes, PendingRequest] = {}
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def _handle_incoming(self, parts: Tuple[bytes, ...]) -> None:
        msg = from_request_frames(parts)
        pending = self._pending.get(msg.msg_id)
        if pending is None:
            return

        if msg.msg_type == ACK:
            pending._complete_ack()
            return

        # REP (or error REP on version mismatch)
        pending._complete(msg)
        self._pending.pop(msg.msg_id, None)

    def _handle_outgoing(self) -> None:
        # Clear one signal and send one request.
        self._signal_rx.recv(flags=zmq.NOBLOCK)
        pending: PendingRequest = self._outbox.get(block=False)

        frames = to_request_frames(pending.req)
        self._pending[pending.id] = pending
        self.socket.send_multipart(frames)

    def run(self) -> None:
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self._signal_rx, zmq.POLLIN)

        while True:
            for active, _flag in poller.poll(10000):
                if active == self._signal_rx:
                    self._handle_outgoing()
                elif active == self.socket:
                    parts = tuple(self.socket.recv_multipart())
                    self._handle_incoming(parts)

    def send(self, request: Request) -> PendingRequest:
        pending = PendingRequest(request)
        self._outbox.put(pending)
        self._signal_tx.send(b"")

        ack = pending.wait_ack(self.timeout)
        if not ack:
            raise TransportTimeout(
                f"{request.msg_type} @ {self.address}:{self.port}: no ACK in {self.timeout:.2f} sec"
            )
        return pending


class Server:
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

    # --- request handling hooks ---
    def req_handler(self, request: Request) -> Optional[Payload]:
        """Override in subclasses.

        Return:
          - Payload -> will be wrapped into a REP
          - None    -> no immediate REP (handler is responsible for later response)
        """

        # Default: no-op
        self.req_ack(request)
        return None

    def req_ack(self, request: Request) -> None:
        ack = Message(msg_type=ACK, target=request.target, msg_id=request.msg_id)
        ack.meta["zmq_prefix"] = request.meta.get("zmq_prefix", ())
        self.send(ack)

    def send(self, response: Message) -> None:
        self._responses.put(response)
        self._signal_tx.send(b"")

    # --- internal ---
    def _rep_outgoing(self) -> None:
        self._signal_rx.recv(flags=zmq.NOBLOCK)
        response: Message = self._responses.get(block=False)
        frames = to_request_frames(response, include_prefix=True)
        self.socket.send_multipart(frames)

    def _req_incoming(self, parts: Tuple[bytes, ...]) -> None:
        msg = from_request_frames(parts)

        # Convert generic Message to typed Request (validates op)
        try:
            req = Request(msg_type=msg.msg_type, target=msg.target, payload=msg.payload, msg_id=msg.msg_id)
        except Exception:
            # If invalid, treat as opaque request
            req = Request(msg_type=msg.msg_type, target=msg.target, payload=msg.payload, msg_id=msg.msg_id)

        req.meta.update(msg.meta)

        payload: Optional[Payload] = None
        error: Optional[dict] = None

        try:
            payload = self.req_handler(req)
        except Exception:
            e_class, e_instance, _tb = sys.exc_info()
            error = {
                "type": getattr(e_class, "__name__", "Exception"),
                "text": str(e_instance),
                "debug": traceback.format_exc(),
            }

        if payload is None and error is None:
            return

        if payload is None:
            payload = Payload(value=None)
        if error is not None:
            payload.error = error

        rep = Message(msg_type=REP, target=req.target, payload=payload, msg_id=req.msg_id)
        rep.meta["zmq_prefix"] = req.meta.get("zmq_prefix", ())
        self.send(rep)

    def run(self) -> None:
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self._signal_rx, zmq.POLLIN)

        while not self.shutdown:
            for active, _flag in poller.poll(10000):
                if active == self._signal_rx:
                    self._rep_outgoing()
                elif active == self.socket:
                    parts = tuple(self.socket.recv_multipart())
                    self.workers.submit(self._req_incoming, parts)


# --- convenience helpers (API-compatible-ish) ---

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


def send(address: str, port: int, message: Request) -> Payload:
    c = client(address, port)
    pending = c.send(message)
    response = pending.wait(timeout=60)
    if response is None:
        raise TransportTimeout("no response received")
    if response.payload is None:
        return Payload(value=None)
    return response.payload


def _cleanup() -> None:
    try:
        zmq_context.term()
    except Exception:
        pass


atexit.register(_cleanup)
