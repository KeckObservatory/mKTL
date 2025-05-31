Executables
===========

.. _mark:

mark
----

`mark` is intended to be the primary command line interface for client
interactions with mKTL. It doesn't exist yet, but when it does, the
command set is expected to be something akin to::

    mark get key1 key2 key3
    mark plot key1 key2 key3
    mark set key1=foo key2=bar key3=baz


markd
-----

Refer to the section covering the :ref:`markd` in the :ref:`daemon`
documentation.


.. _markguided:

markguided
----------

The `markguided` persistent daemon is a discovery aid, listening for UDP
broadcasts on a well-known port number so that clients can be directed to
a specific mKTL daemon handling requests for a specific store, or fraction
of a store. While having a `markguided` daemon running is not a strict
requirement it is a key component of automated discovery of mKTL stores on
a local network.
