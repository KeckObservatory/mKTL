from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import StrEnum
import time
import uuid


class MsgType(StrEnum):
    GET     = "GET"
    SET     = "SET"
    HASH    = "HASH"
    CONFIG  = "CONFIG"
    ACK     = "ACK"
    REP     = "REP"
    PUB     = "PUB"

@dataclass(frozen=True)
class Envelope:
    """
    Semantic protocol envelope.

    This is NOT wire-format.
    Codec is responsible for mapping to multipart layout.
    """

    type: MsgType
    sourceid: str

    # Correlation
    transid: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Routing intent
    destid: Optional[str] = None
    key: Optional[str] = None

    # Data
    payload: Dict[str, Any] = field(default_factory=dict)

    # Metadata useful for runtime/transport
    time: float = field(default_factory=time.time)
    version: str = "a"
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Message:
    """
    Message container combining semantic envelope
    and optional binary payload.

    Binary is codec/transport handled.
    """

    env: Envelope
    binary: Optional[bytes] = None
