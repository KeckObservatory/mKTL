
.. _client:

Client interface
================

.. py:module:: mKTL.Client

A client is any software component interacting with a daemon, in the form of
issuing requests, receiving responses to requests, and receiving asynchronous
updates of new item values. The Python interface described here makes liberal
use of background threads, callbacks in particular can and will arrive from
background threads as asynchronous updates arrive. the author of any custom
code should not assume that calls arriving via these mechanisms will be
serialized or thread-safe to any meaningful degree.

Unlike the :ref:`daemon`, a typical client application will not need subclasses
of the classes defined here, they are expected to be used directly, as-is.


Getting started
---------------

The :func:`mKTL.get` method is the universal entry point to retrieve a
:class:`Store` or :class:`Item` instance; client configuration is automatically
refreshed if necessary, and the remainder of the connection logic is handled
by the :class:`Store`.

All other client operations, such as getting and setting item values, are
handled via the :class:`Item` instance.

.. autofunction:: mKTL.get


Client.Store class
------------------

The :class:`Store` class is primarily an organizational structure, providing
a dictionary-style interface to retrieve :class:`Item` instances.

.. autoclass:: Store
   :members:


Client.Item class
-----------------

The bulk of the client interactions will occur with the :class:`Item` class.
In addition to the methods described here an :class:`Item` instance can be
used with Python operators, such as addition/concatenation or multiplication.
The behavior of an :class:`Item` when used in this fashion will be aligned
with the native Python binary type for the item value; for example, if an
item test.BAR has an integer value 12, ``test.BAR + 5`` will return 17; if
the value is instead the string value '12', the same operation will raise a
TypeError exception.

.. autoclass:: Item
   :members:
