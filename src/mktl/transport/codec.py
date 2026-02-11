"""Transport codec for protocol Payload."""

from __future__ import annotations

from typing import Optional, Tuple

from .. import json
from ..protocol.message import Payload


def encode_payload(payload: Optional[Payload]) -> Tuple[bytes, bytes]:
    """Return (json_bytes, bulk_bytes)."""

    if payload is None:
        return b"", b""

    bulk = payload.bulk or b""
    j = json.dumps(payload.to_dict())
    return j, bulk


def decode_payload(payload_bytes: bytes, bulk_bytes: bytes) -> Optional[Payload]:
    if payload_bytes in (b"", None):
        return None

    d = json.loads(payload_bytes)
    bulk = bulk_bytes if bulk_bytes not in (b"", None) else None
    try:
        return Payload.from_dict(d, bulk=bulk)
    except Exception:
        # Preserve non-conforming payloads for advanced users.
        # Return as raw dict-like payload embedded in Payload.value.
        return Payload(value=d, bulk=bulk)
