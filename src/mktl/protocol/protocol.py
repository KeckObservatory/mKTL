from __future__ import annotations

from typing import Optional, Callable, Any

from .builder import MessageBuilder
from .message import Message
from . import request
from . import publish


class Protocol:

    def __init__(self, node_id: str, session):
        self.builder = MessageBuilder(node_id)
        self.session = session
        self._handlers = {}


    # Request APIs
    def get(self, key: str, *, dest: Optional[str] = None):

        msg = (
            self.builder
            .get(key)
            .to(dest)
            .build()
        )

        request.validate(msg)
        return self.session.send(msg)


    def set(self, key: str, payload: dict, *, dest=None):

        msg = (
            self.builder
            .set(key)
            .payload(payload)
            .to(dest)
            .build()
        )

        request.validate(msg)
        return self.session.send(msg)


    def request(self, msg: Message):
        request.validate(msg)
        return self.session.send(msg)


    # Publish APIs
    def publish(self, topic: str, payload: Any):

        topic = publish.normalize_topic(topic)

        msg = (
            self.builder
            .pub(topic)
            .payload(payload)
            .build()
        )

        publish.validate(msg)
        self.session.send(msg)


    def serve(
        self,
        key: str,
        callback: Callable[[dict, dict], Optional[dict]],
    ) -> None:
        """
        Register a key handler.

        callback(payload, ctx) -> dict | None
        """

        def _wrap(msg: Message):

            payload = msg.env.payload

            ctx = {
                "key": msg.env.key,
                "source": msg.env.sourceid,
                "transid": msg.env.transid,
                "time": msg.env.time,
                "binary": msg.binary,
                "raw_msg": msg,
            }

            try:
                result = callback(payload, ctx)
            except Exception as ex:
                result = {"ok": False, "error": str(ex)}

            # Build response automatically
            if result is not None:
                resp = (
                    self.builder
                    .rep(msg.env.transid)
                    .to(msg.env.sourceid)
                    .payload(result)
                    .build()
                )
                self.session.send(resp)

        self._handlers[key] = _wrap
