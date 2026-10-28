""" The primary objective of this module is to implement a variant of
    time.time() that returns a value in microseconds, similar to how
    time.time_ns() returns nanoseconds. The standard time module is
    quite fast, and is implemented in C; while the code implemented
    here strives to be lean it will never be as performant.
"""

import time as time_module

sleep = time_module.sleep
time = time_module.time
time_s = time_module.time


def time_us():
    """ Return the current time in microseconds since the Epoch.
        This relies on :func:`time.time` returning a floating point
        number containing fractional seconds.
    """

    # While time.time_ns() does exist, it was added in Python 3.7,
    # and what we really want is microseconds instead of nanoseconds.
    # JSON integers are reliable up to 53 bits, which comfortably
    # accommodates timestamps for the next 200+ years; nanoseconds
    # wouldn't fit.

    timestamp = time_module.time()

    # The extra steps to turn this into an integer basically doubles
    # the time required to generate this timestamp, compared to just
    # calling time.time() directly. It's still a factor of ten faster
    # than using datetime and accessing microseconds separately.

    # This is a duplication of the math in to_microseconds(); calling
    # that method instead of duplicating the math results in something
    # like a 20% increase in CPU usage.

    timestamp_us = timestamp * 1000000
    timestamp_us = round(timestamp_us)

    return timestamp_us


def to_seconds(microseconds):
    """ Convert from microseconds to seconds. The result is returned as
        a floating point number; there may be a loss of precision in the
        conversion.
    """

    seconds = microseconds / 1000000.0
    return seconds


def to_microseconds(seconds):
    """ Convert from seconds to microseconds. The result is returned as
        an integer.
    """

    microseconds = seconds * 1000000
    microseconds = round(microseconds)
    return microseconds


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
