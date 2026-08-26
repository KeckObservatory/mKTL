import mktl
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
