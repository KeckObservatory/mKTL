""" This is a super-simple mktl.Daemon to act as a foil for any client-facing
    unit tests. This file is used by the invocation of mkd in the run_mkd()
    fixture defined in conftest.py.
"""

import mktl
import time


class Daemon(mktl.Daemon):

    def __init__(self, *args, **kwargs):

        items = generate_config()
        mktl.config.authoritative('unittest', 'unittest', items)
        mktl.Daemon.__init__(self, *args, **kwargs)


# end of class Daemon



def generate_config():

    items = dict()

    items['INTEGER'] = dict()
    items['INTEGER']['description'] = 'A numeric item.'
    items['INTEGER']['units'] = 'meaningless units'
    items['INTEGER']['type'] = 'numeric'

    items['STRING'] = dict()
    items['STRING']['description'] = 'A string item.'
    items['STRING']['type'] = 'string'

    items['ANGLE'] = dict()
    items['ANGLE']['description'] = 'An angular numeric item.'
    items['ANGLE']['units'] = 'radians'
    items['ANGLE']['type'] = 'numeric'

    items['READONLY'] = dict()
    items['READONLY']['description'] = 'A read-only numeric item.'
    items['READONLY']['units'] = 'meaningless units'
    items['READONLY']['type'] = 'numeric'
    items['READONLY']['initial'] = 13
    items['READONLY']['settable'] = False

    return items


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
