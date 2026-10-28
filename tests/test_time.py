import time
import mktl


def test_conversions():

    now = time.time()
    now_us = mktl.time.s_to_us(now)
    now_s = mktl.time.us_to_s(now_us)

    low = now - 0.000001
    high = now + 0.000001

    manual_us = now * 1000000
    manual_us = round(manual_us)
    manual_s = manual_us / 1000000.0
    assert manual_s > low and manual_s < high

    assert now_us == manual_us
    assert now_s > low and now_s < high


def test_microseconds():

    now = time.time()
    now_microseconds = mktl.time.s_to_us(now)

    assert isinstance(now_microseconds, int)
    assert mktl.time.time_us() > now_microseconds


def test_wrappers():

    assert mktl.time.sleep is time.sleep
    assert mktl.time.time is time.time
    assert mktl.time.time_s is time.time


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
