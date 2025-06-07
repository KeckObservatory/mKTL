
Protocol interface
==================

Each aspect of the mKTL protocol is split into two different components: the
client-facing half, and a server-facing half. The interfaces described here
are generally not exposed to direct usage, they support the end-user
functionality exposed in the :ref:`client` and :ref:`daemon` code.

.. py:module:: mKTL.Protocol.Request

Request client
--------------

.. autoclass:: Client
   :members:


The :class:`Pending` class
----------------------------------

.. autoclass:: Pending
   :members:

Request server
--------------

.. autoclass:: Server
   :members:


.. py:module:: mKTL.Protocol.Publish

Publish client
--------------

.. autoclass:: Client
   :members:

Publish server
--------------

.. autoclass:: Server
   :members:

