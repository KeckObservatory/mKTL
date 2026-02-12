"""Transport codec for protocol payloads."""

from __future__ import annotations

from typing import Dict, Any, Optional

from .. import json


def encode_payload(payload: Optional[Dict[str, Any]]) -> bytes:
    if not payload:
        return b""
    return json.dumps(payload)


def decode_payload(payload_bytes: bytes) -> Dict[str, Any]:
    if payload_bytes in (b"", None):
        return {}
    return json.loads(payload_bytes)
