
import weakref


def ref(thing):
    """ Return a weak reference to the supplied argument, regardless of
        whether it is a simple object or a bound method.
    """

    try:
        thing.__func__
        thing.__self__
    except AttributeError:
        return weakref.ref(thing)
    else:
        return weakref.WeakMethod(thing)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
