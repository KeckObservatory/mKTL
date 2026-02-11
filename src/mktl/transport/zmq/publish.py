"""ZeroMQ publish/subscribe transport."""

from __future__ import annotations

import atexit
import itertools
import queue
import threading
import traceback
from typing import Dict, Optional, Tuple

import zmq

from ...protocol import Message, Publish
from ...transport import TransportPortError
from .framing import from_pub_frames, to_pub_frames

minimum_port = 10139
maximum_port = 13679
zmq_context = zmq.Context()


class Client:
    """SUB client."""

    def __init__(self, address: str, port: int):
        self.address = address
        self.port = int(port)

        server = f"tcp://{address}:{self.port}"
        self.socket = zmq_context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.connect(server)

        # Subscribe to all topics by default (call subscribe() to narrow)
        self.socket.setsockopt(zmq.SUBSCRIBE, b"")

    def subscribe(self, topic: str) -> None:
        # Historical trailing '.' topic separator.
        self.socket.setsockopt(zmq.SUBSCRIBE, (topic + ".").encode())

    def recv(self) -> Message:
        parts = self.socket.recv_multipart()
        return from_pub_frames(parts)


class Server:
    """PUB server."""

    def __init__(self, port: Optional[int] = None, avoid: Optional[set] = None):
        avoid = avoid or set()
        self.port = int(port) if port is not None else None
        self.socket = zmq_context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.LINGER, 0)

        if self.port is None:
            for p in range(minimum_port, maximum_port):
                if p in avoid:
                    continue
                try:
                    self.socket.bind(f"tcp://*:{p}")
                    self.port = p
                    break
                except zmq.ZMQError:
                    continue
            if self.port is None:
                raise TransportPortError(
                    f"no ports available in range {minimum_port}:{maximum_port}"
                )
        else:
            try:
                self.socket.bind(f"tcp://*:{self.port}")
            except zmq.ZMQError as exc:
                raise TransportPortError(
                    f"port already in use: {self.port}"
                ) from exc

        # Internal queue for thread-safe sends
        try:
            self._queue = queue.SimpleQueue()
        except AttributeError:
            self._queue = queue.Queue()

        internal = f"inproc://publish.Server:signal:{id(self)}"
        self._sig_rx = zmq_context.socket(zmq.PAIR)
        self._sig_rx.bind(internal)
        self._sig_tx = zmq_context.socket(zmq.PAIR)
        self._sig_tx.connect(internal)

        self.shutdown = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def send(self, msg: Publish) -> None:
        self._queue.put(msg)
        self._sig_tx.send(b"")

    def _send_one(self) -> None:
        self._sig_rx.recv(flags=zmq.NOBLOCK)
        msg = self._queue.get(block=False)
        frames = to_pub_frames(msg)
        self.socket.send_multipart(frames)

    def run(self) -> None:
        poller = zmq.Poller()
        poller.register(self._sig_rx, zmq.POLLIN)
        while not self.shutdown:
            for active, _flag in poller.poll(10000):
                if active == self._sig_rx:
                    try:
                        self._send_one()
                    except Exception:
                        traceback.print_exc()


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


def _cleanup() -> None:
    try:
        zmq_context.term()
    except Exception:
        pass


atexit.register(_cleanup)
