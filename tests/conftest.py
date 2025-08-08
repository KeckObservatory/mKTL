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
    arguments.append('unittest')

    pipe = subprocess.PIPE
    markd = subprocess.Popen(arguments, stdout=pipe, stderr=pipe)

    yield

    markd.terminate()

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
