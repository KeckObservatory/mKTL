""" This is a super-simple mktl.Daemon to act as a foil for any client-facing
    unit tests. This file is used by the invocation of markd in the run_markd()
    fixture defined in conftest.py.
"""

import mktl
import time


class Daemon(mktl.Daemon):

    def __init__(self, *args, **kwargs):

        items = generate_config()
        mktl.config.save('unittest', items, 'unittest')
        mktl.Daemon.__init__(self, *args, **kwargs)


# end of class Daemon



def generate_config():

    items = dict()

    items['INTEGER'] = dict()
    items['INTEGER']['description'] = 'A dummy keyword, ostensibly numeric.'
    items['INTEGER']['units'] = 'meaningless units'
    items['INTEGER']['type'] = 'numeric'

    items['STRING'] = dict()
    items['STRING']['description'] = 'A dummy keyword, ostensibly a string.'
    items['STRING']['type'] = 'string'

    items['ANGLE'] = dict()
    items['ANGLE']['description'] = 'A dummy keyword, ostensibly an angle.'
    items['ANGLE']['units'] = 'radians'
    items['ANGLE']['type'] = 'numeric'

    return items


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
