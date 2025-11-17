import mktl
import pytest
import time

def test_get(run_markbrokered, run_marked):

    integer = mktl.get('unittest.INTEGER')
    integer.get()


def test_set(run_markbrokered, run_marked):

    integer = mktl.get('unittest.INTEGER')
    integer.set(-1)
    integer.set(23)
    integer.set(44)

    assert integer.get() == 44
    assert integer.value == 44
    assert integer == 44

    string = mktl.get('unittest.STRING')

    string.set('testing')
    assert string.get() == 'testing'
    assert string.value == 'testing'
    assert string == 'testing'

    string.set('')


def test_logic(run_markbrokered, run_marked):

    string = mktl.get('unittest.STRING')

    string.set('testing')
    assert bool(string) == True

    string.set('')
    assert bool(string) == False


    integer = mktl.get('unittest.INTEGER')

    integer.value = 0
    assert bool(integer) == False
    assert integer | 0 == 0
    assert integer | 1 == 1
    assert integer & 0 == 0
    assert integer & 1 == 0

    integer.value = 1
    assert bool(integer) == True

    integer.value = 2
    assert bool(integer) == True
    assert integer | 0 == 2
    assert integer | 1 == 3
    assert integer & 0 == 0
    assert integer & 1 == 0
    assert integer & 2 == 2
    assert integer ^ 2 == 0
    assert integer ^ 1 == 3

    assert 0 | integer == 2
    assert 1 | integer == 3
    assert 0 & integer == 0
    assert 1 & integer == 0
    assert 2 & integer == 2
    assert 2 ^ integer == 0
    assert 1 ^ integer == 3


def test_math(run_markbrokered, run_marked):

    integer = mktl.get('unittest.INTEGER')

    integer.value = 50

    assert integer == 50
    assert integer <= 50
    assert integer <= 51
    assert integer < 51
    assert integer >= 50
    assert integer >= 49
    assert integer > 49
    assert integer != 49

    assert +integer == 50
    assert -integer == -50
    assert ~integer == ~50
    assert integer + 1 == 51
    assert integer - 1 == 49
    assert integer * 2 == 100
    assert integer / 2 == 25
    assert integer ** 2 == 2500
    assert integer % 25 == 0
    assert integer % 12 == 2

    assert 1 + integer == 51
    assert 1 - integer == -49
    assert 2 * integer == 100
    assert 2 / integer == 0.04
    assert 2 ** integer == 1125899906842624
    assert 100 % integer == 0
    assert 52 % integer == 2

    integer += 1
    assert integer == 51
    integer -= 1
    assert integer == 50
    integer /= 2
    assert integer == 25
    integer *= 2
    assert integer == 50


def test_callback(run_markbrokered, run_marked):

    string = mktl.get('unittest.STRING')

    test_callback.called = False
    test_callback.item = None
    test_callback.value = None
    test_callback.timestamp = None

    def callback(item, value, timestamp):
        test_callback.called = True
        test_callback.item = item
        test_callback.value = value
        test_callback.timestamp = timestamp

    string.register(callback)
    before = time.time()
    string.value = 'callback testing'

    assert test_callback.called == True
    assert test_callback.item is string
    assert test_callback.value == 'callback testing'
    assert test_callback.timestamp != None
    assert test_callback.timestamp > before


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
