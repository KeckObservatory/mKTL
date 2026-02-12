from __future__ import annotations

import uuid
import time
from typing import Optional, Dict, Any

from .message import Message, Envelope, MsgType


class MessageBuilder:

    def __init__(self, sourceid: str):
        self._source = sourceid

        self._type: Optional[MsgType] = None
        self._dest: Optional[str] = None
        self._key: Optional[str] = None
        self._payload: Dict[str, Any] = {}
        self._meta: Dict[str, Any] = {}
        self._binary: Optional[bytes] = None
        self._transid: Optional[str] = None

    # Semantic type setters
    def get(self, key: str):
        self._type = MsgType.GET
        self._key = key
        return self

    def set(self, key: str):
        self._type = MsgType.SET
        self._key = key
        return self

    def hash(self, key: str):
        self._type = MsgType.HASH
        self._key = key
        return self

    def config(self, key: str):
        self._type = MsgType.CONFIG
        self._key = key
        return self

    def pub(self, key: str):
        self._type = MsgType.PUB
        self._key = key
        return self

    def ack(self, transid: str):
        self._type = MsgType.ACK
        self._transid = transid
        return self

    def rep(self, transid: str):
        self._type = MsgType.REP
        self._transid = transid
        return self

    # Routing
    def to(self, destid: Optional[str]):
        self._dest = destid
        return self

    # Data
    def payload(self, data: Dict[str, Any]):
        self._payload = data
        return self

    def meta(self, data: Dict[str, Any]):
        self._meta.update(data)
        return self

    def binary(self, blob: bytes):
        self._binary = blob
        return self

    # Finalize
    def build(self) -> Message:

        if self._type is None:
            raise ValueError("Message type not specified")

        env = Envelope(
            type=self._type,
            sourceid=self._source,
            destid=self._dest,
            key=self._key,
            payload=self._payload,
            meta=self._meta,
            transid=self._transid or str(uuid.uuid4()),
            time=time.time(),
        )

        return Message(env=env, binary=self._binary)
