
import threading
import time

from . import weakref

active = dict()


def start(method, period):
    """ Call the provided *method* on an interval of *period* seconds.
        A dedicated background thread is used for each method; it is possible
        to exhaust the available system resources with a high enough quantity
        of background threads.

        If a background poller is already active for the specified method, the
        poller will be updated to use the newly requested period.
    """

    if period is None or period == 0:
        stop(method)
        return

    method_id = id(method)

    try:
        poller = active[method_id]
    except KeyError:
        poller = Poller(method)
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



class Poller:
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
            now = time.time()

            if self.shutdown == True:
                break

            if self.alarm.is_set() == True:
                self.alarm.clear()
                interval = self.interval
                next = now + interval
            else:
                next += interval

            method = self.reference()

            if method is None:
                # The original object is gone. No further calls are possible.
                break

            method()
            now = time.time()

            delay = next - now
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
