import json
import mktl


def test_message_translation():

    payload = mktl.protocol.message.Payload(True)
    message = mktl.protocol.message.Message('PUB', payload=payload)
    parts = tuple(message)

    translated = mktl.protocol.message.from_parts(parts)

    assert message.id == translated.id
    assert message.type == translated.type
    assert message.prefix == translated.prefix
    assert message.target == translated.target

    assert round(message.timestamp, 4) == round(translated.timestamp, 4)

    assert message.payload.value == translated.payload.value
    assert message.payload.time == translated.payload.time


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
