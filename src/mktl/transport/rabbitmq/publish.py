"""RabbitMQ publish/subscribe transport."""

from __future__ import annotations

import atexit
import os
import queue
import threading
import traceback
from typing import Dict, Optional, Tuple

import pika

from ...protocol.message import Message
from ...protocol.wire import pack_frame, unpack_frame
from ..session import PublishSession, SubscribeSession


_EXCHANGE = "mktl.pub"
_BROKER_HOST = os.environ.get("MKTL_AMQP_HOST", "localhost")
_BROKER_PORT = int(os.environ.get("MKTL_AMQP_PORT", "5672"))


def _broker_params() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=_BROKER_HOST,
        port=_BROKER_PORT,
        heartbeat=600,
        blocked_connection_timeout=300,
    )


class Client(SubscribeSession):
    """SUB client backed by a RabbitMQ topic exchange."""

    def __init__(self, address: str, port: int):
        self.address = address
        self.port = int(port)

        self._inbox: queue.Queue = queue.Queue()
        self._bindings: list = []
        self._has_wildcard = False
        self._ready = threading.Event()
        self._connection = None

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)

    def subscribe(self, topic: str) -> None:
        routing_key = topic + ".#"
        self._bindings.append(routing_key)
        if self._ready.is_set():
            self._connection.add_callback_threadsafe(
                lambda rk=routing_key: self._bind_topic(rk)
            )

    def _bind_topic(self, routing_key: str) -> None:
        """Add a topic binding, removing the default wildcard if present."""
        if self._has_wildcard:
            self._channel.queue_unbind(
                exchange=_EXCHANGE,
                queue=self._queue_name,
                routing_key="#",
            )
            self._has_wildcard = False
        self._channel.queue_bind(
            exchange=_EXCHANGE,
            queue=self._queue_name,
            routing_key=routing_key,
        )

    def recv(self) -> Message:
        body = self._inbox.get()
        return unpack_frame(body)

    def _run(self) -> None:
        self._connection = pika.BlockingConnection(_broker_params())
        self._channel = self._connection.channel()

        self._channel.exchange_declare(
            exchange=_EXCHANGE, exchange_type="topic", durable=False
        )

        result = self._channel.queue_declare(queue="", exclusive=True)
        self._queue_name = result.method.queue

        self._channel.queue_bind(
            exchange=_EXCHANGE,
            queue=self._queue_name,
            routing_key="#",
        )
        self._has_wildcard = True

        # Apply any bindings requested before the channel was ready.
        for rk in self._bindings:
            self._bind_topic(rk)

        self._channel.basic_consume(
            queue=self._queue_name,
            on_message_callback=self._on_message,
            auto_ack=True,
        )

        self._ready.set()
        self._channel.start_consuming()

    def _on_message(self, _ch, _method, _properties, body: bytes) -> None:
        self._inbox.put(body)


class Server(PublishSession):
    """PUB server backed by a RabbitMQ topic exchange."""

    def __init__(
        self,
        port: Optional[int] = None,
        avoid: Optional[set] = None,
    ):
        self.port = int(port) if port is not None else 0

        self._queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._connection = None
        self.shutdown = False

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)

    def send(self, msg: Message) -> None:
        self._queue.put(msg)
        self._connection.add_callback_threadsafe(self._flush)

    def _run(self) -> None:
        self._connection = pika.BlockingConnection(_broker_params())
        self._channel = self._connection.channel()

        self._channel.exchange_declare(
            exchange=_EXCHANGE, exchange_type="topic", durable=False
        )

        self._ready.set()
        # Keep the connection alive by consuming from an unused queue
        self._connection.process_data_events(time_limit=None)

    def _flush(self) -> None:
        """Drain all queued outgoing messages (called on the connection
        thread via add_callback_threadsafe)."""
        while True:
            try:
                msg: Message = self._queue.get_nowait()
            except queue.Empty:
                break

            routing_key = (msg.env.key or "") + "."
            try:
                self._channel.basic_publish(
                    exchange=_EXCHANGE,
                    routing_key=routing_key,
                    body=pack_frame(msg),
                )
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
    for c in _client_cache.values():
        try:
            c._connection.close()
        except Exception:
            pass


atexit.register(_cleanup)
