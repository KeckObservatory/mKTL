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
    items['angle']['type'] = 'numeric'
    items['angle']['format'] = '%2d:%2.2d:%04.1f'
    items['angle']['units'] = {'': 'radians', 'formatted': 'degrees'}

    items['boolean'] = dict()
    items['boolean']['description'] = 'A boolean item without enumerators.'
    items['boolean']['type'] = 'boolean'

    items['enumerated'] = dict()
    items['enumerated']['description'] = 'An enumerated item.'
    items['enumerated']['type'] = 'enumerated'
    items['enumerated']['enumerators'] = {0: 'Zero', 1: 'One', 4: 'Four'}

    items['hourangle'] = dict()
    items['hourangle']['description'] = 'An angular numeric item, in h:m:s.'
    items['hourangle']['type'] = 'numeric'
    items['hourangle']['format'] = '%2d:%2.2d:%04.1f'
    items['hourangle']['units'] = {'': 'radians', 'formatted': 'hours'}

    items['mask'] = dict()
    items['mask']['description'] = 'A mask item.'
    items['mask']['type'] = 'mask'
    items['mask']['enumerators'] = {'None': 'none set', 0: 'A', 1: 'B', 2: 'C'}

    items['noyes'] = dict()
    items['noyes']['description'] = 'A boolean item with enumerators.'
    items['noyes']['type'] = 'boolean'
    items['noyes']['enumerators'] = {0: 'No', 1: 'Yes'}

    items['number'] = dict()
    items['number']['description'] = 'A numeric item.'
    items['number']['type'] = 'numeric'
    items['number']['units'] = 'meaningless units'

    items['readonly'] = dict()
    items['readonly']['description'] = 'A read-only numeric item.'
    items['readonly']['type'] = 'numeric'
    items['readonly']['units'] = 'meaningless units'
    items['readonly']['initial'] = 13
    items['readonly']['settable'] = False

    items['string'] = dict()
    items['string']['description'] = 'A string item.'
    items['string']['type'] = 'string'

    items['typeless'] = dict()
    items['typeless']['description'] = 'A typeless item.'

    return items


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
