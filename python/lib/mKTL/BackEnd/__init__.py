''' A BackEnd is a Daemon.Store subclass for a specific purpose, such as
    proxying some other protocol, like KTL, or EPICS. In a more perfect
    world these might be broken out into subpackages.
'''

##from . import EPICS
from . import KTL

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
