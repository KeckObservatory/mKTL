"""ZMQ multipart framing for protocol messages.

Request/Response (DEALER<->ROUTER)
    (optional routing prefix...), version, id, type, target, payload_json, bulk

Publish (PUB/SUB)
    topic_with_trailing_dot, version, payload_json, bulk
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from ...protocol import Message, Payload, PROTOCOL_VERSION
from .codec import encode_payload, decode_payload


_VERSION_BYTES = PROTOCOL_VERSION.encode()


def _as_bytes_id(msg_id: bytes) -> bytes:
    # msg_id is bytes in the new protocol. Keep as-is.
    return msg_id


def to_request_frames(msg: Message, *, include_prefix: bool = False) -> Tuple[bytes, ...]:
    """Encode a protocol Message to ZMQ request/response multipart frames."""

    prefix: Tuple[bytes, ...] = tuple(msg.meta.get("zmq_prefix", ()))
    if prefix and not include_prefix:
        prefix = ()

    payload_bytes, bulk = encode_payload(msg.payload)
    target = (msg.target or "").encode()
    parts = (
        _VERSION_BYTES,
        _as_bytes_id(msg.msg_id),
        msg.msg_type.encode(),
        target,
        payload_bytes,
        bulk,
    )
    return prefix + parts


def from_request_frames(parts: Sequence[bytes]) -> Message:
    """Decode ROUTER/DEALER parts into a protocol Message.

    If a ROUTER identity prefix is present, it is stored as msg.meta['zmq_prefix'].
    """

    if not parts:
        raise ValueError("empty message")

    # ROUTER sockets prepend identity frames. We expect either:
    #   [version, id, type, target, payload, bulk]
    # or
    #   [ident, version, id, type, target, payload, bulk]
    if parts[0] == _VERSION_BYTES:
        prefix: Tuple[bytes, ...] = ()
        start = 0
    else:
        prefix = (parts[0],)
        start = 1

    their_version = parts[start]
    if their_version != _VERSION_BYTES:
        # Version mismatch: represent as an error payload.
        err = {
            "type": "RuntimeError",
            "text": f"message is mKTL protocol {their_version!r}, recipient expects {_VERSION_BYTES!r}",
        }
        payload = Payload(value=None, error=err)
        msg = Message(msg_type="REP", target="???", payload=payload, msg_id=parts[start + 1])
        if prefix:
            msg.meta["zmq_prefix"] = prefix
        return msg

    msg_id = parts[start + 1]
    msg_type = parts[start + 2].decode()
    target = parts[start + 3].decode() if parts[start + 3] not in (b"", None) else None
    payload_bytes = parts[start + 4]
    bulk_bytes = parts[start + 5] if len(parts) > start + 5 else b""

    payload = decode_payload(payload_bytes, bulk_bytes)
    msg = Message(msg_type=msg_type, target=target, payload=payload, msg_id=msg_id)
    if prefix:
        msg.meta["zmq_prefix"] = prefix
    return msg


def to_pub_frames(msg: Message) -> Tuple[bytes, ...]:
    """Encode a publish message for PUB/SUB sockets."""

    topic = (msg.target or "") + "."  # trailing dot to prevent prefix matches
    topic_b = topic.encode()
    payload_bytes, bulk = encode_payload(msg.payload)
    return (topic_b, _VERSION_BYTES, payload_bytes, bulk)


def from_pub_frames(parts: Sequence[bytes]) -> Message:
    if len(parts) < 4:
        raise ValueError("invalid PUB message")

    topic = parts[0].decode()
    if topic.endswith("."):
        topic = topic[:-1]
    their_version = parts[1]
    if their_version != _VERSION_BYTES:
        err = {
            "type": "RuntimeError",
            "text": f"message is mKTL protocol {their_version!r}, recipient expects {_VERSION_BYTES!r}",
        }
        payload = Payload(value=None, error=err)
        return Message(msg_type="PUB", target=topic, payload=payload)

    payload = decode_payload(parts[2], parts[3])
    return Message(msg_type="PUB", target=topic, payload=payload)
