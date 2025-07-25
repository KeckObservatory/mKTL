
.. _daemon:

Daemon interface
================

A daemon is the source of authority for one or more mKTL items; when a client
gets or sets an item value, that request is handled by the daemon. Exactly
how that request gets handled is entirely up to the daemon code; there are no
restrictions imposed by the mKTL protocol itself, it is up to the daemon to
resolve any consistency issues or conflicting requests.

The default behavior of the :class:`mktl.Store` is to act as a caching
key/value store: values come in, values go out, they may or may not persist
across restarts depending on the configuration. This behavior is rarely
sufficient for an application; a typical daemon will implement custom code
behind the getting and setting of individual items. The Python interface
described here expects the user to create custom subclasses of
:class:`mktl.Daemon`, which in turn may instantiate custom subclasses of
:class:`mktl.Item`. Background threads are used widely, polling and callbacks
in particular are two areas where dedicated per-item background threads will
invoke any/all registered methods; the author of any custom code should not
assume that calls arriving via these mechanisms will be serialized or
thread-safe to any meaningful degree.


The Daemon class
----------------

The :class:`mktl.Daemon` class is the entry point and overall organization
for the daemon; while it provides a common storage location for daemon-wide
functions, such as handling requests and publishing broadcasts, from the
perspective of the developer the :class:`mktl.Store` is a container for
the :class:`mktl.Item` instances that define the actual behavior of the
system. An incoming set request, for example, is not handled by the
any higher level construct, it is passed to the appropriate :class:`mktl.Item`
instance for proper handling.

The :class:`mktl.Daemon` also defines the initialization sequence, if any,
for the daemon: which steps to take upon startup, which
:class:`mktl.Item` subclasses to invoke for specific items, whether other
initialization steps must occur such as defining a common communication point
to access a hardware controller, or whether the initial state of a set of
items needs to be manipulated before proceeding with routine operations.

In nearly all cases the developer will need to create a custom
:class:`mktl.Daemon` subclass to satisfy the operational goals of an
individual daemon.

.. autoclass:: mktl.Daemon
   :members:


The Item class, expanded
------------------------

The bulk of any daemon-specific logic will occur in :class:`mktl.Item`
subclasses. This is where requests get handled, where data gets interpreted,
where logic is defined that could span items within and without the boundaries
of the containing :class:`mktl.Daemon`.

Subclass definitions of the :func:`mktl.Item.req_refresh`,
:func:`mktl.Item.req_set`, and :func:`mktl.Item.validate` methods
are especially important for defining any
custom behavior. Any method with a `req_` prefix is part of the handling chain
for an inbound request, with :func`mktl.Item.req_get` and
:func:`mktl.Item.req_set` implementing entry points for their respective
operations, though if necessary :func:`mktl.Item.req_get` calls
:func:`mktl.Item.req_refresh` in order to acquire the most recent value.

.. autoclass:: mktl.Item
   :members: poll, publish, req_get, req_poll, req_refresh, req_set, validate


markd executable
----------------

The `markd` executable provides a command-line interface to invoke a
persistent daemon executing a :class:`mktl.Daemon` subclass as described above.
It is the natural starting point for any persistent daemon implementing
the scheme described in this document, since that is the precise purpose
it is written for.

Refer to the section covering :ref:`markd` in the :ref:`executables`
documentation for additional details.
