.. _example_get:

Client: get a value
===================

This example will use the 'population' store and the item 'CRAZY'. The
objective is to retrieve the current value for 'population.CRAZY'.


.. _getting_started:

Getting started
---------------

.. py:currentmodule:: mktl

An :class:`Item` instance is required to perform any client operations; the
:func:`get` method should be invoked to acquire a cached singleton for
any/all subsequent use. The required boilerplate is short::

    import mktl
    crazy = mktl.get('population.CRAZY')
    crazy = mktl.get('population', 'CRAZY')
    crazy = mktl.get('population', 'crazy')
    crazy = mktl.get('PoPuLaTiOn', 'crazy')

The ``crazy`` reference here will be identical for each different invocation
shown. The important part is that we now have a :class:`Item` that can be used
for subsequent calls. A ``ValueError`` exception will be raised if no
configuration is available for that store; a ``KeyError`` exception will be
raised if the key does not exist.


Calling :func:`Item.get`
------------------------

Most exceptions do not need to be caught if you are calling :func:`Item.get`
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

With no arguments the call to :func:`Item.get` will return the locally
cached value if the item is subscribed to broadcasts, or request the value
from the authoritative daemon if it is not. The caller can bypass the local
cache if it is relevant for their application, explicitly requesting that
the daemon update (and broadcast) the current value while handling this call::

    current = crazy.get(refresh=True)

For nearly all applications the ``refresh`` argument does not need to be
specified.


Handling return values
----------------------

The value returned by :func:`Item.get` is a Python native object, either a
primitive, such as an integer or floating point number, or something like a
numpy array. For example::

    >>> current
    True

If the item represents a bulk value the returned reference will not be a Python
dictionary, it will be a numpy array. If no value is availble the current value
could simply be ``None``.


Full example
------------

Putting it all together::

    import mktl
    crazy = mktl.get('population.CRAZY')
    current = crazy.get()

    if current is None:
        print('The population craziness is unknown.')
    else:
        craziness = current
        if craziness == True:
            print('The population is crazy.')
        else:
            print('The population is sane.')

It's worth mentioning that the above comparison can be further simplified,
if one were not writing an example specifically to describe the behavior of
:func:`Item.get`. An :class:`Item` instance can be used directly in comparison
operations, and will behave as if the Item.value is being used directly::

    import mktl
    crazy = mktl.get('population.CRAZY')
    crazy.subscribe()	# For this example calling crazy.get() would also work

    if crazy == None:
        print('The population craziness is unknown.')
    elif craziness == True:
        print('The population is crazy.')
    else:
        print('The population is sane.')

