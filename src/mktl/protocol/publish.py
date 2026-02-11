from .message import Message


class Publish(Message):
    def __init__(self, topic, payload=None):
        super().__init__(
            msg_type="PUB",
            target=topic,
            payload=payload
        )
