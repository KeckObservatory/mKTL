"""Protocol message model (transport-agnostic).

This module intentionally contains **no** ZeroMQ/Zyre/MQTT concepts:
no sockets, no multipart framing, and no byte encoding.

Wire representation lives in transport-specific code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional
import time
import uuid


# Protocol version identifier (semantic protocol version; not a transport detail).
PROTOCOL_VERSION: str = "a"


@dataclass(slots=True)
class Payload:
    """Structured payload for messages.

    This stays *data-only*; encoding/decoding is handled by a codec.
    """

    value: Any
    time: float = field(default_factory=time.time)
    error: Optional[Dict[str, Any]] = None
    bulk: Optional[bytes] = None

    # Optional metadata commonly used by mKTL
    shape: Optional[Any] = None
    dtype: Optional[str] = None
    refresh: Optional[bool] = None

    # Extra arbitrary JSON-serializable fields
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"value": self.value, "time": self.time}
        if self.error is not None:
            d["error"] = self.error
        if self.shape is not None:
            d["shape"] = self.shape
        if self.dtype is not None:
            d["dtype"] = self.dtype
        if self.refresh is not None:
            d["refresh"] = self.refresh
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], *, bulk: Optional[bytes] = None) -> "Payload":
        # Pull canonical keys and keep the rest as extra.
        d = dict(d)
        value = d.pop("value", None)
        t = d.pop("time", None)
        err = d.pop("error", None)
        shape = d.pop("shape", None)
        dtype = d.pop("dtype", None)
        refresh = d.pop("refresh", None)
        if t is None:
            t = time.time()
        return cls(
            value=value,
            time=t,
            error=err,
            bulk=bulk,
            shape=shape,
            dtype=dtype,
            refresh=refresh,
            extra=d,
        )


@dataclass(slots=True)
class Message:
    """Transport-agnostic protocol message."""

    msg_type: str
    target: Optional[str] = None
    payload: Optional[Payload] = None

    msg_id: bytes = field(default_factory=lambda: uuid.uuid4().bytes)
    timestamp: float = field(default_factory=time.time)

    # Transport-optional metadata (routing envelopes, trace ids, etc.).
    # This is intentionally *not* part of the protocol schema.
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": PROTOCOL_VERSION,
            "id": self.msg_id.hex(),
            "type": self.msg_type,
            "target": self.target,
            "timestamp": self.timestamp,
            "payload": None if self.payload is None else self.payload.to_dict(),
        }
