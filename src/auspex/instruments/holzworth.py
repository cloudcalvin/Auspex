# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

__all__ = ['HolzworthHS9000']

from .instrument import Instrument, MetaInstrument
import usb
import os
from auspex.log import logger
from auspex import config
from unittest.mock import MagicMock
import ctypes

class HolzworthDevice(object):

    TIMEOUT = 1000

    def __init__(self, device):
        super(HolzworthDevice, self).__init__()

        if not isinstance(device, usb.core.Device):
            raise TypeError("Holzworth device must receive a USB device!")

        self.serial = device.__repr__()

        self._device = device
        self._device.reset()
        if self._device.is_kernel_driver_active(0):
            self._device.detach_kernel_driver(0)
        self._device.set_configuration()

        if "Holzworth" not in usb.util.get_string(self._device, self._device.iManufacturer):
            raise ValueError("Not a Holzworth!")

        self._e_in = self._device[0][(0,0)][0]
        self._e_out = self._device[0][(0,0)][1]

        self.channels = self.query(":ATTACH?").split(":")[1:-1]
        if not self.channels:
            raise ValueError("Holzworth has no channels!")

        self.serial = self.query(":{}:IDN?".format(self.channels[0])).split(',')[-1]

    def __del__(self):
        if self._device is not None:
            usb.util.dispose_resources(self._device)

    def write(self, command):
        try:
            wlen = self._e_out.write(command.encode(), timeout=self.TIMEOUT)
            assert wlen == len(command.encode())
        except usb.core.USBError:
            logger.error("Command {} to Holzworth {} timed out!".format(command, self.serial))

    def read(self, nbytes=64):
        data = None
        try:
            data = self._e_in.read(nbytes, timeout=self.TIMEOUT)
        except usb.core.USBError:
            logger.error("Read from Holzworth {} timed out!".format(self.serial))
        #Strip NULLs from reply and decode
        return bytes(data).partition(b'\0')[0].decode()

    def query(self, command, nbytes=64):
        self.write(command)
        response = self.read(nbytes=nbytes)
        if response == "Invalid Command":
            logger.error("Invalid command {} to Holzworth {}.".format(command, self.serial))
        return response

class HolzworthPythonDriver(object):

    HOLZWORTH_VENDOR_ID = 0x1bb3
    HOLZWORTH_PRODUCT_ID = 0x1001

    def __init__(self):
        super(HolzworthPythonDriver, self).__init__()
        logger.debug("Using Holzworth pure-python driver.")
        self.devices = {}
        for dev in usb.core.find(idVendor = self.HOLZWORTH_VENDOR_ID,
                             idProduct = self.HOLZWORTH_PRODUCT_ID,
                             find_all=True):
            holz = HolzworthDevice(dev)
            logger.debug("Found Holzworth {} with channels {}".format(holz.serial, holz.channels))
            self.devices[holz.serial] = holz

        if not self.devices:
            raise IOError("No Holzworth devices found.")

    def enumerate(self):
        return self.devices.keys()

    def ch_check(self, serial, channel):
        if serial not in self.devices.keys():
            ValueError("Holzworth {} not connected!".format(serial))
        if channel not in self.devices[serial].channels:
            ValueError("Holzworth {} does not have channel {}".format(serial, channel))

#----- ST-15 note:  Defined/indented here as a stand-alone block, this segment
# fires ONCE upon module load (even for simple import reference); as such
# this is what has been spawning the "No Holzworths" warning -- this would
# occur (originally) as the module loaded for MetaClass introspection/validation.
#
if config.auspex_dummy_mode:
    fake_holz = True
    holzworth_driver = MagicMock()
else:
    fake_holz = False

    # ----- ST-15 delta start...
    # Added optional logic to exclude/skip HolzworthPythonDriver load when
    # config.tgtInstrumentClass defined and indicates one of the Holzworth
    # instrument class definitions.
    #
    # 31 Oct Generalized & enhanced previous logic as disjointNameRefz function
    #
    # Where config.tgtInstrumentClass defined, this function looks to see if
    # any of the class name references (compared as lower case) contain
    # the target key string (in this case, Holzworth).  If key is not Found
    # in the class set (or config.tgtInstrumentClass defined is NOT defined),
    # the function returns true and thus the new logic avoids loading the
    # driver...
    #
    bSkipHWDriverLoad = \
        config.disjointNameRefz( "Holzworth",
                                 acceptClassRefz=config.tgtInstrumentClass,
                                 bEchoDetails=config.bEchoInstrumentMetaInit,
                                 szLogLabel="HW driver load")

    # logger.debug( "Pre MSG -- os.name: {%s}", os.name)
    #
    # ----- ST-15 delta stop.

    if os.name == "posix":
        #
        # ----- ST-15 delta start...
        if bSkipHWDriverLoad:
            logger.debug( "HolzworthPythonDriver load skipped << ST-15 Delta.")
        else:
            # ----- ST-15 delta stop.
            # Original block indented to suit bSkipHWDriverLoad use-case:
            try:
                holzworth_driver = HolzworthPythonDriver()
                logger.debug("Using Holzworth pure-python driver.")
            except Exception as e:
                #logger.warning("Could not connect to Holzworths: {}".format(e))
                logger.warning("HolzworthPythonDriver load failed!" \
                    "\n\r   << EEE Exception: %s", e)
                if str(e) == "No backend available":
                    logger.warning("You may not have the libusb backend: please install it!")
                holzworth_driver = MagicMock()
                fake_holz = True
                # Note:  we could react to config.bUseMockOnLoadError Here
                # too allow true failure or optional MagicMock continuation
                # (the original default behavior)
                print( "      -- Continuing process nonetheless with MagicMock holzworth_driver...\n\r")
    else:
        logger.debug("Using Holzworth DLL driver.")

class MakeSettersGetters(MetaInstrument):
    def __init__(self, name, bases, dct):

        # ---- ST-15 additional config.tgtInstrumentClass originally explored
        # here; initally proved irrelevant and excluded
        # (due to static block delta, above)
        # ----- TJR, 26 Oct 2018

        super(MakeSettersGetters, self).__init__(name, bases, dct)

        for k,v in dct.items():
            if isinstance(v, property):
                logger.debug("Adding '%s' command to Holzworth", k)
                setattr(self, 'set_'+k, v.fset)
                setattr(self, 'get_'+k, v.fget)

class HolzworthInstrument(Instrument, metaclass=MakeSettersGetters):
    """Holzworth instrument"""

    def __init__(self, resource_name=None, name="Unlabeled Generic Holzworth Instrument"):
        self.name = name
        self.resource_name = resource_name

        # ---- ST-15 additional config.tgtInstrumentClass originally explored
        # here; initally proved irrelevant and excluded
        # (due to static block delta, above)
        # ----- TJR, 26 Oct 2018

    def get_info(self):
        # read frequency and power ranges
        if fake_holz:
            self.fmin = 10e3
            self.fmax = 20e9
            self.pmin = -80.
            self.pmax = 16.
        else:
            self.fmin = float((self.ch_query(":FREQ:MIN?")).split()[0]) * 1e6 #Hz
            self.fmax = float((self.ch_query(":FREQ:MAX?")).split()[0]) * 1e6 #Hz
            self.pmin = float((self.ch_query(":PWR:MIN?")).split()[0]) #dBm
            self.pmax = float((self.ch_query(":PWR:MAX?")).split()[0]) #dBm

    @property
    def frequency(self):
        v = self.ch_query(":FREQ?")
        return float(v.split()[0]) * 1e6
    @frequency.setter
    def frequency(self, value):
        if self.fmin <= value <= self.fmax:
            # WARNING!!! The Holzworth might blow up if you ask for >12 digits of precision here
            self.ch_query(":FREQ:{:.12g} Hz".format(value))
        else:
            err_msg = "The value {} GHz is outside of the allowable range {}-{} GHz specified for instrument '{}'.".format(value*1e-9, self.fmin*1e-9, self.fmax*1e-9, self.name)
            raise ValueError(err_msg)

    @property
    def power(self):
        v = self.ch_query(":PWR?")
        return float(v.split()[0])
    @power.setter
    def power(self, value):
        if self.pmin <= value <= self.pmax:
            self.ch_query(":PWR:{} dBm".format(value))
        else:
            err_msg = "The value {} dBm is outside of the allowable range {}-{} dBm specified for instrument '{}'.".format(value, self.pmin, self.pmax, self.name)
            raise ValueError(err_msg)

    @property
    def phase(self):
        v = self.ch_query(":PHASE?")
        return float(v.split()[0])
    @phase.setter
    def phase(self, value):
        self.ch_query(":PHASE:{} deg".format(value % 360))

    @property
    def output(self):
        v = self.ch_query(":PWR:RF?")
        if v == 'ON':
            return True
        else:
            return False
    @output.setter
    def output(self, value):
        if value:
            self.ch_query(":PWR:RF:ON")
        else:
            self.ch_query(":PWR:RF:OFF")

    @property
    def reference(self):
        v = self.ref_query(":STATUS?")
        return v
    @reference.setter
    def reference(self, value):
        ref_opts = ["INT", "10MHz", "100MHz"]
        if value in ref_opts:
            if value == "INT":
                self.ref_query(":INT:100MHz")
            else:
                self.ref_query(":EXT:{}".format(value))
        else:
            raise ValueError("Reference must be one of {}.".format(ref_opts))

class HolzworthHS9000Py(HolzworthInstrument, metaclass=MakeSettersGetters):
    """Holzworth HS9000 microwave source"""
    instrument_type = "Microwave Source"

    def __init__(self, resource_name=None, name="Unlabeled Holzworth HS9000"):
        super(HolzworthHS9000Py, self).__init__(resource_name=resource_name, name=name)

    @classmethod
    def enumerate(cls):
        return holzworth_driver.enumerate()

    def connect(self, resource_name=None):
        if resource_name is not None:
            self.resource_name = resource_name
        # parse resource_name: expecting something like "HS9004A-009-1"
        model, serial, self.chan = self.resource_name.split("-")
        self.serial = model + '-' + serial
        if int(self.chan) not in (1,2,3,4):
            raise ValueError("Holzworth {} has unknown channel {}.".format(self.serial, self.chan))
        holzworth_driver.ch_check(self.serial, self.chan)
        self.get_info()

    def ref_query(self, scpi_string):
        serial = self.serial
        return holzworth_driver.devices[self.serial].query(":REF{}".format(scpi_string))

    def ch_query(self, scpi_string):
        chan_string = ":CH{}".format(self.chan)
        scpi_string = chan_string + scpi_string
        return holzworth_driver.devices[self.serial].query(scpi_string)

class HolzworthHS9000DLL(HolzworthInstrument, metaclass=MakeSettersGetters):
    """Holzworth HS9000 microwave source"""
    instrument_type = "Microwave Source"

    def __init__(self, resource_name=None, name="Unlabeled Holzworth HS9000"):
        super(HolzworthHS9000DLL, self).__init__(resource_name=resource_name, name=name)
        try:
            self._lib = ctypes.CDLL("HolzworthMulti.dll")
            self.fake_holz = False
        except:
            logger.warning("Could not find the Holzworth driver.")
            self._lib = MagicMock()
            self.fake_holz = True

        self._lib.usbCommWrite.restype = ctypes.c_char_p
        self._lib.openDevice.restype = ctypes.c_int

    @classmethod
    def enumerate(cls):
        try:
            lib = ctypes.CDLL("HolzworthMulti.dll")
        except:
            logger.error("Could not find the Holzworth driver.")
            return
        lib.getAttachedDevices.restype = ctypes.c_char_p
        devices = lib.getAttachedDevices()
        return devices.decode('ascii').split(',')

    def connect(self, resource_name=None):
        if resource_name is not None:
            self.resource_name = resource_name
        # parse resource_name: expecting something like "HS9004A-009-1"
        model, serial, self.chan = self.resource_name.split("-")
        self.serial = model + '-' + serial
        success = self._lib.openDevice(self.serial.encode('ascii'))
        if success != 0:
            logger.debug("Could not open Holzworth at address: {}, might already be open on another channel.".format(self.serial))
        # read frequency and power ranges
        self.get_info()

    def ref_query(self, scpi_string):
        serial = self.serial + '-R'
        return self._lib.usbCommWrite(serial.encode('ascii'), scpi_string.encode('ascii')).decode('ascii')

    def ch_query(self, scpi_string):
        chan_string = ":CH{}".format(self.chan)
        scpi_string = chan_string + scpi_string
        return self._lib.usbCommWrite(self.resource_name.encode('ascii'), scpi_string.encode('ascii')).decode('ascii')

#create class based on OS...
class HolzworthHS9000(Instrument):
    def __new__(cls, *args, **kwargs):
        if os.name == "posix":
            obj = object.__new__(HolzworthHS9000Py, *args, **kwargs)
            obj.__init__(*args, **kwargs)
            return obj
        else:
            obj = object.__new__(HolzworthHS9000DLL, *args, **kwargs)
            obj.__init__(*args, **kwargs)
            return obj
