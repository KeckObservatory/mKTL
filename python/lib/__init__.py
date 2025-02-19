''' Python implementation of mKTL. This includes client functions, such as
    interacting with key/value stores, and daemon functions, such as publishing
    key/value pairs and handling client requests.
'''

from . import WeakRef

from . import Protocol
from . import Proxy
from . import Config
from . import Client

from . import Get
get = Get.get


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
