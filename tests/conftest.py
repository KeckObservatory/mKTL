import os
import pytest
import subprocess
import sys
import time


@pytest.fixture(scope="session")
def run_mkbrokerd():

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/mkbrokerd')

    pipe = subprocess.PIPE
    mkbrokerd = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    yield

    mkbrokerd.terminate()


@pytest.fixture(scope="session")
def run_mkd():

    os.environ['PYTHONPATH'] = os.getcwd()

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/mkd')
    arguments.append('-m')
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
