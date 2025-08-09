import json
import mktl


def test_normal_server():

    server = mktl.protocol.discover.Server(-999)

    found = mktl.protocol.discover.search()         # For completeness's sake
    found = mktl.protocol.discover.search(wait=True)
    found_test_server = False
    for address,port in found:
        if port == -999:
            found_test_server = True
            break

    assert found_test_server == True

    found = mktl.protocol.discover.search_direct(wait=True)
    found_test_server = False
    for address,port in found:
        if port == -999:
            found_test_server = True
            break

    assert found_test_server == False

    server.cleanup()


def test_direct_server():

    server = mktl.protocol.discover.DirectServer(-998)

    found = mktl.protocol.discover.search_direct()  # For completeness's sake
    found = mktl.protocol.discover.search_direct(wait=True)
    found_test_server = False
    for address,port in found:
        if port == -998:
            found_test_server = True
            break

    assert found_test_server == True

    found = mktl.protocol.discover.search(wait=True)
    found_test_server = False
    for address,port in found:
        if port == -998:
            found_test_server = True
            break

    assert found_test_server == False

    server.cleanup()


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
