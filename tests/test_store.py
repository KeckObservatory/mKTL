import mktl
import pytest


def test_store(run_markguided, run_marked):

    store = mktl.get('unittest')

    assert store.name == 'unittest'

    assert store.has_key('angle')
    assert store.has_key('integer')
    assert store.has_key('string')

    with pytest.raises(NotImplementedError):
        store['angle'] = 55

    with pytest.raises(NotImplementedError):
        store['bad_key_name'] = 346

    with pytest.raises(KeyError):
         store['bad_key_name']

    with pytest.raises(NotImplementedError):
        del store['angle']

    with pytest.raises(NotImplementedError):
        del store['bad_key_name']

    with pytest.raises(NotImplementedError):
        store.clear()

    with pytest.raises(NotImplementedError):
        store.copy()

    with pytest.raises(NotImplementedError):
        store.update()

    integer1 = store['integer']
    string1 = store['string']

    integer2 = store['INTEGER']
    string2 = store['STRING']

    assert integer1 is integer2
    assert string1 is string2

    for item in store:
        assert isinstance(item, mktl.Item)

    for item in store.values():
        assert isinstance(item, mktl.Item)

    for key in store.keys():
        assert isinstance(key, str)

    assert len(store) == len(store.keys())

    for key in store.keys():
        assert key in store.config

    # The actual result from str() and repr() is not enforced, just want to
    # invoke the statement(s) for completeness's sake.

    str(store)
    repr(store)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
