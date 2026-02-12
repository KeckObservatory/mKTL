from __future__ import annotations

from .message import Message, MsgType


def is_publish(msg: Message) -> bool:
    return msg.env.type == MsgType.PUB

def normalize_topic(topic: str) -> str:
    """
    Enforce trailing '.' to avoid substring matches
    per mKTL convention.
    """
    if topic and not topic.endswith("."):
        topic += "."
    return topic

def validate(msg: Message) -> None:

    if msg.env.type != MsgType.PUB:
        return

    if msg.env.key is None:
        raise ValueError("PUB requires topic/key")

    if msg.env.destid is not None:
        raise ValueError("PUB must not specify destid")
