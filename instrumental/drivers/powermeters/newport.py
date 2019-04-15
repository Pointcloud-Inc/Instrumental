# -*- coding: utf-8 -*-
# Copyright 2014-2019 Chris Rogers, Nate Bogdanowicz
"""
Driver module for Newport power meters. Supports:

* 1830-C

For example, suppose a power meter is connected on port COM1.
One can then connect and measure the power using the following sequence::

    >>> from instrumental import instrument
    >>> newport_power_meter = instrument(visa_address='COM1',
                                         classname='Newport_1830_C',
                                         module='powermeters.newport')
    >>> newport_power_meter.power
    <Quantity(3.003776, 'W')>

"""
from . import PowerMeter
from .. import Facet, MessageFacet, VisaMixin, deprecated
from ..util import visa_timeout_context
from ... import Q_
import time
from pyvisa import errors

def _check_visa_support(visa_inst):
    with visa_timeout_context(visa_inst, 100):
        try:
            if int(visa_inst.query('Z?')) in (0, 1):
                return 'Newport_1830_C'
        except:
            pass
    return None


def MyFacet(msg, readonly=False, **kwds):
    """Like SCPI_Facet, but without a space before the set-value"""
    get_msg = msg + '?'
    set_msg = None if readonly else (msg + '{}')
    return MessageFacet(get_msg, set_msg, convert=int, **kwds)


class Newport_1830_C(PowerMeter, VisaMixin):
    """A Newport 1830-C power meter"""
    _INST_PRIORITY_ = 8  # IDN isn't supported
    _INST_PARAMS_ = ['visa_address']

    # Status byte codes
    _PARAM_ERROR = 1
    _COMMAND_ERROR = 2
    _SATURATED = 4
    _OUT_OF_RANGE = 8
    _MSG_AVAILABLE = 16
    _BUSY = 32
    _SERVICE_REQUEST = 64
    _READY_READING = 128

    # Filter averaging constants
    SLOW_FILTER = 1
    MEDIUM_FILTER = 2
    NO_FILTER = 3

    def _initialize(self):
        self._rsrc.read_termination = '\n'
        self._rsrc.write_termination = '\n'

    def close(self):
        self.local_lockout = False

    status_byte = MyFacet('Q', readonly=True)

    @deprecated('status_byte')
    def get_status_byte(self):
        """Query the status byte register and return it as an int"""
        return self.status_byte

    @Facet(units='W', cached=False)
    def power(self):
        """Get the current power measurement

        Returns
        -------
        power : Quantity
            Power in units of watts, regardless of the power meter's current
            'units' setting.
        """
        original_units = self.query('U?')
        if original_units != '1':
            self.write('U1')  # Measure in watts
            power = float(self.query('D?'))
            self.write('U' + original_units)
        else:
            power = float(self.query('D?'))

        return Q_(power, 'watts')

    @deprecated('power')
    def get_power(self):
        return self.power

    range = MyFacet('R', doc="The current input range, [1-8], where 1 is lowest signal.")

    def enable_auto_range(self):
        """Enable auto-range"""
        self.set_range(0)

    def disable_auto_range(self):
        """Disable auto-range

        Leaves the signal range at its current position.
        """
        cur_range = self.get_range()
        self.set_range(cur_range)

    @deprecated('range')
    def set_range(self, range_num):
        """Set the range for power measurements

        range_num = 0 for auto-range
        range_num = 1 to 8 for manual signal range
        (1 is lowest, and 8 is highest)

        Parameters
        ----------
        n : int
            Sets the signal range for the input signal.
        """
        self.range = range_num

    @deprecated('range')
    def get_range(self):
        """Return the current range setting as an int

        1 corresponds to the lowest range, while 8 is the highest range (least
        amplifier gain).

        Note that this does not query the status of auto-range.

        Returns
        -------
        range : int
            the current range setting. Possible values are from 1-8.
        """
        return self.range

    wavelength = MyFacet('W', units='nm')

    @deprecated('wavelength')
    def set_wavelength(self, wavelength):
        """Set the input signal wavelength setting

        Parameters
        ----------
        wavelength : Quantity
            wavelength of the input signal, in units of [length]
        """
        self.wavelength = wavelength

    @deprecated('wavelength')
    def get_wavelength(self):
        """Get the input wavelength setting"""
        return self.wavelength

    attenuator = MyFacet('A', value={False:0, True:1}, doc="Whether the attenuator is enabled")

    @deprecated('attenuator')
    def enable_attenuator(self, enabled=True):
        """Enable the power meter attenuator"""
        self.write('A{}', int(enabled))

    @deprecated('attenuator')
    def disable_attenuator(self):
        """Disable the power meter attenuator"""
        self.enable_attenuator(False)

    @deprecated('attenuator')
    def attenuator_enabled(self):
        """Whether the attenuator is enabled

        Returns
        -------
        enabled : bool
            whether the attenuator is enabled
        """
        val = self.write('A?')
        return bool(val)

    def set_slow_filter(self):
        """Set the averaging filter to slow mode

        The slow filter uses a 16-measurement running average.
        """
        self.write('F1')

    def set_medium_filter(self):
        """Set the averaging filter to medium mode

        The medium filter uses a 4-measurement running average.
        """
        self.write('F2')

    def set_no_filter(self):
        """Set the averaging filter to fast mode, i.e. no averaging"""
        self.write('F3')

    def get_filter(self):
        """Get the current setting for the averaging filter

        Returns
        -------
        SLOW_FILTER, MEDIUM_FILTER, NO_FILTER
            the current averaging filter
        """
        val = self.query("F?")
        return int(val)

    def enable_hold(self, enable=True):
        """Enable hold mode"""
        self.write('G{}', int(not enable))

    def disable_hold(self):
        """Disable hold mode"""
        self.enable_hold(False)

    def hold_enabled(self):
        """Whether hold mode is enabled

        Returns
        -------
        enabled : bool
            True if in hold mode, False if in run mode
        """
        val = int(self.query('G?'))
        return (val == 0)

    def is_measurement_valid(self):
        """Whether the current measurement is valid

        The measurement is considered invalid if the power meter is saturated,
        over-range or busy.
        """
        reg = self.get_status_byte()
        is_saturated = bool(reg & self._SATURATED)
        is_over_range = bool(reg & self._OUT_OF_RANGE)
        is_busy = bool(reg & self._BUSY)

        return not (is_saturated or is_over_range or is_busy)

    def store_reference(self):
        """Store the current power input as a reference

        Sets the current power measurement as the reference power for future dB
        or relative measurements.
        """
        self.write('S')

    def enable_zero(self, enable=True):
        """Enable the zero function

        When enabled, the next power reading is stored as a background value
        and is subtracted off of all subsequent power readings.
        """
        self.write("Z{}", int(enable))

    def disable_zero(self):
        """Disable the zero function"""
        self.enable_zero(False)

    def zero_enabled(self):
        """Whether the zero function is enabled"""
        val = int(self.query('Z?'))  # Need to cast to int first
        return bool(val)

    def set_units(self, units):
        """Set the units for displaying power measurements

        The different unit modes are watts, dB, dBm, and REL. Each displays
        the power in a different way.

        'watts' displays absolute power in watts

        'dBm' displays power in dBm (i.e. dBm = 10 * log(P / 1mW))

        'dB' displays power in dB relative to the current reference power (i.e.
        dB = 10 * log(P / Pref). At power-up, the reference power is set to
        1mW.

        'REL' displays power relative to the current reference power (i.e.
        REL = P / Pref)

        The current reference power can be set using `store_reference()`.

        Parameters
        ----------
        units : 'watts', 'dBm', 'dB', or 'REL'
            Case-insensitive str indicating which units mode to enter.
        """
        units = units.lower()
        valid_units = {'watts': 1, 'dbm': 2, 'db': 3, 'rel': 4}

        if units not in valid_units:
            raise Exception("`units` must be one of 'watts', 'dbm', 'db', or 'rel")

        self.write('U{}', valid_units[units])

    def get_units(self):
        """Get the units used for displaying power measurements

        Returns
        -------
        units : str
            'watts', 'db', 'dbm', or 'rel'
        """
        val = int(self.query('U?'))
        units = {1: 'watts', 2: 'db', 3: 'dbm', 4: 'rel'}
        return units[val]

    @property
    def local_lockout(self):
        """Whether local-lockout is enabled"""
        return bool(self.query('L?'))

    @local_lockout.setter
    def local_lockout(self, enable):
        self.write("L{}", int(enable))

class Newport_2936_R(PowerMeter, VisaMixin):
    """A Newport 2936-R power meter"""
    timeout = 10e-3

    def _initialize(self):
        self.flush_read()

        self.set_channel(1)
        self.set_units('watts')
        self.set_channel(2)
        self.set_units('watts')

    def write(self, message):
        time.sleep(self.timeout)
        return self._rsrc.write(message + '\n')
        
    def read(self):
        while True:
            try:
                time.sleep(self.timeout)
                return self._rsrc.read_bytes(1).decode("utf-8").strip("\r\n")
            except errors.VisaIOError:
                pass

    def flush_read(self):
        try:
            while True:
                time.sleep(self.timeout)
                self._rsrc.read_bytes(1)
        except errors.VisaIOError:
            pass
            
    def query(self, message):
        self.write(message)
        return self.read()

    def set_channel(self, channel):
        return self.write('pm:channel %d' % channel)

    def set_units(self, units, channel=1):
        """ Set units for power measurements.
        
        Parameters
        ----------
        units : str
            'amps', 'volts', 'watts', 'watts_cm2', 'joules', 'joules_cm2','dbm'
        """

        valid_units = {
            'amps': 0,
            'volts': 1,
            'watts': 2,
            'watts_cm2': 3,
            'joules': 4, 
            'joules_cm2': 5, 
            'dbm': 6
            }

        self.set_channel(channel)
        return self.write('pm:units %d' % valid_units[units.lower()])

    def set_analogfilter(self, mode, channel=1):
        """ Set analog filter mode.

        Parameters
        ----------
        mode : str
            'None', '250khz', '12.5khz', '1khz', '5hz'
        """
        valid_modes = {
            'None': 0,
            '250khz': 1,
            '12.5khz': 2, 
            '1khz': 3,
            '5hz': 4
        }

        self.set_channel(channel)
        return self.write('pm:analogfilter %d' % valid_modes[mode.lower()])
 
    def set_digitalfilter(self, num, channel=1):
        """ Set digital filter mode.

        Parameters
        ----------
        num : int
            Integer between 0 and 10,000
        """
        assert num >= 0 and num <= 10000
        self.set_channel(channel)
        return self.write('pm:digitalfilter %d' % num)
    
    def set_autoranging(self, auto, channel=1):
        """ Turns auto-ranging on / off.

        Parameters
        ----------
        auto : bool
        """
        valid_auto = {
            True: 1,
            False: 0
        }
        self.set_channel(channel)
        return self.write('pm:auto %d' % valid_auto[auto])
    
    def set_range(self, value, channel=1):
        """ Set power range.

        Parameters
        ----------
        value : int
            Integer between 0 and 7
        """
        assert value >= 0 and value <= 7
        self.set_channel(channel)
        return self.write('pm:range %d' % value)

    def get_power(self, channel=1):
        self.set_channel(channel)
        return float(self.query("pm:power?"))
     
