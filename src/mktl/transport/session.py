"""Transport-agnostic session layer."""

from __future__ import annotations

import sys
import threading
import traceback
from typing import Dict, Optional

from ..protocol.message import Message, Envelope, MsgType
from .base import Transport, TransportTimeout


class PendingRequest:
    """Client-side helper that provides ACK/REP synchronization."""

    def __init__(self, msg: Message):
        self.req = msg
        self.response: Optional[Message] = None
        self.ack_event = threading.Event()
        self.rep_event = threading.Event()

    @property
    def id(self) -> str:
        return self.req.env.transid

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


class RequestSession:
    """Client-side request/response pattern logic."""

    timeout = 0.1

    def __init__(self, transport: Transport):
        self.transport = transport
        self._pending: Dict[str, PendingRequest] = {}

    def _handle_incoming(self, msg: Message) -> None:
        """Correlate incoming ACK/REP to a PendingRequest."""
        pending = self._pending.get(msg.env.transid)
        if pending is None:
            return

        if msg.env.type == MsgType.ACK:
            pending._complete_ack()
            return

        # REP
        pending._complete(msg)
        self._pending.pop(msg.env.transid, None)

    def send(self, msg: Message) -> PendingRequest:
        pending = PendingRequest(msg)
        self._pending[pending.id] = pending
        self.transport.send(msg)

        ack = pending.wait_ack(self.timeout)
        if not ack:
            self._pending.pop(pending.id, None)
            raise TransportTimeout(
                f"{msg.env.type}: no ACK in {self.timeout:.2f} sec"
            )
        return pending


class RequestServer:
    """Server-side request handler."""

    node_id = ""
    _on_receive = None

    def __init__(self, transport: Transport, node_id: str = ""):
        self.transport = transport
        self.node_id = node_id

    # --- request handling hooks ---
    def req_handler(self, msg: Message) -> Optional[dict]:
        """Override in subclasses.

        Return:
          - dict  -> will be wrapped into a REP
          - None  -> no immediate REP (handler is responsible)
        """
        self.req_ack(msg)
        return None

    def req_ack(self, msg: Message) -> None:
        ack = Message(
            env=Envelope(
                type=MsgType.ACK,
                sourceid=self.node_id,
                transid=msg.env.transid,
                destid=msg.env.sourceid,
                key=msg.env.key,
                meta=dict(msg.env.meta),
            ),
        )
        self.send(ack)

    def send(self, response: Message) -> None:
        self.transport.send(response)

    # --- internal ---
    def _req_incoming(self, msg: Message) -> None:
        if self._on_receive is not None:
            self._on_receive(msg)
            return

        payload: Optional[dict] = None
        error: Optional[dict] = None

        try:
            payload = self.req_handler(msg)
        except Exception:
            e_class, e_instance, _tb = sys.exc_info()
            error = {
                "type": getattr(e_class, "__name__", "Exception"),
                "text": str(e_instance),
                "debug": traceback.format_exc(),
            }

        if payload is None and error is None:
            return

        rep_payload = payload if payload is not None else {}
        if error is not None:
            rep_payload["error"] = error

        rep = Message(
            env=Envelope(
                type=MsgType.REP,
                sourceid=self.node_id,
                transid=msg.env.transid,
                destid=msg.env.sourceid,
                key=msg.env.key,
                payload=rep_payload,
                meta=dict(msg.env.meta),
            ),
        )
        self.send(rep)


class PublishSession:
    """Server-side publish pattern logic."""

    port = None

    def __init__(self, transport: Transport):
        self.transport = transport

    def send(self, msg: Message) -> None:
        self.transport.send(msg)


class SubscribeSession:
    """Client-side subscribe pattern logic."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def subscribe(self, topic: str) -> None:
        if hasattr(self.transport, 'subscribe'):
            self.transport.subscribe(topic)

    def recv(self) -> Message:
        return self.transport.recv()
