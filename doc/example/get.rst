Client: get a value
===================

This example will use the 'population' store and the item 'CRAZY'. The
objective is to retrieve the current value for 'population.CRAZY'.


.. _getting_started:

Getting started
---------------

.. py:currentmodule:: mKTL.Client

An :class:`Item` instance is required to perform any client operations; the
:func:`mKTL.get` method should be invoked to acquire a cached singleton for
any/all subsequent use. The required boilerplate is short::

    import mKTL
    crazy = mKTL.get('population.CRAZY')
    crazy = mKTL.get('population', 'CRAZY')
    crazy = mKTL.get('population', 'crazy')
    crazy = mKTL.get('PoPuLaTiOn', 'crazy')

The ``crazy`` reference here will be identical for each different invocation
shown. The important part is that we now have a :class:`Item` that can be used
for subsequent calls. A ``ValueError`` exception will be raised if no
configuration is available for that store; a ``KeyError`` exception will be
raised if the key does not exist.


Calling :func:`Item.get`
------------------------

Most exceptions do not need to be caught if you are calling :func:`mKTL.get`
directly; an exception here is unexpected, and likely violates any reasonable
attempts at error recovery that might be performed. This section shows exception
handling for completeness's sake::

    try:
        current = crazy.get()
    except zmq.ZMQError:
        # The answering daemon could not be contacted. The timeout for the
	# initial request is short, just 0.05 seconds, so a failure of this
	# type should likewise be fast.
	raise

With no arguments the call to :func:`Item.get`` will return the locally
cached value if the item is subscribed to broadcasts, or request the value
from the authoritative daemon if it is not. The caller can bypass the local
cache if it is relevant for their application, explicitly requesting that
the daemon update (and broadcast) the current value while handling this call::

    current = crazy.get(refresh=True)

For nearly all applications the ``refresh`` argument does not need to be
specified.


Handling return values
----------------------

The value returned by :func:`Item.get` is, for most item types, a dictionary,
containing 'asc' and 'bin' keys, where the 'asc' value is a human-readable,
string representation of the 'bin' value, which will be a Python-native format.
For example::

    >>> current['asc']
    'On'
    >>> current['bin']
    True

If the item represents a bulk value the returned reference will not be a Python
dictionary, it will be a numpy array. If no value is availble the current value
could simply be ``None``.


Full example
------------

Requesting a value, without the discussion of the various options::

    import mKTL
    crazy = mKTL.get('population.CRAZY')
    current = crazy.get()

    if current is None:
        print('The population craziness is unknown.')
    else:
    	craziness = current['bin']
        if craziness == True:
            print('The population is crazy.')
        else:
            print('The population is sane.')

