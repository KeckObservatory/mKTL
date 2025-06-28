""" A class representation of an mKTL message, including subclasses for
    specific messages.
"""

import itertools
import threading
import time

from . import Json


# This is the version of the mKTL on-the-wire protocol implemented here.
# See the protocol specification for a full description; the version is
# identified by a single byte.

version = b'a'


class Message:
    """ The :class:`Message` provides a very thin encapsulation of what it
        means to be a message in an mKTL context.

        :ivar payload: The item-specific data, if any, for the message.
        :ivar bulk: The item-specific bulk data, if any, for the message.
        :ivar valid_types: A set of valid strings for the message type.
        :ivar timestamp: A UNIX epoch timestamp for the message send time.
    """

    valid_types = set(('ACK', 'PUB', 'REP'))

    def __init__(self, id, type, target=None, payload=None, bulk=None):

        if type in self.valid_types:
            pass
        else:
            raise ValueError('invalid request type: ' + type)

        self.id = id
        self.type = type
        self.payload = payload
        self.target = target
        self.bulk = bulk
        self.timestamp = time.time()

        self.parts = None
        self.publish_parts = None


    def __repr__(self):
        as_tuple = (version, self.id, self.type, self.target, self.payload, self.bulk)
        return repr(as_tuple)


    def multiparts(self):
        """ Convert this :class:`Message` to a tuple of parts appropriate
            for a call send_multipart(), where every part has been converted
            to bytes. The tuple is returned.
        """

        parts = self.parts

        if parts is None:

            id = self.id
            type = self.type
            target = self.target
            payload = self.payload
            bulk = self.bulk

            try:
                id.decode
            except AttributeError:
                id = '%08x' % (id)
                id = id.encode()

            type = type.encode()

            if target ==  None or target == '':
                target = b''
            else:
                try:
                    target = target.encode()
                except AttributeError:
                    print(repr(self))

            # Some JSON encoders will happily take a byte sequence and
            # encode it. We may need to check here whether the payload
            # is already bytes; it is expected to be a dictionary.

            if payload == None or payload == '':
                payload = b''
            else:
                payload = Json.dumps(payload)

            if bulk is None:
                bulk = b''

            parts = (version, id, type, target, payload, bulk)
            self.parts = parts


        return parts


    def publish_multiparts(self):
        """ Convert this :class:`Message` to a tuple of parts appropriate
            for a call send_multipart(), in a publish context, where every
            part has been converted to bytes. The tuple is returned.
        """

        parts = self.publish_parts

        if parts is None:

            target = self.target
            payload = self.payload
            bulk = self.bulk

            # The PUB/SUB topic has a trailing dot to prevent leading
            # substring matches from picking up extra keys.

            target = target + '.'
            target = target.encode()

            # Some JSON encoders will happily take a byte sequence and
            # encode it. We may need to check here whether the payload
            # is already bytes; it is expected to be a dictionary.

            if payload == None or payload == '':
                payload = b''
            else:
                payload = Json.dumps(payload)

            if bulk is None:
                bulk = b''

            parts = (target, version, payload, bulk)
            self.publish_parts = parts


        return parts


# end of class Message



class Request(Message):
    """ A :class:`Request` has a little extra functionality, focusing on
        local caching of response values and signaling that a request is
        complete.

        :ivar response: The final response to a request (also a Message).
    """

    valid_types = set(('CONFIG', 'GET', 'HASH', 'SET'))

    def __init__(self, type, target=None, payload=None, bulk=None, id=None):

        if id is None:
            id = _id_next()

        Message.__init__(self, id, type, target, payload, bulk)

        self.response = None

        self.ack_event = threading.Event()
        self.rep_event = threading.Event()


    def __repr__(self):
        as_tuple = (version, self.id, self.type, self.target, self.payload, self.bulk)
        if self.response is None:
            as_tuple = as_tuple + (None,)
        else:
            as_tuple = as_tuple + repr(self.response)

        return repr(as_tuple)


    def _complete_ack(self):
        """ The request, if any, has been acknowledged; signal any callers blocking via :func:`wait_ack` to proceed.
        """

        self.ack_event.set()


    def _complete(self, response):
        """ Locally store the response and signal any callers blocking via
            :func:`wait` to proceed.
        """

        self.response = response
        self.ack_event.set()
        self.rep_event.set()


    def poll(self):
        """ Return True if the request is complete, otherwise return False.
        """

        return self.rep_event.is_set()


    def wait_ack(self, timeout):
        """ Block until the request has been acknowledged. This is a wrapper to
            a class:`threading.Event` instance; if the event has occurred it
            will return True, otherwise it returns False after the requested
            *timeout*. If the *timeout* argument is None it will block
            indefinitely.
        """

        return self.ack_event.wait(timeout)


    def wait(self, timeout=60):
        """ Block until the request has been handled. The response to the
            request is always returned; the response will be None if the
            original request is still pending.
        """

        self.rep_event.wait(timeout)
        return self.response


# end of class Request



_id_min = 0
_id_max = 0xFFFFFFFF
_id_lock = threading.Lock()
_id_ticker = itertools.count(_id_min)


def _id_next():
    """ Return the next request identification number for subroutines to
        use when constructing a message.
    """

    global _id_ticker
    _id_lock.acquire()
    id = next(_id_ticker)

    if id >= _id_max:
        _id_ticker = itertools.count(_id_min)

        if id > _id_max:
            # This shouldn't happen, but here we are...
            id = _id_min
            next(_id_ticker)

    _id_lock.release()

    id = '%08x' % (id)
    id = id.encode()
    return id


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
