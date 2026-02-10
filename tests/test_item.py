import mktl
import pytest
import time

def test_get(run_mkbrokerd, run_mkd):

    number = mktl.get('unittest.number')
    number.get()


def test_set(run_mkbrokerd, run_mkd):

    number = mktl.get('unittest.number')
    number.set(-1)
    number.set(23)
    number.set(44)

    assert number.get() == 44
    assert number.value == 44
    assert number == 44

    string = mktl.get('unittest.STRING')

    string.set('testing')
    assert string.get() == 'testing'
    assert string.value == 'testing'
    assert string == 'testing'

    string.set('')

    readonly = mktl.get('unittest.READONLY')

    with pytest.raises(RuntimeError):
        readonly.set(44)


def test_logic(run_mkbrokerd, run_mkd):

    string = mktl.get('unittest.STRING')

    string.set('testing')
    assert bool(string) == True

    string.set('')
    assert bool(string) == False


    number = mktl.get('unittest.number')

    number.value = 0
    assert bool(number) == False
    assert number | 0 == 0
    assert number | 1 == 1
    assert number & 0 == 0
    assert number & 1 == 0

    number.value = 1
    assert bool(number) == True

    number.value = 2
    assert bool(number) == True
    assert number | 0 == 2
    assert number | 1 == 3
    assert number & 0 == 0
    assert number & 1 == 0
    assert number & 2 == 2
    assert number ^ 2 == 0
    assert number ^ 1 == 3

    assert 0 | number == 2
    assert 1 | number == 3
    assert 0 & number == 0
    assert 1 & number == 0
    assert 2 & number == 2
    assert 2 ^ number == 0
    assert 1 ^ number == 3


def test_math(run_mkbrokerd, run_mkd):

    number = mktl.get('unittest.number')

    number.value = 50

    assert number == 50
    assert number <= 50
    assert number <= 51
    assert number < 51
    assert number >= 50
    assert number >= 49
    assert number > 49
    assert number != 49

    assert +number == 50
    assert -number == -50
    assert ~number == ~50
    assert number + 1 == 51
    assert number - 1 == 49
    assert number * 2 == 100
    assert number / 2 == 25
    assert number ** 2 == 2500
    assert number % 25 == 0
    assert number % 12 == 2

    assert 1 + number == 51
    assert 1 - number == -49
    assert 2 * number == 100
    assert 2 / number == 0.04
    assert 2 ** number == 1125899906842624
    assert 100 % number == 0
    assert 52 % number == 2

    assert number + 1 == 51
    assert number - 1 == 49
    assert number * 2 == 100
    assert number / 2 == 25
    assert number ** 2 == 2500
    assert number % 25 == 0
    assert number % 48 == 2

    number += 1
    assert number == 51
    number -= 1
    assert number == 50
    number /= 2
    assert number == 25
    number *= 2
    assert number == 50


def test_callback(run_mkbrokerd, run_mkd):

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
