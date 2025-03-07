
import atexit
import queue
import time

from . import Poll
from .. import Config
from .. import Protocol


queues = dict()


def load(store, uuid):
    ''' Load any/all cached values for the specified *store* name and *uuid*.
        The values will be returned as a dictionary, with the item key as the
        dictionary key, and the value appropriate for the Item.cached attribute
        as the value.
    '''

    values = dict()

    base_directory = Config.File.directory()
    uuid_directory = os.path.join(base_directory, 'cache', uuid)

    try:
        files = os.listdir(uuid_directory)
    except FileNotFoundError:
        return values

    for key in files:
        if key[:5] == 'bulk:':
            continue

        filename = os.path.join(uuid_directory, key)
        bulk_filename = os.path.join(uuid_directory, 'bulk:' + key)

        json = open(filename, 'r').read()
        value = Protocol.Json.loads(json)

        try:
            bulk = open(bulk_filename, 'r').read()
        except FileNotFoundError:
            bulk = None

        values[key] = (value, bulk)

    return values



def save(item):
    ''' Queue the Item.cached attribute to be written out to disk.
    '''

    uuid = item.store.daemon_uuid

    try:
        pending = queues[uuid]
    except KeyError:
        pending = Pending(uuid)

    ## Does this need to be made more generic, to rely on a method from the
    ## Item class to provide the interpretation-to-bytes? Right now this
    ## code checks for something that acts like a numpy array and handles
    ## it for bulk data, but otherwise will throw whatever's at the .cached
    ## attribute at the JSON translator directly.

    cached = dict()

    try:
        bytes = item.cached.tobytes()
    except AttributeError:
        payload = item.cached
    else:
        payload = dict()
        payload['shape'] = item.cached.shape
        payload['dtype'] = str(item.cached.dtype)

        cached['bulk'] = bytes

    payload = Json.dumps(payload)
    cached[''] = payload

    pending.add(item.key, cached)



def flush():
    ''' Request that any/all background threads with queued :func:`save` calls
        flush their queue out to disk. This call will block until the flush is
        complete.
    '''

    for uuid in queues.keys():
        pending = queues[uuid]
        pending.flush()


atexit.register(flush)



class Pending:
    ''' This is a helper class to accumulate cached values, and periodically
        write them out to disk.
    '''

    def __init__(self, uuid):

        self.uuid = uuid
        queues[uuid] = self

        base_directory = Config.File.directory()
        uuid_directory = os.path.join(base_directory, 'cache', uuid)

        if os.path.exists(uuid_directory):
            if os.access(uuid_directory, os.W_OK) != True:
                raise OSError('cannot write to cache directory: ' + uuid_directory)
        else:
            os.makedirs(uuid_directory, mode=0o775)

        self.directory = uuid_directory
        self.queue = queue.SimpleQueue()
        self.add = self.queue.add

        # Use a background poller to flush events to disk every five seconds.
        Poll.start(self.flush, 5)


    def flush(self):

        pending = dict()

        while True:
            try:
                key, value = self.queue.get(block=False)
            except queue.Empty:
                break

            # Only write out the most recent value. Whatever is last in the
            # queue, that's what we will commit to disk.

            pending[key] = value


        for key in pending.keys():
            value = pending[key]

            for prefix in value.keys():
                if prefix == '':
                    filename = os.path.join(self.directory, key)
                else:
                    filename = os.path.join(self.directory, prefix + ':' + key)

                bytes = value[prefix]
                file = open(filename, 'w')
                file.write(repr(bytes))
                file.close()


# end of class Pending



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
