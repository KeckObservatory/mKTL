""" This daemon connects to a fictional temperature controller. It is
    structured to relay commands and publish available telemetry from
    the controller.

    As a fictional example, this code has not been directly tested, and may
    contain syntax errors, logical errors, and other miscellaneous problems.
"""

import configparser
import mktl

# This module, which does not exist, implements a simple interface to
# the hardware controller itself.

import heatercontroller


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
            prefix = self.heater_config.get('inputs', input)
            items.update(self.describe_input_items(prefix))

        for output in outputs:
            prefix = self.heater_config.get('outputs', output)
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

        channel = self.heater_config.get(prefix, 'input')
        chi = prefix + 'chi'
        items[chi] = dict()
        items[chi]['description'] = 'Channel for this temperature input.'
        items[chi]['settable'] = False
        items[chi]['initial'] = channel

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

        channel = self.heater_config.get(prefix, 'output')
        cho = prefix + 'cho'
        items[cho] = dict()
        items[cho]['description'] = 'Channel for this heater output.'
        items[cho]['settable'] = False
        items[chi]['initial'] = channel

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

        controller = heatercontroller.Controller(self.heater_config)

        controller_number = self.heater_config.get('main', 'controller')
        self.setup_controller_items(controller_number, controller)

        try:
            inputs = self.heater_config.options('inputs')
        except configparser.NoSectionError:
            inputs = tuple()

        try:
            outputs = self.heater_config.options('outputs')
        except configparser.NoSectionError:
            outputs = tuple()

        for input in inputs:
            prefix = self.heater_config.get('inputs', input)
            self.setup_input_items(prefix, controller)

        for output in outputs:
            prefix = self.heater_config.get('outputs', output)
            self.setup_output_items(prefix, controller)


    def setup_controller_items(self, number, controller):

        number = str(number)
        prefix = 'ctrl' + number

        aux = prefix + 'aux'

        self.add_item(AuxiliaryCommand, aux, controller)


    def setup_input_items(self, prefix, controller):

        tmp = prefix + 'tmp'
        self.add_item(InputTemperature, tmp, controller)


    def setup_output_items(self, prefix, controller):

        out = prefix + 'out'
        self.add_item(OutputPower, out, controller)

        trg = prefix + 'trg'
        self.add_item(OutputSetpoint, trg, controller)


class ControllerItem(mktl.Item):

    def __init__(self, store, key, controller):

        mktl.Item.__init__(self, store, key)
        self.controller = controller

        # The custom item subclasses defined here all manage published values
        # via some mechanism other than the default publish-on-set behavior.

        self.publish_on_set = False


class AuxiliaryCommand(ControllerItem):

    def perform_set(self, value):

        self.value = value
        response = self.controller.command(value)
        self.value = value + ' => ' + response


class InputChannel(ControllerItem):

    def __init__(self, *args, **kwargs):
        ControllerItem.__init__(self, *args, **kwargs)

        channel = self.key[:-3] + 'chi'
        channel = self.store[channel]
        self.channel = channel

        self.poll(0.5)


    def perform_get(self):

        channel = self.channel.value
        command = 'TEMP? ' + channel
        value = self.controller.command(command)

        return value


class OutputPower(ControllerItem):

    def __init__(self, *args, **kwargs):
        ControllerItem.__init__(self, *args, **kwargs)

        channel = self.key[:-3] + 'cho'
        channel = self.store[channel]
        self.channel = channel

        self.poll(0.5)


    def perform_get(self):

        channel = self.channel.value
        command = 'OUT? ' + channel
        value = self.controller.command(command)

        return value


class OutputSetpoint(ControllerItem):

    def __init__(self, *args, **kwargs):
        ControllerItem.__init__(self, *args, **kwargs)

        channel = self.key[:-3] + 'cho'
        channel = self.store[channel]
        self.channel = channel

        # The setpoint is not expected to change absent commands, so the
        # polling rate here is lower than for the temperature and power
        # outputs. But the controller is still considered the authoritative
        # source of the setpoint value.

        self.poll(10)


    def perform_get(self):

        channel = self.channel.value
        command = 'SETP? ' + channel
        value = self.controller.command(command)

        return value


    def perform_set(self, value):

        channel = self.channel.value
        command = 'SETP ' + channel + ' ' + str(value)
        self.controller.command(command)

        # Read the current setpoint back from the controller rather than
        # assume it matches the value commanded.

        self.perform_poll()


# vim: set expandtab tabstop=8 softtabstop=4 shiftwidth=4 autoindent:
