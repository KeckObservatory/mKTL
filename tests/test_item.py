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

    string = mktl.get('unittest.string')

    string.set('testing')
    assert string.get() == 'testing'
    assert string.value == 'testing'
    assert string == 'testing'

    string.set('')

    readonly = mktl.get('unittest.readonly')

    with pytest.raises(RuntimeError):
        readonly.set(44)


def test_logic(run_mkbrokerd, run_mkd):

    string = mktl.get('unittest.string')

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

    # The ~ operator works on integers and not floating point numbers.

    number.value = 25
    assert ~number == ~25

    number.value = 25.1
    with pytest.raises(TypeError):
        ~number

    # The remainder of the operations are expected to work for both integer
    # and floating point numbers.

    testing = (50, 50.1)
    for test_value in testing:
        number.value = test_value

        assert number == test_value
        assert number <= test_value
        assert number <= test_value + 1
        assert number < test_value + 1
        assert number >= test_value
        assert number >= test_value - 1
        assert number > test_value - 1
        assert number != test_value - 1

        assert +number == test_value
        assert -number == -test_value
        assert number + 1 == test_value + 1
        assert number - 1 == test_value - 1
        assert number * 2 == test_value * 2
        assert number / 2 == test_value / 2
        assert number ** 2 == test_value ** 2
        assert number % 25 == test_value % 25
        assert number % 12 == test_value % 12

        assert 1 + number == 1 + test_value
        assert 1 - number == 1 - test_value
        assert 2 * number == 2 * test_value
        assert 2 / number == 2 / test_value
        assert 2 ** number == 2 ** test_value
        assert 100 % number == 100 % test_value
        assert 52 % number == 52 % test_value

        assert number + 1 == test_value + 1
        assert number - 1 == test_value - 1
        assert number * 2 == test_value * 2
        assert number / 2 == test_value / 2
        assert number ** 2 == test_value ** 2
        assert number % 25 == test_value % 25
        assert number % 48 == test_value % 48

        number += 1
        assert number == test_value + 1
        number -= 1
        assert number == test_value
        number /= 2
        assert number == test_value / 2
        number *= 2
        assert number == test_value


def test_string(run_mkbrokerd, run_mkd):

    string = mktl.get('unittest.string')

    test_value = 'test'
    string.value = test_value

    with pytest.raises(TypeError):
        ~string

    with pytest.raises(TypeError):
        string - 't'

    with pytest.raises(TypeError):
        string - 1

    with pytest.raises(TypeError):
        +string

    with pytest.raises(TypeError):
        -string

    with pytest.raises(ValueError):
        string / 't'

    with pytest.raises(ValueError):
        string / 2

    with pytest.raises(TypeError):
        string ** 2

    with pytest.raises(TypeError):
        string % 2

    assert string == test_value
    assert string <= test_value
    assert string <= test_value + 'z'
    assert string < test_value + 'z'
    assert string >= test_value
    assert string >= 'a' + test_value
    assert string > 'a' + test_value
    assert string != 'a' + test_value

    assert string + 'z' == test_value + 'z'
    assert string * 2 == test_value * 2
    assert 'z' + string == 'z' + test_value
    assert 2 * string == 2 * test_value

    string += 'z'
    assert string == test_value + 'z'
    string.value = test_value
    string *= 2
    assert string == test_value * 2


def test_callback(run_mkbrokerd, run_mkd):

    string = mktl.get('unittest.string')

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
