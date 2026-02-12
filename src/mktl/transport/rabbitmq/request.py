"""RabbitMQ request/response transport."""

from __future__ import annotations

import atexit
import concurrent.futures
import os
import queue
import socket as pysocket
import threading
from typing import Dict, Optional, Tuple

import pika

from ...protocol.message import Message
from ...protocol.wire import pack_frame, unpack_frame
from ...transport import TransportTimeout
from ..session import RequestSession, RequestServer, PendingRequest


_BROKER_HOST = os.environ.get("MKTL_AMQP_HOST", "localhost")
_BROKER_PORT = int(os.environ.get("MKTL_AMQP_PORT", "5672"))


def _broker_params() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=_BROKER_HOST,
        port=_BROKER_PORT,
        heartbeat=600,
        blocked_connection_timeout=300,
    )


class Client(RequestSession):
    """Issue requests via RabbitMQ and receive responses on an exclusive
    reply queue."""

    timeout = 0.1

    def __init__(self, address: str, port: int):
        self.port = int(port)
        self.address = address

        self._pending: Dict[str, PendingRequest] = {}
        self._outbox: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._connection = None

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)

    def send(self, msg: Message) -> PendingRequest:
        if self._connection is None or not self._ready.is_set():
            raise TransportTimeout(
                f"not connected to AMQP broker at {_BROKER_HOST}:{_BROKER_PORT}"
            )

        pending = PendingRequest(msg)
        self._outbox.put(pending)
        self._connection.add_callback_threadsafe(self._flush_outbox)

        ack = pending.wait_ack(self.timeout)
        if not ack:
            raise TransportTimeout(
                f"{msg.env.type} @ {self.address}:{self.port}: "
                f"no ACK in {self.timeout:.2f} sec"
            )
        return pending

    def _run(self) -> None:
        self._connection = pika.BlockingConnection(_broker_params())
        self._channel = self._connection.channel()

        # Exclusive auto-delete reply queue
        result = self._channel.queue_declare(queue="", exclusive=True)
        self._reply_queue = result.method.queue

        self._channel.basic_consume(
            queue=self._reply_queue,
            on_message_callback=self._on_response,
            auto_ack=True,
        )

        self._ready.set()
        self._channel.start_consuming()

    def _on_response(self, _ch, _method, properties, body: bytes) -> None:
        msg = unpack_frame(body)
        self._handle_incoming(msg)

    def _flush_outbox(self) -> None:
        """Drain all queued outgoing requests (called on the connection
        thread via add_callback_threadsafe)."""
        while True:
            try:
                pending: PendingRequest = self._outbox.get_nowait()
            except queue.Empty:
                break

            server_queue = _server_queue_name(self.address, self.port)
            self._pending[pending.id] = pending
            self._channel.basic_publish(
                exchange="",
                routing_key=server_queue,
                properties=pika.BasicProperties(
                    reply_to=self._reply_queue,
                    correlation_id=pending.id,
                ),
                body=pack_frame(pending.req),
            )


class Server(RequestServer):
    """Receive requests from a RabbitMQ queue, respond to them."""

    port = None
    hostname = None

    def __init__(
        self,
        address: Optional[str] = None,
        port: Optional[int] = None,
        avoid: Optional[set] = None,
    ):
        self.hostname = address or pysocket.getfqdn()
        self.port = int(port) if port is not None else 0

        self._queue_name = _server_queue_name(self.hostname, self.port)

        self._responses: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._connection = None
        self.shutdown = False
        self.workers = concurrent.futures.ThreadPoolExecutor(max_workers=8)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)

    def send(self, response: Message) -> None:
        self._responses.put(response)
        self._connection.add_callback_threadsafe(self._flush_responses)

    def _run(self) -> None:
        self._connection = pika.BlockingConnection(_broker_params())
        self._channel = self._connection.channel()

        self._channel.queue_declare(queue=self._queue_name, durable=False)
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=self._queue_name,
            on_message_callback=self._on_request,
        )

        self._ready.set()
        self._channel.start_consuming()

    def _on_request(self, ch, method, properties, body: bytes) -> None:
        ch.basic_ack(delivery_tag=method.delivery_tag)
        msg = unpack_frame(body)
        msg.env.meta["_reply_to"] = properties.reply_to
        msg.env.meta["_correlation_id"] = properties.correlation_id
        self.workers.submit(self._req_incoming, msg)

    def _flush_responses(self) -> None:
        """Drain all queued outgoing responses (called on the connection
        thread via add_callback_threadsafe)."""
        while True:
            try:
                response: Message = self._responses.get_nowait()
            except queue.Empty:
                break

            reply_to = response.env.meta.get("_reply_to", "")
            correlation_id = response.env.meta.get(
                "_correlation_id", response.env.transid
            )
            self._channel.basic_publish(
                exchange="",
                routing_key=reply_to,
                properties=pika.BasicProperties(
                    correlation_id=correlation_id,
                ),
                body=pack_frame(response),
            )


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


def _server_queue_name(address: str, port: int) -> str:
    return f"mktl.req.{address}.{port}"


def _cleanup() -> None:
    for c in _client_cache.values():
        try:
            c._connection.close()
        except Exception:
            pass


atexit.register(_cleanup)
