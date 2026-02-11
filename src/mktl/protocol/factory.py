"""Convenience constructors for protocol messages."""

from __future__ import annotations

from typing import Any, Optional

from .discover import Discover
from .publish import Publish
from .request import Request
from .fields import GET
from .message import Payload


def payload(value: Any, **kwargs) -> Payload:
    return Payload(value=value, **kwargs)


def request(target: str, value: Any = None, *, op: str = GET, payload: Optional[Payload] = None, **payload_kwargs) -> Request:
    if payload is None:
        payload = Payload(value=value, **payload_kwargs)
    return Request(msg_type=op, target=target, payload=payload)


def publish(topic: str, value: Any = None, *, payload: Optional[Payload] = None, **payload_kwargs) -> Publish:
    if payload is None:
        payload = Payload(value=value, **payload_kwargs)
    return Publish(target=topic, payload=payload)


def discover(value: Any = None, *, payload: Optional[Payload] = None, **payload_kwargs) -> Discover:
    if payload is None and (value is not None or payload_kwargs):
        payload = Payload(value=value, **payload_kwargs)
    return Discover(payload=payload)
