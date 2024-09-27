
from . import Config
from . import Item


class Store:
    ''' The :class:`Store` implements a key/value store, effectively a Python
        dictionary with some additional context. A store has a unique *name*
        within the local POT context; which daemons will be contacted to handle
        further requests is determined by the per-Item configuration.
    '''

    def __init__(self, name):

        config = Config.get(name)
        self.config = config
        self._items = dict()


    def __setitem__(self, name, value):
        raise NotImplementedError("you cannot set a Store's key directly")


    def __getitem__(self, key):
        item = self._items[key]

        if item is None:
            config = self.config[key]
            item = Item.Item(self, config)
            self._items[key] = item

        return item


    def __iter__(self):
        return Iterator(self)


    def __repr__(self):
        return repr(self._items)


    def __len__(self):
        return len(self._items)


    def __delitem__(self, key):
        raise NotImplementedError("you cannot delete a Store's key directly")


    def clear(self):
        raise NotImplementedError("you cannot delete a Store's keys directly")


    def copy(self):
        raise NotImplementedError('a Store is intended to be a singleton')


    def has_key(self, key):
        return key in self._items


    def update(self, *args, **kwargs):
        raise NotImplementedError("you cannot update a Store's keys directly")


    def keys(self):
        return self._items.keys()


    def values(self):
        return self._items.values()


# end of class Store



class Iterator:
    ''' Internal class for iteration over a :class:`Store` instance. The custom
        iterator allows easier just-in-time instantiation of any missing Item
        instances.
    '''

    def __init__(self, store):
        self.store = store
        self.keys = store.keys()
        self.keys.reverse()


    def __next__(self):

        item = None

        while item is None:
            try:
                key = self.keys.pop()
            except IndexError:
                raise StopIteration

            try:
                item = self.store[key]
            except KeyError:
                item = None

        return item

    next = __next__


# end of class Iterator


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
