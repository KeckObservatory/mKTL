""" This is a super-simple mktl.Daemon to act as a foil for any client-facing
    unit tests. This file is used by the invocation of mkd in the run_mkd()
    fixture defined in conftest.py.
"""

import mktl
import time


class Daemon(mktl.Daemon):

    def __init__(self, store, alias, *args, **kwargs):

        items = generate_config()
        mktl.config.authoritative(store, alias, items)
        mktl.Daemon.__init__(self, store, alias, *args, **kwargs)


# end of class Daemon



def generate_config():

    items = dict()

    items['angle'] = dict()
    items['angle']['description'] = 'An angular numeric item.'
    items['angle']['units'] = 'radians'
    items['angle']['type'] = 'numeric'

    items['number'] = dict()
    items['number']['description'] = 'A numeric item.'
    items['number']['units'] = 'meaningless units'
    items['number']['type'] = 'numeric'

    items['readonly'] = dict()
    items['readonly']['description'] = 'A read-only numeric item.'
    items['readonly']['units'] = 'meaningless units'
    items['readonly']['type'] = 'numeric'
    items['readonly']['initial'] = 13
    items['readonly']['settable'] = False

    items['string'] = dict()
    items['string']['description'] = 'A string item.'
    items['string']['type'] = 'string'

    items['typeless'] = dict()
    items['typeless']['description'] = 'A typeless item.'

    return items


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
