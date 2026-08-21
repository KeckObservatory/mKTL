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


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
