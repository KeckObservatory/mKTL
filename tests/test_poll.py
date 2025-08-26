import time
import mktl

try:
    import numpy
except ImportError:
    numpy = None


class Referenced:
    def a_method(self):
        pass


def test_references():
    """ The mKTL polling functionality promises to only have one polling
        entity active for a given method. We can wind up in a bad place
        if there is a mismatch in how that uniqueness constraint is applied,
        so make sure it's working as expected.
    """

    def callback():
        pass

    mktl.poll.start(callback, period=1)
    period = mktl.poll.period(callback)
    assert period is not None
    assert period == 1


    referenced = Referenced()
    mktl.poll.start(referenced.a_method, period=1)
    period = mktl.poll.period(referenced.a_method)
    assert period is not None
    assert period == 1



def test_basics():

    test_basics.polled = False
    assert test_basics.polled == False

    def callback():
        test_basics.polled = True

    mktl.poll.start(callback, 0.1)
    time.sleep(0.12)

    assert test_basics.polled == True


    mktl.poll.stop(callback)
    test_basics.polled = False
    time.sleep(0.12)

    assert test_basics.polled == False


    mktl.poll.start(callback, 0.1)
    time.sleep(0.12)

    assert test_basics.polled == True


    mktl.poll.start(callback, period=None)
    test_basics.polled = False
    time.sleep(0.12)

    assert test_basics.polled == False

    # Redundant calls should be a no-op.

    mktl.poll.start(callback, period=0)
    mktl.poll.start(callback, period=None)
    mktl.poll.stop(callback)


    mktl.poll.start(callback, period=None)
    del(callback)
    test_basics.polled = False
    time.sleep(0.12)

    assert test_basics.polled == False


def test_low_frequency():
    test_low_frequency.calls = list()

    def callback():
        test_low_frequency.calls.append(time.time())

    # Polling at 0.1 kilohertz is well within what could be used by
    # applications. The jitter should be measurable and low.

    frequency = 100
    period = 1.0 / frequency
    window = 0.2

    mktl.poll.start(callback, period)
    time.sleep(window)
    mktl.poll.stop(callback)

    calls = len(test_low_frequency.calls)
    expected_calls = window * frequency
    assert calls > expected_calls - 1
    assert calls <= expected_calls + 1


    if numpy is not None:
        timestamps = list(test_low_frequency.calls)
        timestamps.reverse()
        previous = timestamps.pop()
        timestamps.reverse()

        deltas = list()
        for timestamp in timestamps:
            delta = timestamp - previous
            previous = timestamp
            deltas.append(delta)

        deltas = numpy.array(deltas)
        standard_deviation = numpy.std(deltas)

        assert standard_deviation < 0.001


def test_high_frequency():
    test_high_frequency.calls = list()

    def callback():
        test_high_frequency.calls.append(time.time())

    # Polling at 10 kilohertz is beyond any expected mKTL application. Pushing
    # to higher frequcny gets into territory where the callbacks can't occur
    # quickly enough to pass this simple test.

    frequency = 10000
    period = 1.0 / frequency
    window = 0.2

    mktl.poll.start(callback, period)
    time.sleep(window)
    mktl.poll.stop(callback)

    calls = len(test_high_frequency.calls)
    expected_calls = window * frequency
    assert calls > expected_calls - 1
    assert calls < expected_calls + 5

    # Yes, it's strange that we're winding up with "extra" polling calls.
    # One extra call is within what you might expect if you count calls at
    # both ends of the test window. For 2000 expected calls you will typically
    # see 2001-2003 actual calls.


    if numpy is not None:
        timestamps = list(test_high_frequency.calls)
        timestamps.reverse()
        previous = timestamps.pop()
        timestamps.reverse()

        deltas = list()
        for timestamp in timestamps:
            delta = timestamp - previous
            previous = timestamp
            deltas.append(delta)

        deltas = numpy.array(deltas)
        standard_deviation = numpy.std(deltas)

        assert standard_deviation < 0.001


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
