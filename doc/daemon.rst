
.. _daemon:

Daemon interface
================

.. py:module:: mKTL.Daemon

A daemon is the source of authority for one or more mKTL items; when a client
gets or sets an item value, that request is handled by the daemon. Exactly
how that request gets handled is entirely up to the daemon code; there are no
restrictions imposed by the mKTL protocol itself, it is up to the daemon to
resolve any consistency issues or conflicting requests.

The default behavior of the :class:`Store` is to act as a caching
key/value store: values come in, values go out, they may or may not persist
across restarts depending on the configuration. This behavior is rarely
sufficient for an application; a typical daemon will implement custom code
behind the getting and setting of individual items. The Python interface
described here expects the user to create custom subclasses of
:class:`Store`, which in turn may instantiate custom subclasses of
:class:`Item`. Background threads are used widely, polling and callbacks
in particular are two areas where dedicated per-item background threads will
invoke any/all registered methods; the author of any custom code should not
assume that calls arriving via these mechanisms will be serialized or
thread-safe to any meaningful degree.


Daemon.Store class
------------------

The :class:`Store` class is the entry point and overall organization
for the daemon; while it provides a common storage location for daemon-wide
functions, such as handling requests and publishing broadcasts, from the
perspective of the developer the :class:`Store` is a container for
the :class:`Item` instances that define the actual behavior of the
system. An incoming request, for example, is not handled by the
:class:`Store`, it is passed to the appropriate :class:`Item` instance for
proper handling.

The :class:`Store` also defines the initialization sequence, if any,
for the daemon: which steps to take upon startup, which
:class:`Item` subclasses to invoke for specific items, whether other
initialization steps must occur such as defining a common communication point
to access a hardware controller, or whether the initial state of a set of
items needs to be manipulated before proceeding with routine operations.

In nearly all cases the developer will need to create a custom
:class:`Store` subclass to satisfy the operational goals of an
individual daemon.

.. autoclass:: Store
   :members:


Daemon.Item class
------------------

The bulk of any daemon-specific logic will occur in :class:`Item` subclasses.
This is where requests get handled, where data gets interpreted, where logic
is defined that could span items within and without the boundaries of the
containing :class:`Store` instance.

Subclass definitions of the :func:`Item.req_refresh`, :func:`Item.req_set`,
and :func:`Item.validate` methods are especially important for defining any
custom behavior. Any method with a `req_` prefix is part of the handling chain
for an inbound request, with :func`Item.req_get` and :func:`Item.req_set`
implementing entry points for their respective operations, though if
necessary :func:`Item.req_get` calls :func:`Item.req_refresh` in order to
acquire the most recent value.

.. autoclass:: Item
   :members: poll, publish, req_get, req_refresh, req_set, validate


.. _markd:

markd executable
----------------

The `markd` executable provides a command-line interface to invoke a
persistent daemon executing a :class:`Store` subclass to implement its core
functionality. The `markd` executable is positioned to be the common point
of entry for any Python-based mKTL daemon.

The command line arguments describe the intended usage:

.. literalinclude:: ./markd.txt
   :language: none

