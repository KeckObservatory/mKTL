
.. _protocol:

Protocol
========

The mKTL protocol is the primary interface layer for mKTL as a whole;
associated Python code can be considered a reference implementation,
but the intent is for the protocol to be language agnostic. mKTL clients
and daemons communicate using ZeroMQ sockets. This document describes the
socket types used, the formatting of the messages, and the types of requests
that can be made.


Principles of operation
-----------------------

Unique addressing of daemons within a store is accomplished by the use of
a unique port number to connect to that daemon; messages arriving on a
specific port are thus guaranteed, by construction, to only need decoding
exactly once; there is no envelope for the message contents, such that the
message contents may need to be rerouted to a new location. Each daemon
will use a unique :ref:`publish <publish>` and :ref:`request <request>`
listener, operating on a unique port on that host.

A given host providing connectivity for mKTL could have thousands of daemons
running locally, each listening on a unique port number. Each daemon deploys
a UDP listener on a predetermined port number (10111) to enable discovery of
daemons on that host; a :ref:`dedicated "guide" process <markguided>` also
listens on a predetermined port number (10103) to streamline discovery from
the client side. This usage pattern expects there to be a single
:ref:`markguided` process running on every host running one or more mKTL
daemons. The discovery exchange is :ref:`described below <discovery>`
in more detail.

An mKTL proxy, were such a thing to exist, would follow the same principle:
a unique port for each listener of each proxied daemon, which allows the use
of the ``zmq.proxy()`` method to cleanly bridge between endpoints at the
protocol level without any inspection of message contents, thus ensuring the
proxy has minimal processing overhead.


.. _request:

Request/response
----------------

The first socket type implements a request/response pattern. This represents
the majority of the interactive traffic between a mKTL client and daemon.
Because requests can be asynchronous, mKTL does not use the REQ/REP
implementation in ZeroMQ, which enforces a strict one request, one response
pattern; instead, we use DEALER/ROUTER, which allows any amount of messages
in any order, in any direction.

The request/response interaction between the client and daemon is a multipart
message, where each part is required and has specific meaning. The reference
implementation provides a :class:`mktl.protocol.Message` class to minimize
the amount of code that has to be aware about the on-the-wire message structure.
For both ends of the request/response exchange, the message parts are:

.. list-table::

  * - *Field*
    - *Data type*

  * - **version**
    - A single ASCII character indicating the mKTL protocol version number.
      The initial release of the mKTL protocol uses the version character 'a'.

  * - **identifier**
    - A unique identifier for the request. The format of this identifier is
      not strict, it could be any byte string (such as a UUID), but the initial
      implementation uses a monotonically increasing eight-byte integer. The
      identifier is set by the client, and allows the client to tie a response
      to the original request. Note that this identifier does not necessarily
      have significance on the daemon side, daemons will use their own internal
      scheme to uniquely identify requests, but the response will always include
      this original identifier.

  * - **type**
    - The message type. This is a short string of characters that identifies
      what type of request, or reponse, this message represents. It is one
      of the values described in the ref:`message_types` section below.

  * - **target**
    - The target for this request/response, if any. Not all requests have a
      target; responses don't need to specify it, since it is the identification
      number that ties a response to its request. If a target is specified it
      is a store or a key, depending on the request; this field will be an empty
      byte sequence if the target is not specified.

  * - **payload**
    - The message payload. This is the JSON representation of any additional
      data required as part of this exchange; if setting a new value, it would
      contain the value; if it is a response containing additional information
      it would go here. This field will be an empty byte sequence if no
      additional information is required. See the :ref:`message_payload` section
      for a more complete description of the payload contents.

  * - **bulk**
    - A bulk byte sequence, typically a component of the payload. This is to
      allow the transmission of information like image data, where the bulk
      bytes represent the image buffer, and the JSON payload describes how
      to interpret the buffer. This field will be an empty byte sequence if
      there is no bulk component.

Upon receipt of a request the daemon will immediately issue an ACK response.
The absence of a quick response indicates that the daemon is not available,
and the client should immediately raise an error. After the client receives
the initial ACK it should then look for the full response. There will be no
further messages associated with that id number after the full response is
received. A daemon may choose to forego the ACK response, but should only
do so in circumstances where processing a request requires zero additional
processing time.

All requests are handled
fully asynchronously; a client could send a thousand requests in quick
succession, but the responses will not be serialized, and the response order
is not guaranteed. Synchronous behavior, if desired, is implemented by client
code and not in the protocol itself.

Here is an example of what the full exchange on the client side might look
like, in this case handling the exchange as a synchronous request::

        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.identity = identity.encode()
        self.socket.connect(daemon)

	self.socket.send_multipart(request)
	result = self.socket.poll(100) # milliseconds
	if result == 0:
	    raise zmq.ZMQError('no response received in 100 ms')

	ack = self.socket.recv_multipart()
	response = self.socket.recv_multipart()

Here is a representation of what the on-the-wire messages might look like
for the simple exchange outlined above::

	b'a'
	b'00000023'
	b'GET'
	b'kpfguide.LASTFILENAME'
	b''
	b''

	b'a'
	b'00000023'
	b'ACK'
	b''
	b''
	b''

	b'a'
	b'00000023'
	b'REP'
	b''
	b'{"value": /sdata1701/kpf1/2025-06-23/image_672.fits', "time": 234.23}'
	b''


.. _message_types:

Message types
-------------

This section describes the various requests a client can make of the mKTL
daemon via the request/response socket. An additional message type, the PUB,
also exists, but has its own message structure outside this scheme.

.. list-table::

  * - *Message type*
    - *Description*

  * - **GET**
    - Request the current value for a single item.
      The target is always the name of the store, and the key for the item,
      concatenated with a period. No additional payload is required for a
      basic GET request.

      The default behavior for a GET request is for a cached value to be
      returned by the handling daemon. A client can explicitly request an
      up-to-date value by setting the 'refresh' field in the payload to
      'True'; see the :ref:`message_payload` section for additional details.

      The payload of the response will contain 'value' and 'time' fields,
      corresponding to the item value and the last-changed timestamp. If
      the item has a bulk data component, the payload will instead describe
      the bulk data.

  * - **SET**
    - Request a change to the value of a single key. Depending on the daemon,
      this could result in a variety of behavior, from simply caching the value
      to slewing a telescope, and anything in-between. The final response
      indicates the request is complete but does not indicate what the new
      item value is.

      The :ref:`message_payload` for a SET request is the same as the payload
      for a GET response, except that the 'time' field is not required or
      expected.

  * - **HASH**
    - Request the current hash identifiers for any known configuration blocks
      of a single mKTL store. All available hash identifiers, for all known
      stores, will be returned if no store name is specified in the target
      field. An error will be
      returned if a store is requested and the responding daemon does not have
      a cached configuration for that store.

      The hash is 32 hexadecimal integers. The actual hash format is not
      significant, as long as the source of authority is consistent about
      which hash format it uses, and the format can be transmitted as 32
      hexadecimal integers.

      To unify processing the response value is always a dictionary of
      dictionaries, even if only one hash is available.

      Example response values::

	{'kpfguide': {'uuid1': 0x84a30b35...,
		      'uuid2': 0x983ae10f...}}

	{'kpfguide': {'uuid1': 0x84a30b35...,
		      'uuid2': 0x983ae10f...},
	 'kpfmet': {'uuid6': 0xe0377e7d...,
		    'uuid7': 0x7735a20a...,
		    'uuid8': 0x88645dab...,
		    'uuid9': 0x531c14fd...}}


  * - **CONFIG**
    - Request the full configuration contents for a single mKTL store.
      There is no option to dump the configuration data for all known stores,
      a target must always be specified.
      A typical client interaction will request the configuration hash first,
      and if the hash for the cached local copy is not a match, request the
      full contents from the daemon to update the local cache.

      The configuration contents are not fully described here, this is just
      a description of the request. See the
      :ref:`configuration documentation <configuration>` for a full description
      of the data format.

  * - **ACK**
    - Immediate acknowledgement of a request; this message type originates from
      a daemon, only in response to a request If this response is not received
      with a very small time window after the initial request, the client can
      and should assume the daemon handling that request is offline.

  * - **REP**
    - A response to a direct request; this message type originates from a
      daemon, only in response to a request. This response will contain the
      full payload to satisfy the request, any error text related to a problem
      satisfying the request, or simply an indication that the request has been
      completed.


.. _message_payload:

Message payload
---------------

The payload of a message is a JSON associative array. The fields will vary
depending on the message type, and are optional in nearly all circumstances,
but each field has a consistent meaning.

.. list-table::

  * - *Payload field*
    - *Description*

  * - **value**
    - The base representation of the value being transmitted in this message.
      For a GET response or a SET request, this would be the item value;
      depending on the item type this could be a boolean, numeric, or string
      value, depending.

  * - **time**
    - The timestamp associated with the transmitted value. This should be
      interpreted as the "last modified" timestamp for an item, indicating
      when the item assumed the transmitted value. The timestamp is a numeric
      representation of UNIX epoch seconds.

  * - **error**
    - A JSON dictionary with information about any error that occurred while
      processing the request. If the value is not present or is the JSON null
      value, no error occurred. If it is present, it will have these fields:

      =========	============================================
      **type**	Analagous to the Python exception type
                (ValueError, TypeError, etc.).

      **text**	Descriptive text of the error.

      **debug**	Optional additional information about the
		error, such as a Python traceback.
      =========	============================================

      The intent of this error field is not to provide enough information for
      debugging of code, it is intended to provide enough information for the
      client to perform meaningful error handling.

  * - **refresh**
    - An optional field associated with a GET request. If this field is
      present, and it is set to True, the daemon processing the request is
      expected to ignore cached data and retrieve the most current value
      for the target item. For example, if the item represents a temperature
      reading, the daemon would be expected to query the hardware controller,
      update its local cache, and return the result to the requesting client.

  * - **shape**
    - One of the two required fields in order to describe a bulk data array.
      This defines the dimensions of the bulk data array, and is interpreted
      the same way as the 'shape' parameter for a numpy ndarray.

  * - **dtype**
    - One of the two required fields in order to describe a bulk data array.
      This defines the data type of the bulk data array, and is interpreted
      the same way as the 'dtype' parameter for a numpy ndarray. If starting
      from an ndarray, the dtype is the string representation of the .dtype
      attribute of that array; when recreating an ndarray, this string is
      used to get the matching dtype attribute from the numpy module. In
      Python::

        payload['dtype'] = str(my_numpy_array.dtype)
        dtype = getattr(numpy, payload['dtype'])


.. _publish:

Publish/subscribe
-----------------

The second socket type implements a publish/subscribe socket pattern. The
desired functionality in mKTL is a neat match for the PUB/SUB socket pattern
offered by ZeroMQ:

	* SUB clients subscribe to one or more topics from
	  a given PUB socket, or can subscribe to all topics
	  by subscribing to the empty string. This aligns well
	  with existing usage patterns, where KTL keyword
	  names and EPICS channel names are treated as unique
	  identifiers, and map easily to a PUB/SUB topic.

	* The filtering of topics occurs on the daemon side,
	  so if a PUB is publishing a mixture of high-frequency
	  values or large broadcasts, and a client is not
	  subscribed to those specific topics, the broadcasts
	  are never sent to the client.

The formatting of the PUB message is very similar to what is described
above for the :ref:`request/response multipart message format <request>`.
Some fields are not necessary for the PUB variant, and in order for the
topic matching to work the topic must be the first component of a multipart
message. The fields are as follows:

.. list-table::

  * - *Field*
    - *Data type*

  * - **topic**
    - For a typical broadcast the topic will be the full key for a single
      mKTL item. This is similar to the 'target' field in a
      :ref:`request/response message <request>`. For all mKTL addressing
      the topic appends a trailing '.' in order to prevent unwanted substring
      matching between similarly
      named keys. Likewise, because of the ZeroMQ behavior around leading
      substrings, any expanded use of mKTL PUB/SUB behavior will use a
      leading prefix to distinguish it from other message types. For example,
      broadcasting all SET requests with a leading 'set:' prefix, or
      broadcasting a bundle of related mKTL items with a leading 'bundle:'
      prefix.

  * - **version**
    - A single ASCII character indicating the mKTL protocol version number.
      The initial release of the mKTL protocol uses the version character 'a'.

  * - **payload**
    - The message payload, with exactly the same contents as
      :ref:`described above <message_payload>`.

  * - **bulk**
    - A bulk byte sequence, with exactly the same contents as the
      :ref:`request/response message <request>`.


.. _discovery:

Discovery
---------

The UDP discovery layer takes advantage of a feature of UDP listeners: not only
are you allowed to have multiple listeners on the same port, but they will all
respond to an incoming broadcast message. Some care thus needs to be taken to
make sure these responses do not lend themselves to a denial of service attack.
Regardless, this feature allows every daemon to create a listener on the same
port, which greatly simplfies periodic discovery.

The discovery of daemons is a two-part process; rather than ask every daemon
to cache the configuration for every other daemon on its local network, the
caching of configuration data is handled by :ref:`markguided`; when a client
issues a discovery broadcast, it is not looking for responses from individual
daemons, it is looking for responses from a :ref:`markguided` process.

This two-step approach, of contacting the guide process, and subsequently
contacting the authoritative daemon, could be avoided if every local daemon
caching the configuration of every other local daemon; however, a typical
client will cache the response, and discovery is only invoked if the cached
daemon cannot be reached, so the impact of the additional inefficiency is
low. The upside of splitting the discovery into two steps is that reduces
the need for consistent chatter between daemons, which would otherwise grow
exponentially with the number of locally reachable daemons.

There are four shared secrets used in the discovery exchange:

===============	===============================================================
*Secret*	*Description*
===============	===============================================================
**guide port**	The UDP port used to discover locally accessible
		:ref:`markguided` processes. Clients use this port to find
		all such processes. The port number is 10103.

**daemon port**	The UDP port used to discover locally accessible mKTL daemons.
		:ref:`markguided` uses this port to find all such daemons.
		The port number is 10111.

**call**	An arbitrary string used by the discoverer to trigger a
		response from the listener. The string value is ``I heard it``.

**response**	An arbitrary string used by the listener to respond to any
		received calls. The string value is ``on the X:``.

===============	===============================================================

The purpose of discovery is to convey a single piece of information: what is
the port number of an actual mKTL request handler on this host? That port
number, encoded as a string representation of an integer, is the sole additional
component of the response after the colon. For example, if a daemon has a
request port listening on port 10079, the full exchange (discovery request,
discovery response) would be::

    b'I heard it'

    b'on the X:10079'

