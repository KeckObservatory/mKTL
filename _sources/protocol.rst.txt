
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
message contents may need to be rerouted to a new location. Each
:ref:`publish <publish>` and :ref:`request <request>` listener will use
a separate, unique port for each daemon.

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
a unique port for each daemon, which allows the use of the ``zmq.proxy()``
method to cleanly bridge between endpoints at the protocol level without
any inspection of message contents.


.. _request:

Request/response
----------------

The first socket type implements a request/response pattern. This represents
the majority of the interactive traffic between a mKTL client and daemon.
Because requests can be asynchronous, mKTL does not use the REQ/REP
implementation in ZeroMQ, which enforces a strict one request, one response
pattern; instead, we use DEALER/ROUTER, which allows any amount of messages
in any order, in any direction.

The request/response interaction between the client and daemon is of this form::

	b"{'request': 'REQ', 'id': some integer, ...}"

	b"{'message': 'ACK',
	   'id': matching the original request,
	   'time': timestamp for this acknowledgement}"

All messages on ZeroMQ sockets are formatted as raw bytes. JSON is used
as a convenient and portable way to encapsulate both the request and the
response.

The daemon immediately issues the ACK response upon receipt of the request.
The absence of a quick response indicates that the daemon is not available,
and the client should immediately raise an error. After the client receives
the initial ACK it should then look for the full response::

	b"{'message': 'REP',
	   'id': matching the original request,
	   'time': timestamp for this response,
	   'data': response payload}"

After receiving the REP message the request is complete and the daemon will
issue no further messages with this request ID. All requests are handled
fully asynchronously; a client could send a thousand requests in quick
succession, but the responses will not be serialized, and the response order
is not guaranteed. Synchronous behavior is implemented on the client side,
not in the protocol itself.

Here is an example of what the full exchange on the client side might look
like, in this case handling the exchange as a synchronous request::

        self.socket = zmq_context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.identity = identity.encode()
        self.socket.connect(daemon)

	self.socket.send(request)
	result = self.socket.poll(100) # milliseconds
	if result == 0:
	    raise zmq.ZMQError('no response received in 100 ms')

	ack = self.socket.recv()
	response = self.socket.recv()

Some responses may include a bulk data component. These will be distinguished
by having a 'bulk' attribute set in the response. Here is an example response::

	b"{'message': 'REP',
	   'id': 0xdeadbeef,
	   'time': 1715738507.234,
	   'data': JSON description of bulk data,
	   'bulk': True}"

The 'bulk' setting in the message contents indicates that a binary data blob
will be sent in a separate message. The message format would look like::

	b'bulk:kpfguide.LASTIMAGE deadbeef 6712437631249763124962431...'

...where the first whitespace separated field is largely noise for the REP
case, the important metadata is the unique id linking the two responses,
but the message structure is identical to the PUB version (which needs the
"topic") so that any bulk data handling code can be shared. The second
whitespace separated field is the same unique identifier found in the JSON
from the other half of the response. All remaining data after the subsequent
whitespace is a pure byte sequence representing the payload. Both messages
must arrive for either component to have any meaning; the 'data' from the
JSON response will include enough information to reconstruct the binary blob,
which at the present time is only envisioned as image data, or more generally,
something that can be represented as a NumPy array. Thus, the 'data' would
include information like the dimensions of the array and its datatype (int16,
uint32, float64, etc.).

The motivation for separating the bulk data into its own message type is
performance. The bulk data would need to be encoded as a string (base64, etc.)
to be usable in JSON; the encoding step alone is very demanding of processor
time, appending it to a JSON structure makes it an order of magnitude slower.
The combination of these additional processing steps is adequate to prevent
a simple client from saturating a basic gigabit network link with continuous
bulk data requests, whereas saturating the link is trivial with raw bytes.


.. _request_types:

Request types
-------------

This section describes the various requests a client can make of the mKTL
daemon via the request/response socket.

.. list-table::

  * - *Request type*
    - *Description*

  * - **GET**
    - Request the current value for a single key. The key is always the name of
      the store, and the name of the item, concatenated with a period. The data
      field will be as in the description of the REQ/REP behavior; bulk data,
      as described above, is sent as raw bytes in a second message.

      The default behavior for a GET request is for a cached value to be
      allowed as the returned response. A client can explicitly request an
      up-to-date value by setting the 'refresh' field to 'True'; in that case,
      the daemon should provide the most up-to-date value available, even if
      that means communicating with a hardware controller to satisfy the
      request.

      Example request/response exchange::

        b"{'request': 'GET',
	   'name': 'kpfpower.OUTLET_1A',
	   'refresh': True,
	   'id': 5742}"

	 b"{'message': 'ACK',
	    'id': 5742,
	    'time': 1723668130.123456}"

	 b"{'message': 'REP',
	    'id': 5742,
	    'time': 1723668130.124,
	    'data': {'bin': 0, 'asc': 'Off'}}"

  * - **SET**
    - Request a change to the value of a single key. Depending on the daemon,
      this could result in a variety of behavior, from simply caching the value
      to slewing a telescope, and anything in-between. The final response
      indicates the request is complete but does not indicate what the new
      item value is.

      Example request/response exchange::

        b"{'request': 'SET',
	   'name': 'kpfpower.OUTLET_1A',
	   'id': 5744,
	   'data': 'On'}"

	b"{'message': 'ACK',
	   'id': 5744,
	   'time': 1723668131.214123}"

	b"{'message': 'REP',
	   'id': 5744,
	   'time': 1723668134.12549}"

      If the SET request results in an error, the response might instead be::

	b"{'message': 'REP',
	   'id': 5744,
	   'time': 1723668132.12549,
	   'error': {'type': 'ValueError', 'text': 'bad input'}}"

  * - **HASH**
    - Request the current hash identifiers for any known configuration blocks
      of a single mKTL store. If no store name is specified, all available hash
      identifiers will be returned, for all known stores. An error will be
      returned if a store is requested and the responding daemon does not have
      a cached configuration for that store.

      The hash is 32 hexadecimal integers. The actual hash format is not
      significant, as long as the source of authority is consistent about
      which hash format it uses, and the format can be bounded to 32
      hexadecimal integers.

      To unify processing the response is always a dictionary of dictionaries,
      even if only one hash is available.

      Example request/response exchange for all hashes::

	b"{'request': 'HASH', 'id': 234}"

	b"{'message': 'ACK',
	   'id': 234,
	   'time': 1723634131.214123}"

	b"{'message': 'REP',
	   'id': 234,
	   'data': {'kpfguide': {'uuid1': 0x84a30b35...,
				 'uuid2': 0x983ae10f...},
		    'kpfmet': {'uuid6': 0xe0377e7d...,
			       'uuid7': 0x7735a20a...,
			       'uuid8': 0x88645dab...,
			       'uuid9': 0x531c14fd...}}}"

      Example request/response exchange for one store::

	b"{'request': 'HASH',
	   'id': 236,
	   'data': 'kpfguide'}"

	b"{'message': 'ACK',
	   'id': 236,
	   'time': 1723634182.214123}"

	b"{'message': 'REP',
	   'id': 236,
	   'data': {'kpfguide': {'uuid1': 0x84a30b35...,
				 'uuid2': 0x983ae10f...}}"

  * - **CONFIG**
    - Request the full configuration contents for a single mKTL store.
      There is no option to dump the configuration data for all known stores.
      A typical client interaction will request the configuration hash first,
      and if the local copy is not a match, request the full contents from
      the daemon to update the local cache.

      The configuration contents are not fully described here, this is just
      a representation of the request. See the
      :ref:`configuration documentation <configuration>` for a full description
      of the data format.

      Example request::

	b"{'request': 'CONFIG',
	   'id': 563,
	   'name': 'kpfguide'}"


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
	  subscribed to those topics, the broadcasts are never
	  sent to the client.

The ZeroMQ messages received by the client include the full topic as the
leading element in the message-as-bytes, followed by a space, followed by
the remainder of the message contents. The structure of a simple broadcast
mimics the form of the request/response exchange described above::

        b"unique_topic_string {'message': 'PUB',
			       'id': eight hexadecimal digits,
			       'time': timestamp for this broadcast,
			       'name': unique mKTL item name,
			       'data': current item value}"

There are two special types of broadcast messages. These are distinguished
by a modifier on the topic string. The first type is the bulk/binary data
broadcast type, as described above for a REP response; there is a similar
PUB broadcast with otherwise exactly the same structure, setting the 'bulk'
flag in the PUB message to True, and the bulk data transmitted in a separate
message. The topic for the bulk message has a 'bulk:' prefix to avoid
accidentally subscribing to bulk messages, since ZeroMQ uses a leading
substring match on the topic when a client initiates a subscription.

The second type of special broadcast message is a bundle of related broadcasts.
If a daemon so chooses, it can collect related telemetry in a single broadcast;
this offers clients the option of treating the entire bundle as an atomic
entity. Each bundle is a sequence of simple JSON messages as described above.

If, for example, there was a bundle of telemetry messages relating to a filter
wheel, the individual items might have keys like::

	deimot.FILTERNAM
	deimot.FILTERORD
	deimot.FILTERRAW

The mKTL daemon could elect to broadcast a single bundle containing all of those
values. The bundle message would have a topic identifier of::

	deimot.FILTER;bundle

The formatting of the on-the-wire message would be::

	b'deimot.FILTER;bundle JSON...'

...where the JSON would be a sequence of individual PUB elements as described
above::

	[{'message': 'PUB', 'id': 0x0123abcd, 'name': deimot.FILTERNAM, ...},
	 {'message': 'PUB', 'id': 0x0123abcd, 'name': deimot.FILTERORD, ...},
	 {'message': 'PUB', 'id': 0x0123abcd, 'name': deimot.FILTERRAW, ...}]

The 'id' field would be identical for all messages in the bundle, but all
remaining fields would vary according to the message contents.


Message fields
--------------

This section is a description of the various fields used in the JSON messaging
described above.

===============	===============================================================
*Field*		*Description*
===============	===============================================================
**request**	Only issued by a client, making a request of a server.
		The potential values for the request field are all described
		in the :ref:`request_types` section.

**message**	Only issued by a server, to be interpreted by the client.
		This is a one-word assertion of the type of content
		represented by this message. It is one of the following
		values:

                =======	==================================================
		**ACK**	Immediate acknowledgement of a request. If this
			response is not received with a very small time
			window after the initial request, the client can
			and should assume the daemon handling that request
			is offline.

		**REP**	A response to a direct request. This will contain
			the full data responding to a request to get a
			value, or the completion status of setting a value.

		**PUB**	An asynchronous broadcast of an event. There aren't
			any other types of message that will arrive on a
			SUB socket, the inclusion of this field is strictly
			for symmetry's sake.
                =======	==================================================

**id**		An eight character hexadecimal value reasonably unique to
		this specific transaction. The 'unique' constraint doesn't
		need to extend beyond a few minutes, at most, for any
		transaction; the id allows the client to tie together
		ACK and REP messages, to combine the JSON with the data
		buffer for a 'bulk' broadcast, and to further associate
		individual PUB messages contained in a 'bundle' broadcast.
		For client-initiated requests, the client is expected to
		provide a sufficiently unique integer to allow it to
		associate all responses with the initial request. For
		daemon-initiated broadcasts, the uniqueness constraint
		should only be applied for a given key, as opposed to
		being unique across an entire store or daemon.

**time**	A UNIX epoch timestamp associated with the generation of
		the event. This is not intended to represent any time
		prior to the actual broadcast or response, it is intended
		to represent the time at which that message was created,
		such that 'now' - 'time' should represent the transmission
		and mKTL handling delay between the daemon and the client.
		This timestamp should not be expected to represent the
		last known change of the value in question, though in some
		(if not most) cases it will be a reasonable approximation.

**name**	The unique mKTL key, or the unique mKTL store name for some
		of the metadata queries. The mKTL key, at the protocol level,
		is a concatenation of the mKTL store name and the item name
		within that store. In KTL parlance, this would be the
		service.KEYWORD name; in EPICS parlance, it would be the full
		IOC+channel name, as one might use with caput or caget on the
		command line.

**data**	The real payload of the message. For a read operation, this
		will be the telemetry requested, whether it be a string,
		integer, floating point number, or short sequence. For a
		response with no data this field will either not be present
		or it will be the JSON null value.

**bulk**	A boolean flag indicating there is a separate bulk-formatted
		message that will contain the bulk data associated with
		the message. If the value is not present, or is the JSON
		null value, or is the JSON False value, there is no bulk
		message.

**error**	A JSON dictionary with information about any error that
		occurred while processing the request. If the value is
		not present or is the JSON null value, no error occurred.
		If it is present, it will have these values:

                =========	============================================
		**type**	Analagous to the Python exception type
				(ValueError, TypeError, etc.).

		**text**	Descriptive text of the error.

		**debug**	Optional additional information about the
				error, such as a Python traceback.
                =========	============================================

		The intent of this error field is not to provide enough
		information for debugging of code, it is intended to
		provide enough information for the client to perform
		meaningful error handling.

===============	===============================================================


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
request port listening on port 10079, the full response from its discovery
listener would be::

    b'on the X:10079'

