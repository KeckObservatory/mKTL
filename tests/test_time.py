import time
import mktl


def test_microseconds():

    now = time.time()
    now_microseconds = mktl.time.time_us(now)

    assert isinstance(now_microseconds, int)
    assert mktl.time.time_us() > now_microseconds


def test_wrappers():

    assert mktl.time.sleep is time.sleep
    assert mktl.time.time is time.time
    assert mktl.time.time_s is time.time


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
