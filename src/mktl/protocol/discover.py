"""Discovery / hello message type (transport-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .fields import DISC
from .message import Message, Payload


@dataclass(slots=True)
class Discover(Message):
    """A protocol discovery/announcement message."""

    msg_type: str = DISC
    target: Optional[str] = None
    payload: Optional[Payload] = None
