
from . import Config


class Store:
    ''' The :class:`Store` implements a key/value store, effectively a Python
        dictionary with some additional context. A store has a unique *name*
        within the local POT context; which daemons will be contacted to handle
        further requests is determined by the per-Key configuration.
    '''

    def __init__(self, name):

        config = Config.get(name)
        self.config = config
        self._keys = dict()


    def __setitem__(self, name, value):
        raise NotImplementedError("you cannot set a Store's key directly")


    def __getitem__(self, name):
        key = self._keys[name]

        if key is None:
            config = self.config[name]
            key = Key.Key(self, config)
            self._keys[name] = key

        return key


    def __iter__(self):
        return Iterator(self)


    def __repr__(self):
        return repr(self._keys)


    def __len__(self):
        return len(self._keys)


    def __delitem__(self, name):
        raise NotImplementedError("you cannot delete a Store's key directly")


    def clear(self):
        raise NotImplementedError("you cannot delete a Store's keys directly")


    def copy(self):
        raise NotImplementedError('a Store is intended to be a singleton')


    def has_key(self, name):
        return name in self._keys


    def update(self, *args, **kwargs):
        raise NotImplementedError("you cannot update a Store's keys directly")


    def keys(self):
        return self._keys.keys()


    def values(self):
        return self._keys.values()


# end of class Store



class Iterator:
    ''' Internal class for iteration over a :class:`Store` instance. The custom
        iterator allows easier just-in-time instantiation of any missing Key
        instances.
    '''

    def __init__(self, store):
        self.store = store
        self.keys = store.keys()
        self.keys.reverse()


    def __next__(self):

        key = None

        while key is None:
            try:
                name = self.keys.pop()
            except IndexError:
                raise StopIteration

            try:
                key = self.store[name]
            except KeyError:
                key = None

        return key

    next = __next__


# end of class Iterator


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
