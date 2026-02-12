"""Transport-agnostic session layer."""

from __future__ import annotations

import sys
import threading
import traceback
from typing import Dict, Optional

from ..protocol.factory import fast_ack
from ..protocol.fields import ACK, REP
from ..protocol.message import Message, Payload
from ..protocol.request import Request
from .base import Transport, TransportTimeout


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


class RequestSession:
    """Client-side request/response pattern logic."""

    timeout = 0.1

    def __init__(self, transport: Transport):
        self.transport = transport
        self._pending: Dict[bytes, PendingRequest] = {}

    def _handle_incoming(self, msg: Message) -> None:
        """Correlate incoming ACK/REP to a PendingRequest."""
        pending = self._pending.get(msg.msg_id)
        if pending is None:
            return

        if msg.msg_type == ACK:
            pending._complete_ack()
            return

        # REP (or error REP on version mismatch)
        pending._complete(msg)
        self._pending.pop(msg.msg_id, None)

    def send(self, request: Request) -> PendingRequest:
        pending = PendingRequest(request)
        self._pending[pending.id] = pending
        self.transport.send(request)

        ack = pending.wait_ack(self.timeout)
        if not ack:
            self._pending.pop(pending.id, None)
            raise TransportTimeout(
                f"{request.msg_type}: no ACK in {self.timeout:.2f} sec"
            )
        return pending


class RequestServer:
    """Server-side request handler."""

    def __init__(self, transport: Transport):
        self.transport = transport

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
        self.send(fast_ack(request))

    def send(self, response: Message) -> None:
        self.transport.send(response)

    # --- internal ---
    def _req_incoming(self, msg: Message) -> None:
        """Dispatch to req_handler, build REP, send."""
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
        rep.meta.update(req.meta)
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
