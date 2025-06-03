Client: register a callback
===========================

This example will use the 'oven' store and the item 'TEMP'. The objective is
to handle all broadcasts for 'oven.TEMP'; a callback method will be defined
that performs any/all desired operations whenever the value changes. This
callback method will be invoked asynchronously whenever a new broadcast
arrives.

The toy example here will calculate and print an exponentially weighted
average.


Getting started
---------------

.. py:currentmodule:: mKTL.Client

See the :ref:`getting_started` section of the :ref:`example_get` example for
more details. We'll get right to it::

    import mKTL
    temp = mKTL.get('oven.TEMP')


Defining a callback
-------------------

The expected signature of a callback method is::

    def my_callback(item, new_value, new_timestamp):

These arguments are always passed to the callback; that doesn't necessarily
mean the callback has to use them, a common pattern is to define a callback
that ignores the arguments provided, an approach made easier by the use of
:func:`mKTL.get`. First, a callback that uses the arguments::

    def average(item, temp, time):

        factor = 0.01
        new_weight = factor
        old_weight = 1 - factor

        if average.computed is None:
            average.computed = temp
        else:
            average.computed = new_weight * temp + old_weight * average.computed

        print("%.3f %s average: %.1f" % (time, item.key, average.computed)

    average.computed = None


...and an alternate version, using :func:`mKTL.get`::

    def average(*args, **kwargs):

        temp = mKTL.get('oven', 'TEMP')

        factor = 0.01
        new_weight = factor
        old_weight = 1 - factor

        if average.computed is None:
            average.computed = float(temp)
        else:
            average.computed = new_weight * temp + old_weight * average.computed

	timestamp = temp.cached_timestamp
        print("%.3f %s average: %.1f" % (timestamp, temp.key, average.computed)

    average.computed = None


These two approaches are functionally identical for this simple example.
The second approach, relying on :func:`mKTL.get`, becomes appealing
when multiple items need to be inspected in a given callback; for example,
if the current temperature were being compared to the current setpoint.


Calling :func:`Item.register`
-----------------------------

Once the callback method is defined it needs to be associated with the
:class:`Item` instance, so that the callback is invoked every time the value
of that item changes. This is accomplished via :func:`Item.register`::

    temp.register(average)

:func:`Item.register` will invoke :func:`Item.subscribe` if the caller did
not already do so in some other context.


Full example
------------

Putting it all together::

    import mKTL
    temp = mKTL.get('oven.TEMP')

    def callback(*args, **kwargs):
        temp = mKTL.get('oven.TEMP')
        value = float(temp)
	time = temp.cached_timestamp
	print ("%.3f oven.TEMP: %.1f" % (time, value))

     temp.register(callback)

