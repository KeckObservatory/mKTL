import os
import pytest
import subprocess
import sys
import time


@pytest.fixture(scope="session")
def run_markbrokered():

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/markbrokered')

    pipe = subprocess.PIPE
    markbrokered = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    yield

    markbrokered.terminate()


@pytest.fixture(scope="session")
def run_marked():

    os.environ['PYTHONPATH'] = os.getcwd()

    arguments = list()
    arguments.append(sys.executable)
    arguments.append('../sbin/marked')
    arguments.append('-m')
    arguments.append('unitdaemon')
    arguments.append('unittest')
    arguments.append('unittest')    # Yes, twice.

    pipe = subprocess.PIPE
    marked = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    # Apparently it takes a smidge of time for things to come online. Hence
    # this arbitrary sleep before yielding to the test. 0.1 seconds is not
    # enough, 0.2 usually is, one second should be more than enough.

    time.sleep(1)

    yield

    marked.terminate()

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
