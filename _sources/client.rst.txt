
.. _client:

Client interface
================

A client is any software component interacting with a daemon, in the form of
issuing requests, receiving responses to requests, and receiving asynchronous
updates of new item values. The Python interface described here makes liberal
use of background threads, callbacks in particular can and will arrive from
background threads as asynchronous updates arrive.

Unlike the :ref:`daemon`, a typical client application will not need subclasses
of the classes defined here, they are expected to be used directly, as-is.


Getting started
---------------

mKTL will cache information locally; there are no restrictions on where this
information gets cached, other than it needs to be cached somewhere. The
default location for this cache is::

    $HOME/.mKTL

You can override this location by setting the ``MKTL_HOME`` environment
variable to the absolute path of your choice; any directory specified in
this fashion will be created if it does not already exist. Alternatively,
the program may invoke the :func:`mktl.home` method to specify the location
at run time.

.. autofunction:: mktl.home

You may need to pre-populate your local cache with information from the
brokers handling the configuration for the store(s) you wish to access.
The :ref:`mark` command line tool will handle this process; for a given
IP address or hostname, you would invoke::

    mark discover 192.168.5.34

This discovery process will query that address for any available configurations,
but more importantly, will cache the address of that broker and use it again in
the future if/when discovering new services, without an explicit request to do
so. In other words, it should only be necessary to run this discovery process
a single time in order to gain access to a new set of mKTL stores.

The :func:`mktl.get` method is the universal entry point to retrieve a
:class:`mktl.Store` or :class:`mktl.Item` instance; client configuration is
automatically refreshed if necessary, and the remainder of the connection logic
is handled by the :class:`mktl.Store`.

All other client operations, such as getting and setting item values, are
handled via the :class:`mktl.Item` instance.

.. autofunction:: mktl.get


The Store class
---------------

The :class:`mktl.Store` class is primarily an organizational structure,
providing a dictionary-like interface to retrieve :class:`mktl.Item` instances.

.. autoclass:: mktl.Store
   :members:


The Item class
--------------

The bulk of the client interactions will occur with the :class:`mktl.Item`
class. In addition to the methods described here an :class:`mktl.Item` instance
can be used with Python operators, such as addition/concatenation or
multiplication.
The behavior of an :class:`mktl.Item` when used in this fashion will be aligned
with the native Python binary type for the item value; for example, if an
item test.BAR has an integer value 12, ``test.BAR + 5`` will return the integer
value 17. If test.BAR is instead the string value '12', the same operation
would raise a TypeError exception; however, ``test.BAR + '5'`` would return
the string value '125', just like you would expect for string concatenation.

.. autoclass:: mktl.Item
   :members: get, register, set, subscribe, value
