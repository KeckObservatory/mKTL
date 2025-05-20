Daemon interface
================

A daemon is the source of authority for one or more mKTL items; when a client
gets or sets an item value, that request is handled by the daemon. Exactly
how that request gets handled is entirely up to the daemon code; there are no
restrictions imposed by the mKTL protocol itself, it is up to the daemon to
resolve any consistency issues or conflicting requests.

The default behavior of the :class:`mKTL.Daemon.Store` is to act as a caching
key/value store: values come in, values go out, they may or may not persist
across restarts depending on the configuration. This behavior is rarely
sufficient for an application; a typical daemon will implement custom code
behind the getting and setting of individual items. The reference implementation
in Python expects the user to create custom subclasses of
:class:`mKTL.Daemon.Store`, which in turn may instantiate custom subclasses of
:class:`mKTL.Daemon.Item`.


Daemon classes
--------------

.. autoclass:: mKTL.Daemon.Store
   :members:

.. autoclass:: mKTL.Daemon.Item
   :members: poll, publish, req_get, req_refresh, req_set, validate


markd executable
----------------
