.. _example_daemon:

Daemon: basics
==============

This example will establish a 'metal' store and items intended to portray
market prices for various precious metals.


Getting started
---------------

.. py:currentmodule:: mktl

The canonical approach to establish an mKTL daemon involves creating a Python
module to represent all of your custom logic. Each of the steps described here
is required, though there is more than one way to satisfy each step.

In order to successfully run the daemon the Python interpreter being used to
start the daemon must be able to import the mKTL module as well as any custom
module(s) implementing the subclass of :class:`Daemon` that encapsulates
the remainder of the functionality.


:class:`Daemon` subclass
------------------------

The structure of the Python module containing the :class:`Daemon` subclass can
be completely arbitrary; for the sake of this example, the code is contained
in a ``Metal`` Python module, and the components described here are in a
``Precious`` submodule.

Within the ``Precious`` submodule we define our subclass. For no reason other
than convenience it is defined with the name ``Daemon``. The structure of the
``Precious.py`` file will be as follows::

    import mktl

    class Daemon(mktl.Daemon):

        def setup(self):
	    pass

	def setup_final(self):
	    pass


:class:`Item` subclasses
------------------------

The items represent the interface the daemon presents to its clients; the
application-specific functionality that motivates the use of mKTL is exposed
via items, and for most applications this means one or more custom :class:`Item`
subclasses.

An example subclass would have a structure like the following::

    class MarketPriced(mktl.Item):

        def __init__(self, *args, **kwargs):
            mktl.Item.__init__(self, *args, **kwargs)
	    # Additional initialization steps would generally follow the
	    # regular initialization from the base class. In this case,
	    # our market-prices should update once per day:
	    self.poll(86400)

        def req_refresh(self):
            # Determine the current value for this item and return it.
	    pass

	def req_set(self, request):
            # Receive a request to set a new value for this item; return
	    # once the request is complete.
	    pass

Note in particular the documentation for :func:`Item.req_refresh` and
:func:`Item.req_set`, as it covers the expected behavior of each method.
For our example, the various items are intended to represent the market
spot price of different precious metals. In this case, the
:func:`req_refresh` method may request the current value from a website,
and :func:`req_set` would not be defined, since we don't get to change
the actual market value. To pick one example::


    class Gold(MarketPriced)

        def req_refresh(self):
            spot = get_spot_value('gold', 'usd', 'grams')
	    spot = float(spot)

	    payload = dict()
	    payload['value'] = spot
	    payload['time'] = time.time()

	    return spot



:func:`Daemon.setup` method
---------------------------

:func:`Daemon.setup` is the first pass of application-level setup for the
daemon. This is where instantiation of any custom subclasses of :class:`Item`
needs to
occur, otherwise the various items defined for this daemon within this store
will be populated with default, caching-only instances; this occurs immediately
after the :class:`Daemon` invokes :func:`Daemon.setup`.

Any custom initialization action for the daemon is reasonable to include as a
call in :func:`Daemon.setup`, such as initializing a connection to a controller,
especially if it is a pre-requisite for any of the custom :class:`Item`
subclasses. For the example defined here, we only need to instantiate our
custom subclasses for each of the different precious metals for which we are
publishing prices::

    def setup(self):

        self.add_item(Gold, 'GOLD')
        self.add_item(Silver, 'SILVER')
        self.add_item(Platinum, 'PLATINUM')

Note the use of :func:`Daemon.add_item` here when establishing :class:`Item`
instances for those items that the daemon is authoritative for. The
:func:`Daemon.add_item` method tweaks the instantiation process such that the
:class:`Item` is properly configured as an authoritative instance.


:func:`Daemon.setup_final` method
---------------------------------

If this store contained any logic that must be executed only after all the items
have been fully instantiated, and/or populated with any previously cached
persistent values, that logic should be invoked in the:func:`Daemon.setup_final`
method. Most daemons will not take advantage of this method; this example daemon
is likewise too simple to require it.


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
        mktl.Config.File.save_daemon('metal', 'precious', items)
        mktl.Daemon.__init__(self, *args, **kwargs)

It's more likely that the JSON configuration is written out as a file, ready
to be used by the daemon. The file can be anywhere, so long as it is accessible
upon startup, after which the file is no longer referenced in any way. The
configuration file is expected to contain a single JSON-formatted dictionary,
with a :ref:`dictionary for each item <items>`. Whitespace is not important,
so long as a JSON parser understands the file contents.

The following is a configuration block appropriate for the items used in this
example:

.. literalinclude:: ./precious.json


Starting the daemon
-------------------

The :ref:`markd` executable provides a common entry point for a persistent
daemon. Assuming the default search path is set up correctly, for the example
outlined here the invocation would resemble::

    markd metal precious --module Metal.Precious -c precious_metals.json
