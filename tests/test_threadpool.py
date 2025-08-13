""" Confirm that the concurrent.futures.ThreadPoolExecutor still behaves
    the way we expect it to.
"""

import concurrent.futures
import time


def test_blocking():
    def short_block():
        time.sleep(0.1)

    workers = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    begin = time.time()
    workers.submit(short_block)
    workers.submit(short_block)

    # The third call to submit() should not raise an exception, it is expected
    # to block until a worker is available.

    future = workers.submit(short_block)

    try:
        future.result(timeout=0.1)
    except concurrent.futures.TimeoutError:
        # This exception is expected, the timeout is too short.
        pass
    else:
        raise RuntimeError('expected a timeout from a blocked worker request')

    # This timeout should not be triggered.
    future.result(timeout=0.11)

    end = time.time()

    elapsed = end - begin

    # With a sleep of 0.1 seconds, and two workers available, we expect the
    # first submitted 'tasks' to run concurrently and take 0.1 second of wall
    # clock time; when one of those workers finishes, it should take up the
    # third submitted task; the net elapsed time is expected to be slightly
    # more than 0.2 seconds, but not outrageously so.

    # These checks are redundant with the checks of future.result() above,
    # if those checks passed these two assert statements will likewise be
    # satisfied.

    assert elapsed >= 0.2
    assert elapsed < 0.21


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
