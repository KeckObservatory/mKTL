import mktl
import pytest
import unitdaemon

# Daemons invoked throughout this file use different store names in
# order to avoid overlap with other unit test fixtures.


def test_empty(run_mkregistryd):
    mktl.Daemon('unittest_daemon_empty', 'unittest', override=True)


def test_subclass(run_mkregistryd):

    class Daemon(mktl.Daemon):

        def describe_items(self):
            items = dict()
            items['something'] = dict()
            items['something']['description'] = 'A test item'
            return items

    Daemon('unittest_daemon_subclass', 'unittest', override=True)


def test_subclass_handlers(run_mkregistryd):

    def get_a_number():
        get_a_number.custom_value += 1
        return get_a_number.custom_value

    get_a_number.custom_value = 5

    def set_a_number(new_value):
        get_a_number.custom_value = new_value * 2


    class Daemon(mktl.Daemon):

        def describe_items(self):
            items = dict()
            items['a_number'] = dict()
            items['a_number']['description'] = 'A test item'
            items['a_number']['type'] = 'numeric'
            items['a_number']['initial'] = -2
            return items


        def setup(self):
            a_number = self.store['a_number']

            # Test the generic entry point; while the specific entry
            # points (like self.add_get_performer()) can be called
            # directly, the generic entry point makes the same calls
            # after parsing the request.

            self.add_performer('a_number', 'get', get_a_number)
            self.add_performer('a_number', 'set', set_a_number)

            with pytest.raises(ValueError):
                self.add_performer('a_number', 'bad_reqest', get_a_number)

            with pytest.raises(KeyError):
                self.add_get_performer('invalid_key', get_a_number)

            with pytest.raises(KeyError):
                self.add_set_performer('invalid_key', set_a_number)



    Daemon('unittest_daemon_subclass_handlers', 'unittest', override=True)


    a_number = mktl.get('unittest_daemon_subclass_handlers', 'a_number')

    # The initial value is -2.

    assert a_number < 0
    assert a_number == -2

    # A GET request for the cached value should yield no change.

    a_number.get()
    assert a_number == -2

    # A GET+refresh request should make it a positive integer, because
    # the performer method gets invoked. The performer method then increments
    # its starting value, which is five. So we should wind up with six as the
    # refreshed value.

    a_number.get(refresh=True)
    assert a_number > 0
    assert a_number == 6

    # Ask again and it should increment again.

    a_number.get(refresh=True)
    assert a_number == 7

    # A SET request should multiply the new value by two before setting it
    # internally. But we only set it internally, the published value won't
    # recognize the multiplication. Not until we ask for a refresh.

    a_number.set(a_number + 1)
    assert a_number == 8

    a_number.get(refresh=True)
    assert a_number == 17

    # Doing an in-place modification bypasses the set handler completely,
    # and just publishes the new value, because the Item we are manipulating
    # here is the authoritative Item.

    a_number += 1
    assert a_number == 18


def test_subclass_item(run_mkregistryd):

    class Something(mktl.Item):
        pass

    class Daemon(mktl.Daemon):

        def describe_items(self):
            items = dict()
            items['something'] = dict()
            items['something']['description'] = 'A test item'
            return items

        def setup(self):
            self.add_item(Something, 'something')

    Daemon('unittest_daemon_subclass_item', 'unittest', override=True)


def test_subclass_item_interactions(run_mkregistryd):

    class Something(mktl.Item):

        def perform_get(self):
            return self.value + 1

    class Payloader(mktl.Item):

        def perform_get(self):
            payload = mktl.protocol.message.Payload(value=self.value)
            return payload

    class Daemon(mktl.Daemon):

        def describe_items(self):
            items = dict()

            items['payloader'] = dict()
            items['payloader']['description'] = 'A test item'
            items['payloader']['type'] = 'string'
            items['payloader']['initial'] = 'testing'

            items['something'] = dict()
            items['something']['description'] = 'A test item'
            items['something']['type'] = 'numeric'
            items['something']['initial'] = 0

            return items

        def setup(self):
            self.add_item(Something, 'something')
            self.add_item(Payloader, 'payloader')

    Daemon('unittest_daemon_subclass_item_interact', 'unittest', override=True)

    something = mktl.get('unittest_daemon_subclass_item_interact', 'something')

    something.set(40)
    assert something == 40

    something.get(refresh=True)
    assert something == 41

    something.get(refresh=True)
    assert something == 42

    something.value = 50
    assert something.get() == 50

    something.publish(66)
    assert something.value == 66
    assert something.get() == 66

    payloader = mktl.get('unittest_daemon_subclass_item_interact', 'payloader')

    assert payloader.value == 'testing'
    payloader.value = 'testing elsewise'
    assert payloader.value == 'testing elsewise'
    assert payloader.get() == 'testing elsewise'



# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
