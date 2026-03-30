import mktl
import pytest


def test_store(run_mkbrokerd, run_mkd):

    store = mktl.get('unittest')

    assert store.name == 'unittest'

    assert store.has_key('angle')
    assert store.has_key('Angle')
    assert store.has_key('ANGLE')
    assert store.has_key('number')
    assert store.has_key('string')

    assert 'angle' in store
    assert 'Angle' in store
    assert 'ANGLE' in store
    assert 'number' in store
    assert 'string' in store

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

    number1 = store['number']
    string1 = store['string']

    number2 = store['NUMBER']
    string2 = store['STRING']

    assert number1 is number2
    assert string1 is string2

    assert number1 in store
    number3 = store[number1]
    assert number1 is number3

    for item in store:
        assert isinstance(item, mktl.Item)

    for item in store.values():
        assert isinstance(item, mktl.Item)

    for key in store.keys():
        assert isinstance(key, str)

    assert len(store) == len(store.keys())

    for key in store.keys():
        assert key in store.config

    # The actual result from str() and repr() is not inspected, it's only
    # used for debug purposes.

    str(store)
    repr(store)


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
