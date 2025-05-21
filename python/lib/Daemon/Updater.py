""" This submodule provides a Daemon-specific analog to the regular
    publish/subscribe functionality in the Client, so that callbacks can be
    handled without invoking the full ZMQ machinery to transmit data just to
    trigger a local update.

    The motivation is highlighted most strongly for bulk data transport. In a
    simple test, a daemon was cable of pushing 3200 events per second when
    subscribed to itself for updates, with no callbacks registered; with the
    subscription removed the rate jumped to 4600 events per second. This
    approach splits the difference, with the remaining inefficiency likely due
    to the reconstruction of the numpy array as part of the Client-side
    interpretation of bulk data. Normal, non-bulk transactions still benefit
    from the increase in efficiency, but not to nearly the same degree.
"""

import queue
import threading


class UpdaterWake(RuntimeError):
    pass


class Updater:
    """ Background thread to invoke any callbacks triggered by local updates.
    """

    def __init__(self, method, queue):

        self.method = method
        self.queue = queue
        self.shutdown = False

        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def run(self):

        while True:
            if self.shutdown == True:
                break

            try:
                dequeued = self.queue.get(timeout=300)
            except queue.Empty:
                continue

            if isinstance(dequeued, UpdaterWake):
                continue

            self.method(dequeued)


    def stop(self):
        self.shutdown = True
        self.wake()


    def wake(self):
        self.queue.put(UpdaterWake())


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
