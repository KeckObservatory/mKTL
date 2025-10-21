import mktl
import time

class Daemon(mktl.Daemon):

    def setup(self):

        self.add_item(Gold, 'GOLD')
        self.add_item(Silver, 'SILVER')
        self.add_item(Platinum, 'PLATINUM')


class MarketPriced(mktl.Item):

    def __init__(self, *args, **kwargs):
        mktl.Item.__init__(self, *args, **kwargs)
        self.poll(86400)    # Update once per day.


class Gold(MarketPriced):

    def req_refresh(self):
        current = get_spot_value('gold', 'usd', 'grams')
        return self.to_payload(current)


class Platinum(MarketPriced):

    def req_refresh(self):
        current = get_spot_value('platinum', 'usd', 'grams')
        return self.to_payload(current)


class Silver(MarketPriced):

    def req_refresh(self):
        current = get_spot_value('silver', 'usd', 'grams')
        return self.to_payload(current)


def get_spot_value(metal, currency, units):

    # Presumably this involves something like a curl/wget call to an
    # external website. Assume that is exactly what would occur in this
    # space, and we retrieved a bare number for the metal, currency,
    # and units of interest.
    #
    # current_price = some magical invocation of external resources
    current_price = 100.4

    current_price = float(current_price)
    return current_price


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
