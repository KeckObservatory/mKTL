import time
import mktl


class Referenced:
    def a_method(self):
        pass


def test_persistent_object():
    thing = Referenced()

    reference = mktl.weakref.ref(thing)
    assert reference is not None
    assert callable(reference)

    dereferenced = reference()
    assert dereferenced is not None


def test_persistent_object_method():
    """ This is the reason the local weak reference wrapper exists: in the
        standard weak reference module a weak reference to an object method
        becomes immediately invalid. This test will fail if you replace the
        local wrapper with the standard module.
    """

    thing = Referenced()

    reference = mktl.weakref.ref(thing.a_method)
    assert reference is not None
    assert callable(reference)

    dereferenced = reference()
    assert dereferenced is not None
    assert callable(dereferenced)


def test_removed_object():
    thing = Referenced()

    reference = mktl.weakref.ref(thing)
    assert reference is not None
    assert callable(reference)

    del thing

    dereferenced = reference()
    assert dereferenced is None


def test_removed_object_method():
    thing = Referenced()

    reference = mktl.weakref.ref(thing.a_method)
    assert reference is not None
    assert callable(reference)

    del thing

    dereferenced = reference()
    assert dereferenced is None


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
