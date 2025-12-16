
import threading

from . import config
from .item import Item


class Store:
    """ The :class:`Store` implements a key/value store, effectively a Python
        dictionary with some additional context. A store has a unique *name*
        within the local mKTL context; which daemons will be contacted to handle
        further requests is determined on a per-Item basis, re-use of
        connections is managed in the :mod:`mktl.protocol` submodule, not here.
    """

    def __init__(self, name):

        self.name = name
        self.config = config.get(name)
        self._items = dict()
        self._items_lock = threading.Lock()

        self._update_config()


    def _update_config(self):

        for key in self.config.keys():
            try:
                self._items[key]
            except KeyError:
                self._items[key] = None


    def __setitem__(self, name, value):
        raise NotImplementedError('you cannot assign a key to a Store directly')


    def __getitem__(self, key):
        key = key.lower()

        try:
            item = self._items[key]
        except KeyError:
            error = "'%s' does not contain the key '%s'" % (self.name, key)
            raise KeyError(error)

        if item is None:
            self._items_lock.acquire()

            # Try again in case some other thread created it before this
            # lock-protected attempt.

            item = self._items[key]
            if item is None:
                try:
                    item = Item(self, key)
                except:
                    self._items_lock.release()
                    raise

            self._items_lock.release()

            # The Item assigns itself to our self._items dictionary as an early
            # step in its initialization process, there is no need to manipulate
            # it directly.

        return item


    def __iter__(self):
        return _Iterator(self)


    def __repr__(self):
        return 'store.Store: ' + repr(self._items)


    def __len__(self):
        return len(self._items)


    def __delitem__(self, key):
        raise NotImplementedError("you cannot delete a Store's key directly")


    def clear(self):
        raise NotImplementedError("you cannot delete a Store's keys directly")


    def copy(self):
        raise NotImplementedError('a Store is intended to be a singleton')


    def has_key(self, key):
        key = key.lower()
        return key in self._items


    def update(self, *args, **kwargs):
        raise NotImplementedError("you cannot update a Store's keys directly")


    def keys(self):
        return self._items.keys()


    def values(self):
        return self._items.values()


# end of class Store



class _Iterator:
    """ Internal class for iteration over a :class:`Store` instance. The custom
        iterator allows easier just-in-time instantiation of any missing Item
        instances.
    """

    def __init__(self, store):
        self.store = store
        self.keys = list(store.keys())
        self.keys.reverse()


    def __next__(self):

        try:
            key = self.keys.pop()
        except IndexError:
            raise StopIteration

        item = self.store[key]
        return item

    next = __next__


# end of class _Iterator


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
