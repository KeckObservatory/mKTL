""" Python implementation of mKTL. This includes client functions, such as
    interacting with key/value stores, and daemon functions, such as publishing
    key/value pairs and handling client requests.
"""

from . import WeakRef

from . import Protocol
from . import Config
from . import Client
from . import Daemon
from . import BackEnd

from . import Get
get = Get.get
home = Config.File.home


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
