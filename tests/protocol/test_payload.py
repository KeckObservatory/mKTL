import mktl
import time

def test_basics():

    start = time.time()

    for test_value in (44, True, None, 35.5, (1,2,3), {1: 'one'}, 'string'):
        payload = mktl.protocol.message.Payload(test_value)
        assert payload.value is test_value
        assert payload.time > start
        assert payload.bulk == None
        assert payload.dtype == None
        assert payload.error == None
        assert payload.refresh == None
        assert payload.shape == None
        ##assert payload.reply == True



##def test_encapsulate():

##def test_kwargs():

##def test_omission():

##def test_origin()

# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
