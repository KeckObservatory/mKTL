import os
import pytest
import subprocess
import sys
import time


@pytest.fixture(scope="session")
def run_mkregistryd():
    """ There is no need to run the registry daemon; the unit test daemons
        do not participate in the mKTL discovery process. Though the
        run_mkregistryd fixture is no longer used it is left here in case
        that changes in the future.
    """

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/mkregistryd')

    pipe = subprocess.PIPE
    mkregistryd = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    yield
    mkregistryd.terminate()


@pytest.fixture(scope="session")
def run_mkd():

    os.environ['PYTHONPATH'] = os.getcwd()

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/mkd')
    arguments.append('--no-discovery')
    arguments.append('--module')
    arguments.append('unitdaemon')
    arguments.append('unittest')
    arguments.append('unittest')    # Yes, twice.

    pipe = subprocess.PIPE
    mkd = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    # Apparently it takes a smidge of time for things to come online. Hence
    # this arbitrary sleep before yielding to the test. 0.1 seconds is not
    # enough, 0.2 usually is, one second should be more than enough.

    time.sleep(1)

    yield
    mkd.terminate()


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
