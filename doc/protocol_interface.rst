
.. py:module:: mktl.protocol

Protocol interface
==================

Each aspect of the mKTL protocol is split into two different components: the
client-facing half, and a server-facing half. The interfaces described here
are generally not exposed to direct usage, they support the end-user
functionality exposed in the :class:`Item <mktl.Item>` class.

Message handling is divided into similar phases, and the various methods
involved have consistent names to indicate their role in the handling chain.

.. list-table::

  * - **1.**
    - The layer closest to the transport is defined in ``incoming`` or
      ``outgoing`` methods, depending on the direction of the data flow.
      These are the methods that directly receive or send messages to the
      transport layer, and provide final interpretation of
      :class:`Message <message.Message>` instances. This layer is sufficient
      for all publish/subscribe handling, and for outbound requests.

  * - **2.**
    - Responding to an incoming request starts with a handling layer; the
      methods in this layer are visible in the :class:`request.Server`
      class. :func:`req_incoming() <request.Server.req_incoming>`
      reconstructs a :class:`message.Request` instance; that instance is
      passed to :class:`req_handler() <request.Server.req_handler>` for
      dispatch to an appropriate handling endpoint, such as
      :func:`req_get() <mktl.Item.req_get>` or
      :func:`req_set() <mktl.Item.req_set>`. The :class:`message.Request`
      instance stops here, as well as its :class:`message.Payload`, if any.

  * - **3.**
    - The last step in the handling chain is a method to perform the
      request. Methods like :func:`perform_get() <mktl.Item.perform_get>`
      and :func:`perform_set() <mktl.Item.perform_set>`
      have a narrower scope, and are intended to be application-specific,
      implementing core application logic as needed for those items,
      and do not require awareness of any message handling concepts.

The above steps are not all contained to the protocol interface; the
first two layers largely are, though the :func:`req_handler()
<request.Server.req_handler>` method is subclassed in the :ref:`daemon`
code, and endpoints like :func:`req_get() <mktl.Item.req_get>` or
or :func:`perform_get() <mktl.Item.perform_get>` are defined as part
of the :class:`mktl.Item` class. The intent of isolating the
application-specific awareness to the last layer is that an application
developer can apply their customizations there, without needing to be
aware of the other steps in the handling chain.


.. py:module:: mktl.protocol.message

Payload class
-------------

.. autoclass:: Payload
   :members:


Message classes
----------------

.. autoclass:: Message
   :members:

   .. automethod:: _finalize

.. autoclass:: Broadcast
   :members:

.. autoclass:: Request
   :members:


.. py:module:: mktl.protocol.request

Request client
--------------

.. autofunction:: client

.. autofunction:: send

.. autoclass:: Client
   :members: send

Request server
--------------

.. autoclass:: Server
   :members:


.. py:module:: mktl.protocol.publish

Publish client
--------------

.. autofunction:: client

.. autoclass:: Client
   :members:

Publish server
--------------

.. autoclass:: Server
   :members: publish

