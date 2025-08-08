import os
import pytest
import subprocess
import sys
import time


@pytest.fixture(scope="session")
def run_markguided():

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/markguided')

    pipe = subprocess.PIPE
    markguided = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    yield

    markguided.terminate()


@pytest.fixture(scope="session")
def run_markd():

    os.environ['PYTHONPATH'] = os.getcwd()

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/markd')
    arguments.append('-m')
    arguments.append('UnitStore')
    arguments.append('unittest')
    arguments.append('unittest')    # Yes, twice.

    pipe = subprocess.PIPE
    markd = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    # Apparently it takes a smidge of time for things to come online. Hence
    # this arbitrary sleep before yielding to the test. 0.1 seconds is not
    # enough, 0.2 usually is, one second should be more than enough.

    time.sleep(1)

    yield

    markd.terminate()

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
