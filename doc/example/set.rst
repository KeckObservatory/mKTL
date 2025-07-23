Client: set a value
===================

This example will use the 'team' store and the item 'SCORE'. The
objective is to set a new value for 'team.SCORE'.


Getting started
---------------

.. py:currentmodule:: mktl

See the :ref:`getting_started` section of the :ref:`example_get` example for
more details. We'll get right to it::

    import mktl
    score = mktl.get('team.SCORE')


Calling :func:`Item.set`
------------------------

The :func:`Item.set` method has one required argument, the new value::

    score.set(44)

The default behavior of this call is to block until the call is handled
successfully on the daemon side. It is up to the daemon to decide what
that means; a daemon may complete a set request instantly, or it may delay
completing the request until some specific set of actions are themselves
complete; for example, if a set request would cause a mechanism to move
to a new physical position, the daemon may elect to not complete the
request until the physical move is complete. Depending on the application,
having this call block until completion may not be desirable-- for example,
in a graphical user interface. In that case, you can issue a non-blocking
set request::

    score.set(44, wait=False)

With the ``wait=False`` argument the call to :func:`Item.set` will return
immediately after the request is successfully delivered to the daemon for
handling. This is the best option if the client application is not concerned
about responding to the completion of this request. If the client application
does want explicit notification when the request is complete, :func:`Item.set`
returns a :class:`protocol.message.Request` instance that enables this usage
pattern::

    pending = score.set(44, wait=False)
    pending.poll()
    pending.wait(timeout=5)

One example of where that might be helpful is if a series of simultaneous
operations are desired, but the caller wants to ensure they all complete
before returning. Something like::

    waitfor = list()
    for item,new_value in settable:
        pending = item.set(new_value, wait=False)
        waitfor.append(pending)

    for pending in waitfor:
        pending.wait()


In-line modification
--------------------

The :class:`Item` class supports in-place modification of values. Incrementing
the score can be done a few different ways::

    import mktl
    score = mktl.get('team.SCORE')

    # Explicit get() and set():
    old_score = score.get()['bin']
    new_score = old_score + 1
    score.set(new_score)

    # Using operator support:
    score.subscribe()
    score.set(score + 1)

    # Using in-place modification:
    score.subscribe()	# Not required, the in-place call will subscribe()
    score += 1

All three of the approaches shown yield the same result.


Full example
------------

Putting it all together::

    import mktl
    score = mktl.get('team.SCORE')
    score.set(44)

