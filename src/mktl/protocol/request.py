"""Request/response message types (transport-agnostic).

This module defines *message shapes* only. The mechanics of delivering
requests (ZMQ/Zyre/MQTT/etc.) live under :mod:`mktl.transport`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .fields import CONFIG, GET, HASH, SET
from .message import Message, Payload


@dataclass(slots=True)
class Request(Message):
    """A protocol request that expects a response."""

    # For mKTL requests, msg_type is the *operation* (CONFIG/GET/HASH/SET).
    msg_type: str = GET
    target: Optional[str] = None
    payload: Optional[Payload] = None

    def __post_init__(self):
        if self.msg_type not in (CONFIG, GET, HASH, SET):
            raise ValueError(f"invalid request operation: {self.msg_type}")
