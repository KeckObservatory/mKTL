
import weakref


class WeakRef:
    """ A faithful implementation of weak references that works not only for
    	static functions and objects, but also bound methods of instances.
        Patterned after the weakref.WeakMethod subclass available in Python 3.4.
    """

    def __init__(self, thing):

        # If 'thing' is an instance method, it will have both a __func__ and
        # a __self__ attribute. If it does not have those attributes, it is a
        # simple object, to which we can retain a direct weak reference.

        try:
            self.method = weakref.ref(thing.__func__)
            self.instance = weakref.ref(thing.__self__)
        except AttributeError:
            self.reference = weakref.ref(thing)
        else:
            self.reference = None


    def __call__(self):

        if self.reference is not None:
            return self.reference()

        # Otherwise, this WeakRef instance refers to an instance method. If the
        # instance was deallocated there is no longer an instance method to
        # refer to.

        instance = self.instance()

        if instance is None:
            return None

        # The instance has not been deallocated; therefore, it is still valid
        # to refer to the instance method. Return a new reference to the
        # instance method; a strong reference to the instance would have kept
        # the instance from being deallocated, and a weak reference to an
        # instance method is dead on arrival.

        method = self.method()
        return getattr(instance, method.__name__)


# end of class WeakRef

ref = WeakRef

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
