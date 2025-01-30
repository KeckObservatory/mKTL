''' Implmentation of the top-level :func:`get` method. This is intended to be
    the principal entry point for users interacting with a key/value store.
'''

from . import Store


def get(store, key=None):
    ''' Return a cached :class:`Store` or :class:`Item` instance. If both a
        *store* and a *key* are specified, the requested *key* will be returned
        from the requested *store*. The same will occur if the sole argument is
        a store and key name concatenated with a dot (store.KEY). If only a
        *store* name is provided, a matching :class:`Store` instance will be
        returned.

        If the caller always uses :func:`get` to retrieve a :class:`Store` or
        :class:`Item` they will always receive the same instance of that class.

        The :func:`get` method is intended to be the primary entry point for
        all interactions with a key/value store, acting like a factory method
        without enforcing strict singleton behavior.
    '''

    store = str(store)

    if key is None and '.' in store:
        store, key = store.split('.', 1)

    try:
        store = cache[store]
    except KeyError:
        store = Store.Store(store)

    if key is None:
        return store
    else:
        key = store[key]
        return key


cache = dict()


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
