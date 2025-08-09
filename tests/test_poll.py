import time
import mktl

try:
    import numpy
except ImportError:
    numpy = None


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


def test_low_frequency():
    test_low_frequency.calls = list()

    def callback():
        test_low_frequency.calls.append(time.time())

    # Polling at 1 kilohertz is not expected to occur often, but it's not
    # unreasonable. The jitter should be measurable and low.

    frequency = 1000
    period = 1.0 / frequency
    window = 0.2

    mktl.poll.start(callback, period)
    time.sleep(window)
    mktl.poll.stop(callback)

    calls = len(test_low_frequency.calls)
    expected_calls = window * frequency
    assert calls > expected_calls - 5
    assert calls < expected_calls + 5


    if numpy is not None:
        timestamps = list(test_low_frequency.calls)
        timestamps.reverse()

        previous = timestamps.pop()
        deltas = list()
        for timestamp in timestamps:
            delta = timestamp - previous
            previous = timestamp
            deltas.append(delta)

        deltas = numpy.array(deltas)
        standard_deviation = numpy.std(deltas)

        assert standard_deviation < 0.02


def test_high_frequency():
    test_high_frequency.calls = list()

    def callback():
        test_high_frequency.calls.append(time.time())

    # Polling at 1 megahertz is well beyond any expected mKTL application.

    frequency = 1000000
    period = 1.0 / frequency
    window = 0.2

    mktl.poll.start(callback, period)
    time.sleep(window)
    mktl.poll.stop(callback)

    calls = len(test_high_frequency.calls)
    expected_calls = window * frequency
    assert calls > expected_calls - frequency / 100
    assert calls < expected_calls + frequency / 100

    # Yes, it's strange that we're winding up with a large number of "extra"
    # polling calls. No, it has not been looked into.


    if numpy is not None:
        timestamps = list(test_high_frequency.calls)
        timestamps.reverse()

        previous = timestamps.pop()
        deltas = list()
        for timestamp in timestamps:
            delta = timestamp - previous
            previous = timestamp
            deltas.append(delta)

        deltas = numpy.array(deltas)
        standard_deviation = numpy.std(deltas)

        assert standard_deviation < 0.0005


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
