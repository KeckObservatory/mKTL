""" This daemon connects to a fictional temperature controller. It is
    structured to relay commands and publish available telemetry from
    the controller.

    As a fictional example, this code has not been directly tested, and may
    contain syntax errors, logical errors, and other miscellaneous problems.
"""

import configparser
import mktl


class Daemon(mktl.Daemon):

    def parse_options(self, options):
        """ Read in the configuration file; this daemon can't function without
            some additional guidance on how it is supposed to run. This file
            would define some metadata on how the controller is being used,
            including system-specific names for temperature inputs and
            heater outputs.
        """

        configuration_file = options.appconfig

        parser = configparser.ConfigParser()
        parser.read(configuration_file)

        self.heater_config = parser


    def describe_items(self):
        """ Generate and return the description of all items handled by
            this daemon.
        """

        items = dict()

        controller_number = self.heater_config.get('main', 'controller')
        controller_items = self.describe_controller_items(controller_number)

        items.update(controller_items)

        try:
            inputs = self.heater_config.options('inputs')
        except configparser.NoSectionError:
            inputs = tuple()

        try:
            outputs = self.heater_config.options('outputs')
        except configparser.NoSectionError:
            outputs = tuple()

        for input in inputs:
            prefix = main.config.get('inputs', input)
            items.update(self.describe_input_items(prefix))

        for output in outputs:
            prefix = main.config.get('outputs', output)
            items.update(self.describe_output_items(prefix))

        return items


    def describe_controller_items(self, controller):
        """ Generation of the description of controller-wide items is broken
            out here for readability. The *controller* argument is expected
            to be a number.
        """

        controller = str(controller)
        prefix = 'ctrl' + controller

        items = dict()

        address = prefix + 'address'
        items[address] = dict()
        items[address]['description'] = 'Controller IP address.'
        items[address]['settable'] = False

        aux = prefix + 'aux'
        items[aux] = dict()
        items[aux]['description'] = 'Auxiliary command and response.'

        firmware = prefix + 'firmware'
        items[firmware] = dict()
        items[firmware]['description'] = 'Controller firmware revision.'
        items[firmware]['settable'] = False

        status = prefix + 'status'
        items[status] = dict()
        items[status]['description'] = 'Controller connection status.'
        items[status]['type'] = 'enumerated'
        items[status]['settable'] = False

        return items


    def describe_input_items(self, prefix):
        """ Generation of the description of input-specific items is broken
            out here for readability.
        """

        items = dict()

        chi = prefix + 'chi'
        items[chi] = dict()
        items[chi]['description'] = 'Channel for this temperature input.'
        items[chi]['settable'] = False

        tmp = prefix + 'tmp'
        items[tmp] = dict()
        items[tmp]['description'] = 'Current temperature value.'
        items[tmp]['type'] = 'numeric'
        items[tmp]['units'] = 'deg C'
        items[tmp]['settable'] = False

        return items


    def describe_output_items(self, prefix):
        """ Generation of the description of output-specific items is broken
            out here for readability.
        """

        items = dict()

        cho = prefix + 'cho'
        items[cho] = dict()
        items[cho]['description'] = 'Channel for this heater output.'
        items[cho]['settable'] = False

        out = prefix + 'out'
        items[out] = dict()
        items[out]['description'] = 'Current heater output.'
        items[out]['type'] = 'numeric'
        items[out]['units'] = 'watts'
        items[out]['settable'] = False

        trg = prefix + 'trg'
        items[trg] = dict()
        items[trg]['description'] = 'Heater setpoint/target value.'
        items[trg]['type'] = 'numeric'
        items[trg]['units'] = 'deg C'

        return items


    def setup(self):

        self.add_item(Gold, 'GOLD')
        self.add_item(Silver, 'SILVER')
        self.add_item(Platinum, 'PLATINUM')


class MarketPriced(mktl.Item):

    def __init__(self, *args, **kwargs):
        mktl.Item.__init__(self, *args, **kwargs)
        self.poll(86400)    # Update once per day.


class Gold(MarketPriced):

    def perform_get(self):
        return get_spot_value('gold', 'usd', 'grams')


class Platinum(MarketPriced):

    def perform_get(self):
        return get_spot_value('platinum', 'usd', 'grams')


class Silver(MarketPriced):

    def perform_get(self):
        return get_spot_value('silver', 'usd', 'grams')


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
