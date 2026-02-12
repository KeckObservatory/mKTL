from __future__ import annotations

import json
from typing import Tuple, Optional

from .message import Envelope, Message, MsgType


# Separator between header and binary payload
_SEP = b"\n\n"


def pack_frame(msg: Message) -> bytes:
    """
    Serialize Message -> bytes

    Layout:
        [JSON header][SEP][binary...]

    Binary section omitted if not present.
    """

    env = msg.env

    header = {
        "version":  env.version,
        "type":     env.type.value,     # stable enum serialization
        "transid":  env.transid,
        "key":      env.key,
        "payload":  env.payload,
        "time":     env.time,
        "destid":   env.destid,
        "sourceid": env.sourceid,
    }

    header_bytes = json.dumps(
        header,
        separators=(",", ":"),          # compact JSON
    ).encode("utf-8")

    if msg.binary is None:
        return header_bytes

    return header_bytes + _SEP + msg.binary


def unpack_frame(frame: bytes) -> Message:
    """
    Deserialize bytes -> Message
    """

    try:
        header_bytes, binary = frame.split(_SEP, 1)
    except ValueError:
        header_bytes = frame
        binary = None

    env = json.loads(header_bytes.decode("utf-8"))

    envelope = Envelope(
        version=env.get("version", 1),
        type=MsgType(env["type"]),
        transid=env["transid"],
        key=env.get("key"),
        payload=env.get("payload", {}),
        time=env.get("time"),
        destid=env.get("destid"),
        sourceid=env.get("sourceid"),
    )

    return Message(envelope, binary)
