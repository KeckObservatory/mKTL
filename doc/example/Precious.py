import mKTL

class Store(mKTL.Daemon):

    def setup(self):

        self.add_item(Gold, 'GOLD')
        self.add_item(Silver, 'SILVER')
        self.add_item(Platinum, 'PLATINUM')


class MarketPriced(mKTL.Item):

    def __init__(self, *args, **kwargs):
        mKTL.Item.__init__(self, *args, **kwargs)
        self.poll(86400)    # Update once per day.


class Gold(MarketPriced)

    def req_refresh(self):
        return get_spot_value('gold', 'usd', 'grams')


class Platinum(MarketPriced)

    def req_refresh(self):
        return get_spot_value('platinum', 'usd', 'grams')


class Silver(MarketPriced)

    def req_refresh(self):
        return get_spot_value('silver', 'usd', 'grams')


def get_spot_value(metal, currency, units):

    # Presumably this involves something like a curl/wget call to an
    # external website. Assume that is exactly what would occur in this
    # space, and we retrieved a bare number for the metal, currency,
    # and units of interest.
    #
    # current_price = some magical invocation of external resources

    current_price = float(current_price)

    payload = dict()
    payload['value'] = current_price
    payload['time'] = time.time()

    return payload


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
