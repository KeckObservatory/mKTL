
import threading
import time

from . import weakref

active = dict()


def period(method):
    """ Return the currently set polling period for the provided *method*.
        Returns None if no polling is presently active for that method.
    """

    method_id = id(method)

    try:
        poller = active[method_id]
    except KeyError:
        return None

    return poller.interval



def start(method, period):
    """ Call the provided *method* on an interval of *period* seconds.
        A dedicated background thread is used for each method; it is possible
        to exhaust the available system resources with a high enough quantity
        of background threads.

        Though there is no lower bound on the polling period, keep in mind
        the limitations of your platform: in 2025, anything less than 0.0001
        seconds (10 kHz) is not going to reliably keep up; tests indicate a
        frequency of 100 kHz falls further behind on every cycle.

        If a background poller is already active for the specified method, the
        poller will be updated to use the newly requested period. This means
        that this mechanism cannot be used to trigger two independent polling
        sequences for the same method.
    """

    if period is None or period == 0:
        stop(method)
        return

    method_id = id(method)

    try:
        poller = active[method_id]
    except KeyError:
        poller = _Poller(method)
        active[method_id] = poller

    poller.period(period)



def stop(method):
    """ Discontinue calling the provided *method*.
    """

    method_id = id(method)

    try:
        poller = active[method_id]
    except KeyError:
        return

    poller.stop()



class _Poller:
    """ Background thread to invoke any polling requests.
    """

    def __init__(self, method):

        self.method_id = id(method)
        active[self.method_id] = self

        self.interval = None
        self.reference = weakref.ref(method)
        self.shutdown = False

        self.alarm = threading.Event()
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def period(self, period):
        """ Update the polling interval to *period* seconds.
        """

        period = float(period)
        self.interval = period
        self.wake()


    def run(self):

        interval = 30
        next = time.time()

        # Initial wait for someone to call self.period().

        while self.interval is None:
            self.alarm.wait(1)

        while True:
            begin = time.time()

            if self.shutdown == True:
                break

            if self.alarm.is_set() == True:
                self.alarm.clear()

                # The interval only changes when the alarm is set, including
                # when it is set upon startup. That's our cue to load a new
                # interval for this loop, and start an entirely new cadence.

                interval = self.interval
                next = begin + interval

            else:
                # Ideally the period is constant-- regardless of when we woke
                # up we want to honor the requested cadence, and set the next
                # wakeup according to the previous value, incremented solely
                # by the interval.

                next += interval

            method = self.reference()

            if method is None:
                # The original object is gone. No further calls are possible.
                break

            method()
            end = time.time()

            delay = next - end
            if delay > 0:
                self.alarm.wait(delay)


        # Infinite loop exited.
        del active[self.method_id]


    def stop(self):
        self.shutdown = True
        self.wake()


    def wake(self):
        self.alarm.set()


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
