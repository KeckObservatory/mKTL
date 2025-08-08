import mktl


def test_store(run_markguided, run_markd):

    unittest = mktl.get('unittest')

    integer = unittest['integer']
    string = unittest['string']

    integer2 = unittest['INTEGER']
    string2 = unittest['STRING']

    assert integer is integer2
    assert string is string2


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
