"""Request/response message types (transport-agnostic).

This module defines *message shapes* only. The mechanics of delivering
requests (ZMQ/Zyre/MQTT/etc.) live under :mod:`mktl.transport`.
"""

from __future__ import annotations

from .message import Message, MsgType
from .builder import MessageBuilder

def is_request(msg: Message) -> bool:
    return msg.env.type in {
        MsgType.GET,
        MsgType.SET,
    }


def is_response(msg: Message) -> bool:
    return msg.env.type == MsgType.REP


def is_ack(msg: Message) -> bool:
    return msg.env.type == MsgType.ACK


def validate(msg: Message) -> None:

    t = msg.env.type

    if t in {MsgType.GET, MsgType.SET, MsgType.REQ}:
        if msg.env.key is None:
            raise ValueError("Request message missing key")

    if t == MsgType.SET:
        if not msg.env.payload:
            raise ValueError("SET requires payload")

    if t == MsgType.PUB:
        raise ValueError("PUB should not be validated via request module")


def matches(req: Message, resp: Message) -> bool:
    return req.env.transid == resp.env.transid


def build_response(
    builder: MessageBuilder,
    req: Message,
    payload,
) -> Message:

    return (
        builder
        .rep(req.env.transid)
        .to(req.env.sourceid)
        .payload(payload)
        .build()
    )


def build_ack(
    builder: MessageBuilder,
    req: Message,
) -> Message:

    return (
        builder
        .ack(req.env.transid)
        .to(req.env.sourceid)
        .build()
    )
