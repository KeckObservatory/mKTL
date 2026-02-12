"""ZMQ multipart framing for protocol messages.

Request/Response (DEALER<->ROUTER)
    (optional routing prefix...), version, transid, type, key, payload_json, binary

Publish (PUB/SUB)
    topic_with_trailing_dot, version, payload_json, binary
"""

from __future__ import annotations

from typing import Sequence, Tuple

from ...protocol.message import Message, Envelope, MsgType
from ..codec import encode_payload, decode_payload


_VERSION = "a"
_VERSION_BYTES = _VERSION.encode()


def to_request_frames(msg: Message, *, include_prefix: bool = False) -> Tuple[bytes, ...]:

    env = msg.env
    prefix: Tuple[bytes, ...] = tuple(env.meta.get("zmq_prefix", ()))
    if not include_prefix:
        prefix = ()

    payload_bytes = encode_payload(env.payload)
    binary = msg.binary or b""
    transid = env.transid.encode()
    key = (env.key or "").encode()

    parts = (
        _VERSION_BYTES,
        transid,
        env.type.value.encode(),
        key,
        payload_bytes,
        binary,
    )
    return prefix + parts


def from_request_frames(parts: Sequence[bytes]) -> Message:
    """Decode ROUTER/DEALER parts into a protocol Message.

    If a ROUTER identity prefix is present, it is stored in env.meta['zmq_prefix'].
    """

    if not parts:
        raise ValueError("empty message")

    # ROUTER sockets prepend identity frames. We expect either:
    #   [version, transid, type, key, payload, binary]
    # or
    #   [ident, version, transid, type, key, payload, binary]
    if parts[0] == _VERSION_BYTES:
        prefix: Tuple[bytes, ...] = ()
        start = 0
    else:
        prefix = (parts[0],)
        start = 1

    their_version = parts[start]
    if their_version != _VERSION_BYTES:
        meta = {"zmq_prefix": prefix} if prefix else {}
        env = Envelope(
            type=MsgType.REP,
            sourceid="",
            transid=parts[start + 1].decode(),
            payload={"error": {
                "type": "RuntimeError",
                "text": f"mKTL protocol {their_version!r}, expected {_VERSION_BYTES!r}",
            }},
            meta=meta,
        )
        return Message(env=env)

    transid = parts[start + 1].decode()
    msg_type = parts[start + 2].decode()
    key_bytes = parts[start + 3]
    key = key_bytes.decode() if key_bytes not in (b"", None) else None
    payload_bytes = parts[start + 4]
    binary_bytes = parts[start + 5] if len(parts) > start + 5 else b""

    payload = decode_payload(payload_bytes)
    meta = {"zmq_prefix": prefix} if prefix else {}

    env = Envelope(
        type=MsgType(msg_type),
        sourceid=prefix[0].decode() if prefix else "",
        transid=transid,
        key=key,
        payload=payload,
        meta=meta,
    )

    return Message(env=env, binary=binary_bytes if binary_bytes else None)


def to_pub_frames(msg: Message) -> Tuple[bytes, ...]:
    """Encode a publish message for PUB/SUB sockets."""

    env = msg.env
    topic = (env.key or "") + "."  # trailing dot to prevent prefix matches
    topic_b = topic.encode()
    payload_bytes = encode_payload(env.payload)
    binary = msg.binary or b""
    return (topic_b, _VERSION_BYTES, payload_bytes, binary)


def from_pub_frames(parts: Sequence[bytes]) -> Message:
    if len(parts) < 4:
        raise ValueError("invalid PUB message")

    topic = parts[0].decode()
    if topic.endswith("."):
        topic = topic[:-1]

    their_version = parts[1]
    if their_version != _VERSION_BYTES:
        env = Envelope(
            type=MsgType.PUB,
            sourceid="",
            key=topic,
            payload={"error": {
                "type": "RuntimeError",
                "text": f"mKTL protocol {their_version!r}, expected {_VERSION_BYTES!r}",
            }},
        )
        return Message(env=env)

    payload = decode_payload(parts[2])
    binary_bytes = parts[3] if len(parts) > 3 else b""

    env = Envelope(
        type=MsgType.PUB,
        sourceid="",
        key=topic,
        payload=payload,
    )

    return Message(env=env, binary=binary_bytes if binary_bytes else None)
