
import time

time_s = time.time

def time_us():
    """ Return the current time in microseconds since the Epoch. This
        relies on :func:`time.time` returning a floating point number
        containing fractional seconds.
    """

    # While time.time_ns() does exist, it was added in Python 3.7,
    # and what we really want is microseconds instead of nanoseconds.
    # JSON integers are reliable up to 53 bits, which comfortably
    # accommodates timestamps for the next 200+ years; nanoseconds
    # wouldn't fit.

    timestamp = time.time()
    timestamp_us = timestamp * 1000000
    timestamp_us = round(timestamp_us)

    return timestamp_us


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
