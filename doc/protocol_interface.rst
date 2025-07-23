
Protocol interface
==================

Each aspect of the mKTL protocol is split into two different components: the
client-facing half, and a server-facing half. The interfaces described here
are generally not exposed to direct usage, they support the end-user
functionality exposed in the :ref:`client` and :ref:`daemon` code.

.. py:module:: mktl.protocol.message

Message classes
----------------

.. autoclass:: Message
   :members:

.. autoclass:: Request
   :members:


.. py:module:: mktl.protocol.request

Request client
--------------

.. autofunction:: client

.. autofunction:: send

.. autoclass:: Client
   :members:

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
   :members:

