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


def time_us(timestamp=None):
    """ Return the current time in microseconds since the Epoch. If
        a *timestamp* is specified it should be a floating point number
        representing seconds since the Epoch; if not specified, this
        relies on :func:`time.time` returning a floating point number
        containing fractional seconds.
    """

    # While time.time_ns() does exist, it was added in Python 3.7,
    # and what we really want is microseconds instead of nanoseconds.
    # JSON integers are reliable up to 53 bits, which comfortably
    # accommodates timestamps for the next 200+ years; nanoseconds
    # wouldn't fit.

    if timestamp is None:
        timestamp = time_module.time()

    # The extra steps to turn this into an integer basically doubles
    # the time required to generate this timestamp, compared to just
    # calling time.time() directly. It's still a factor of ten faster
    # than using datetime and accessing microseconds separately.

    timestamp_us = timestamp * 1000000
    timestamp_us = round(timestamp_us)

    return timestamp_us


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
