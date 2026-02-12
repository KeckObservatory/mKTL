from __future__ import annotations

from typing import Optional, Callable, Dict, Any

from .builder import MessageBuilder
from .message import Message
from . import request
from . import publish


class Protocol:

    def __init__(self, node_id: str, session):
        self.builder = MessageBuilder(node_id)
        self.session = session
        self._req_handlers: Dict[str, Callable[[Message], Optional[dict]]] = {}
        self._evt_handlers: Dict[str, Callable[[Message], None]] = {}

        if hasattr(session, '_on_receive'):
            session._on_receive = self.dispatch


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


    def on(
        self,
        key: str,
        handler: Callable[[Message], Optional[dict]],
    ) -> None:
        self._req_handlers[key] = handler

    def listen(
        self,
        topic: str,
        handler: Callable[[Message], None],
    ) -> None:
        self._evt_handlers[topic] = handler

    def serve(
        self,
        key: str,
        callback: Callable[[dict, dict], Optional[dict]],
    ) -> None:
        """callback(payload, ctx) -> dict | None"""

        def _wrap(msg: Message) -> Optional[dict]:

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
                return callback(payload, ctx)
            except Exception as ex:
                return {"ok": False, "error": str(ex)}

        self.on(key, _wrap)


    def dispatch(self, msg: Message) -> None:
        env = msg.env

        if request.is_request(msg):
            handler = self._req_handlers.get(env.key)
            if handler is None:
                return

            if hasattr(self.session, 'req_ack'):
                self.session.req_ack(msg)

            result = handler(msg)

            if result is not None:
                resp = (
                    self.builder
                    .rep(env.transid)
                    .to(env.sourceid)
                    .payload(result)
                    .meta(dict(env.meta))
                    .build()
                )
                self.session.send(resp)
            return

        if publish.is_publish(msg):
            handler = self._evt_handlers.get(env.key)
            if handler is not None:
                handler(msg)
            return
