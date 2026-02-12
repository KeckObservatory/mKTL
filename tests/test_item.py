import mktl
import pytest
import time

try:
    import pint
except ImportError:
    pint = None


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


def test_boolean(run_mkbrokerd, run_mkd):

    boolean = mktl.get('unittest.boolean')

    boolean.value = False
    assert boolean == 0
    assert boolean == False

    boolean.value = True
    assert boolean == 1
    assert boolean == True

    boolean.value = 0
    assert boolean == 0
    assert boolean == False

    boolean.value = 1
    assert boolean == 1
    assert boolean == True

    boolean.formatted = 'fALSE'
    boolean.formatted = 'False'
    assert boolean == 0
    assert boolean == False

    boolean.formatted = 'tRUE'
    boolean.formatted = 'True'
    assert boolean == 1
    assert boolean == True

    with pytest.raises(KeyError):
        boolean.formatted = 'No'

    with pytest.raises(KeyError):
        boolean.formatted = 'Yes'

    noyes = mktl.get('unittest.noyes')

    with pytest.raises(KeyError):
        noyes.formatted = 'False'

    with pytest.raises(KeyError):
        noyes.formatted = 'True'

    noyes.formatted = 'nO'
    noyes.formatted = 'No'
    assert noyes == 0
    assert noyes == False

    noyes.formatted = 'yES'
    noyes.formatted = 'Yes'
    assert noyes == 1
    assert noyes == True


def test_enumerated(run_mkbrokerd, run_mkd):

    enumerated = mktl.get('unittest.enumerated')

    enumerated.value = 0
    assert enumerated == 0
    assert enumerated.formatted == 'Zero'

    enumerated.value = 1
    assert enumerated == 1
    assert enumerated.formatted == 'One'

    enumerated.formatted = 'zERO'
    assert enumerated == 0

    enumerated.formatted = 'oNE'
    assert enumerated == 1

    with pytest.raises(KeyError):
        enumerated.formatted = 'invalid'

    with pytest.raises(RuntimeError):
        enumerated.value = 234

    with pytest.raises(RuntimeError):
        enumerated.value = 'invalid'


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


def test_mask(run_mkbrokerd, run_mkd):

    mask = mktl.get('unittest.mask')

    mask.value = 0
    assert mask == 0
    assert mask.formatted == 'none set'

    mask.value = 1
    assert mask == 1
    assert mask.formatted == 'A'

    mask.formatted = 'B'
    assert mask == 2

    mask.formatted = 'c'
    assert mask == 4

    mask.value = 3
    assert mask.formatted == 'A, B'

    mask.formatted = 'B, C'
    assert mask == 6

    with pytest.raises(KeyError):
        mask.formatted = 'invalid'

    with pytest.raises(RuntimeError):
        mask.value = 234

    with pytest.raises(RuntimeError):
        mask.value = 'invalid'


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


def test_quantity(run_mkbrokerd, run_mkd):

    if pint is None:
        return


def test_sexagesimal(run_mkbrokerd, run_mkd):

    if pint is None:
        return

    # The regular 'angle' is D:M:S.

    angle = mktl.get('unittest.angle')

    angle.formatted = '1:2:3'
    assert angle.formatted == ' 1:02:03.0'

    angle *= 2
    assert angle.formatted == ' 2:04:06.0'

    angle *= 2
    assert angle.formatted == ' 4:08:12.0'

    angle *= 10
    assert angle.formatted == '41:22:00.0'

    angle *= 10
    assert angle.formatted == '413:40:00.0'
    assert angle.value == 7.21984533908321

    angle.formatted = '-1:2:3'
    assert angle.formatted == '-1:02:03.0'

    angle.formatted = '1:-2:3'
    assert angle.formatted == ' 0:58:03.0'

    angle.formatted = '1:-2:-3'
    assert angle.formatted == ' 0:57:57.0'

    angle.formatted = '1:2:-3'
    assert angle.formatted == ' 1:01:57.0'

    # The 'hourangle' item is H:M:S.

    hourangle = mktl.get('unittest.hourangle')

    hourangle.formatted = '1:2:3'
    assert hourangle.formatted == ' 1:02:03.0'

    hourangle *= 2
    assert hourangle.formatted == ' 2:04:06.0'

    hourangle *= 2
    assert hourangle.formatted == ' 4:08:12.0'

    hourangle *= 10
    assert hourangle.formatted == '41:22:00.0'

    hourangle *= 10
    assert hourangle.formatted == '413:40:00.0'
    assert hourangle.value == 108.29768008624816


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


def test_typeless(run_mkbrokerd, run_mkd):

    typeless = mktl.get('unittest.typeless')

    typeless.value = 24
    typeless.formatted
    typeless.value = True
    typeless.formatted
    typeless.value = 'test'
    typeless.formatted
    typeless.value = {1: 'one', 2: 'two'}
    typeless.formatted
    typeless.value = (1, 2, 3)
    typeless.formatted
    typeless.value = None
    typeless.formatted


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
