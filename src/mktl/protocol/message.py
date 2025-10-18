""" A class representation of an mKTL message, including subclasses for
    specific messages.
"""

import itertools
import threading
import time as timemodule

from .. import json


# This is the version of the mKTL on-the-wire protocol implemented here.
# See the protocol specification for a full description; the version is
# identified by a single byte.

version = b'a'


class Message:
    """ The :class:`Message` provides a very thin encapsulation of what it
        means to be a message in an mKTL context. This class will be used
        to represent mKTL messages that do not result in a response.

        The fields are largely in order of how they are represented on the
        wire: the message *type*, the key/store *target* for the request,
        the *payload* of the message (a :class:`Payload` instance),
        and an identification
        number unique to this correspondence. The identification number is
        the one field that is out-of-order compared to the multipart sequence
        on the wire; this is because some message types (publish messages,
        in particular) do not have an identification number, and it is
        automatically generated for request messages. Rather than force the
        caller to pass an explicit None, the id is left as the last field,
        so that the arguments for all :class:`Message` instances can have
        a similar structure.

        :ivar payload: The item-specific data, if any, for the message.
        :ivar valid_types: A set of valid strings for the message type.
        :ivar timestamp: A UNIX epoch timestamp for the message send time.
    """

    valid_types = set(('ACK', 'REP'))

    def __init__(self, type, target=None, payload=None, id=None):

        if type in self.valid_types:
            pass
        else:
            raise ValueError('invalid request type: ' + type)

        # There are some message types where the id is allowed to be None;
        # in particular, publish messages do not have or need an identification
        # number.

        self.id = id
        self.type = type
        self.payload = payload
        self.target = target
        self.timestamp = timemodule.time()

        self.parts = None


    def __iter__(self):
        self._finalize()
        return iter(self.parts)


    def __repr__(self):
        self._finalize()
        return repr(self.parts)


    def _finalize(self):
        """ Take the contents of this :class:`Message`, interpet them as
            bytes, and prepare the tuple that will be used for the multipart
            transmission on the wire.
        """

        parts = self.parts

        if parts is None:

            id = self.id
            type = self.type
            target = self.target
            payload = self.payload

            # It is legal to create a Message with None as the id-- this happens
            # all the time when a Message is used as a container-- but trying to
            # send such a message is not permitted.

            if id is None:
                raise RuntimeError('messages must have an id to be put on the wire')

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
                    # Assume it is already bytes.
                    pass

            if payload is None or payload == '':
                bulk = b''
                payload = b''
            else:
                bulk = payload.bulk
                if bulk is None:
                    bulk = b''
                payload = payload.encapsulate()

            parts = (version, id, type, target, payload, bulk)
            self.parts = parts


# end of class Message



class Broadcast(Message):
    """ A :class:`Broadcast` is a minor variant of a :class:`Message`,
        with a change to format the multipart tuple in a PUB/SUB specific
        fashion.
    """

    valid_types = set(('PUB',))

    def _finalize(self):

        parts = self.parts

        if parts is None:

            target = self.target
            payload = self.payload

            # The PUB/SUB topic has a trailing dot to prevent leading
            # substring matches from picking up extra keys.

            target = target + '.'
            target = target.encode()

            if payload is None or payload == '':
                bulk = b''
                payload = b''
            else:
                bulk = payload.bulk
                if bulk is None:
                    bulk = b''
                payload = payload.encapsulate()

            parts = (target, version, payload, bulk)
            self.parts = parts


# end of class Broadcast



class Request(Message):
    """ A :class:`Request` has a little extra functionality, focusing on
        local caching of response values and signaling that a request is
        complete. This is the class that will be used on the client side
        when a server is expected to provide a response, such as returning
        a requested value, or signaling that a set operation is complete.

        :ivar response: The final response to a request (also a Message).
    """

    valid_types = set(('CONFIG', 'GET', 'HASH', 'SET'))

    def __init__(self, type, target=None, payload=None, id=None):

        # Requests are generally initiated without an id number, but they're
        # required to have one. The expectation is that requests will have an
        # id number that is locally unique, so that the request/response
        # handler can correctly tie an incoming response to the request that
        # generated it.

        # Long story short, for nearly all Request instances the id argument
        # will be None, and we are expected to auto-generate a locally unique
        # identification number.

        if id is None:
            id = _id_next()

        Message.__init__(self, type, target, payload, id)

        self.response = None

        self.ack_event = threading.Event()
        self.rep_event = threading.Event()


    def __repr__(self):
        self._finalize()
        request = 'REQ: ' + repr(self.parts)

        if self.response is None:
            response = 'REP: None'
        else:
            response = 'REP: ' + repr(tuple(self.response))

        return request + ', ' + response


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



class Payload:
    """ This is a lightweight class to properly encapsulate a Python-native
        value for later inclusion in a :class:`Message` instance. Any fields
        in the Payload.omit set will be excluded from the encapsulation.
    """

    omit = set(('bulk', '_encapsulated', 'omit'))

    def __init__(self, value, time=None, error=None, bulk=None, shape=None, dtype=None, refresh=None, **kwargs):

        # The use of 'time' as a keyword argument is what's motivating the
        # weird import of the time module in this file. We want the keyword
        # arguments to be aligned with the fields in the JSON description
        # of a payload: value, time, and error.

        if time is None:
            time = timemodule.time()

        if refresh is False:
            refresh = None

        self.bulk = bulk
        self.dtype = dtype
        self.error = error
        self.refresh = refresh
        self.shape = shape
        self.time = time
        self.value = value

        self._encapsulated = None

        # Allow additional arbitrary fields in the payload. We are assuming
        # the caller knows what they are doing, and that these additional
        # fields can be serialized as JSON.

        for key,value in kwargs.items():
            setattr(self, key, value)


    def __repr__(self):
        return self.encapsulate().decode()


    def encapsulate(self):
        ''' Encapsulate the non-bulk fields as a dictionary, and return the
            JSON encoding of that dictionary. Calling this method multiple
            times will return the cached encapsulation rather than generate
            it anew.
        '''

        if self._encapsulated:
            return self._encapsulated

        payload = dict()

        # All local attributes get put into the encapsulated payload,
        # except for those included in the omit set.

        for key,value in vars(self).items():
            if key in self.omit:
                continue
            payload[key] = value

        payload = json.dumps(payload)

        self._encapsulated = payload
        return payload


# end of class Payload


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
            id = next(_id_ticker)

    _id_lock.release()

    id = '%08x' % (id)
    id = id.encode()
    return id


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
