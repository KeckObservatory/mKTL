Daemon: initial setup
=====================

This example will establish a 'metal' store and items intended to portray
market prices for various precious metals.


Getting started
---------------

.. py:currentmodule:: mKTL.Daemon

The canonical approach to establish an mKTL daemon involves creating a Python
module to represent all of your custom logic. Each of the steps described here
is required, though there is more than one way to satisfy each step.

In order to successfully run the daemon the Python interpreter being used to
start the daemon must be able to import the mKTL module as well as any custom
module(s) implementing the subclass of :class:`Store` that encapsulates
the remainder of the functionality.


:class:`Store` subclass
-----------------------


:func:`Store.setup` method
--------------------------


JSON description of items
-------------------------

The :ref:`configuration syntax <configuration>` describing a set of items is a
JSON associative array. When a daemon first starts it must have a complete JSON
description of every item; this forms the core of the configuration managed by
that daemon, which is responsible for adding the additional metadata required
for proper client interactions.

The JSON contents can be generated at run time and 'saved' for future use by
other mKTL calls. This is the approach taken by the KTL translation backend,
where the JSON is a repackaging of the configuration metadata supplied by
KTL API calls; with a JSON-like dictionary in hand, the daemon would have
lines like the following in its initialization method::

    def __init__(self, *args, **kwargs):

        items = generate_config()
        mKTL.Config.File.save_daemon('metal', 'precious', items)
        mKTL.Daemon.Store.__init__(self, *args, **kwargs)

It's more likely that the JSON configuration is written out as a file, ready
to be used by the daemon. The file can be anywhere, so long as it is accessible
upon startup; it is not accessed other than upon initial startup.



Starting the daemon
-------------------

The :ref:`markd` executable provides a common entry point for a persistent
daemon. Assuming the default search path is set up correctly, for the example
outlined here the invocation would resemble::

    markd metal precious --module Metal.Precious -c precious_metals.json
