''' Python implementation of POT. This includes client functions, such as
    interacting with key/value stores, and daemon functions, such as publishing
    key/value pairs and handling client requests.
'''

from . import WeakRef

from . import Protocol
from . import Proxy

from . import Get
get = Get.get

### Not sure whether Item needs to be exposed at the top level. Useful for
### debugging at the moment.

from .Item import Item

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
