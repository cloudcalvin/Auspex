# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

from .instrument import SCPIInstrument, StringCommand, FloatCommand, IntCommand, is_valid_ipv4
from auspex.log import logger
import socket
import time
import numpy as np

class Agilent34970A(SCPIInstrument):
    """Agilent 34970A MUX"""

# Allowed value arrays
    RES_VALUES      = [1E2, 1E3, 1E4, 1E5, 1E6, 1E7, 1E8]
    PLC_VALUES      = [0.02, 0.2, 1, 10, 20, 100, 200]
    ONOFF_VALUES    = ['ON','OFF']
    TRIGSOUR_VALUES = ['BUS','IMM','EXT','TIM']
    ADVSOUR_VALUES  = ['EXT','BUS','IMM']

# Commands needed to configure MUX for measurement with an external instrument
    dmm            = StringCommnd(scpi_string="INST:DMM",value_map={'ON': '1', 'OFF': '0'})
    trigger_source = StringCommand(scpi_string="TRIG:SOUR",allowed_values=TRIGSOUR_VALUES)
    advance_source = StringCommand(scpi_string="ROUT:CHAN:ADV:SOUR",allowed_values=ADVSOUR_VALUES)

# Generic init and connect methods
    def __init__(self, resource_name=None, *args, **kwargs):
        super(Agilent34970A, self).__init__(resource_name, *args, **kwargs)
        self.name = "Agilent 34970A MUX"

    def connect(self, resource_name=None, interface_type=None):
        if resource_name is not None:
            self.resource_name = resource_name
        super(Agilent34970A, self).connect(resource_name=self.resource_name, interface_type=interface_type)
        self.interface._resource.read_termination = u"\n"

#Channel to String helper function converts int array to channel list string
    def ch_to_str(self, ch_list):
        return ("(@"+','.join(['{:d}']*len(ch_list))+")").format(*ch_list)

    @property
    def scanlist(self):
        ch_string = self.interface.query("ROUT:SCAN?")
        return ch_string
    @scanlist.setter
    def scanlist(self, ch_list):
        self.interface.write("ROUT:SCAN "+self.ch_to_str(ch_list))

# Commands that configure resistance measurements without internal DMM

    def set_fwire(self, val, ch_list):
        if val not in ONOFF_VALUES:
            raise ValueError("Channels configured for 4 wire measurement must be ON or OFF")
        if self.dmm=="ON"
            raise Exception("Cannot issue command when DMM is enabled. Disable DMM")
        else:
            self.interface.write(("ROUT:CHAN:FWIR {:s},"+self.ch_to_str(ch_list)).format(val))

    def get_fwire(self, ch_list):
        if self.dmm=="ON"
            raise Exception("Cannot issue command when DMM is enabled. Disable DMM")
        else:
            return self.interface.query("ROUT:CHAN:FWIR? "+self.ch_to_str(ch_list))

# Commands that configure resistance measurements with internal DMM

    def set_resistance_range(self, val, ch_list, fw=False):
        fw_char = "F" if fw else "" 
        if val not in RES_VALUES:
            raise ValueError(("Resistance range must be {"+'|'.join(['{:E}']*len(RES_VALUES))+"} Ohms").format(*RES_VALUES))
        if self.dmm=="OFF"
            raise Exception("Cannot issue command when DMM is disabled. Enable DMM")
        else: 
            self.interface.write(("SENS:{}RES:RANG {:E},"+self.ch_to_str(ch_list)).format(fw_char,val))       

    def get_resistance_range(self, ch_list, fw=False):
        fw_char = "F" if fw else ""
        if self.dmm=="OFF"
            raise Exception("Cannot issue command when DMM is disabled. Enable DMM")
        else: 
            query_str = ("SENS:{}RES:RANG? "+self.ch_to_str(ch_list)).format(fw_char,ch_list)
            output = self.interface.query_ascii_values(query_str, converter=u'd')   
            return {ch: val for ch, val in zip(ch_list, output) }

    def set_resistance_resolution(self, val, ch_list, fw=False):
        fw_char = "F" if fw else ""
        if val not in PLC_VALUES:
            raise ValueError(("PLC integration times must be {"+'|'.join(['{:E}']*len(PLC_VALUES))+"} cycles").format(*PLC_VALUES))
        if self.dmm=="OFF"
            raise Exception("Cannot issue command when DMM is disabled. Enable DMM") 
        else: 
            self.interface.write(("SENS:{}RES:NPLC {:E},"+self.ch_to_str(ch_list)).format(fw_char,val))       

    def get_resistance_resolution(self, ch_list, fw=False):
        fw_char = "F" if fw else ""
        if self.dmm=="OFF"
            raise Exception("Cannot issue command when DMM is disabled. Enable DMM") 
        else:
            output = self.interface.query_ascii_values(("SENS:{}RES:NPLC? "+self.ch_to_str(ch_list)).format(fw_char)) 
            return {ch: val for ch, val in zip(ch_list, output) }

    def set_resistance_zcomp(self, val, ch_list, fw=False):
        fw_char = "F" if fw else ""
        if val not in ONOFF_VALUES:
            raise ValueError("Zero compensation must be ON or OFF. Only valid for resistance range less than 100 kOhm")
        if self.dmm=="OFF"
            raise Exception("Cannot issue command when DMM is disabled. Enable DMM") 
        else: 
            self.interface.write(("SENS:{}RES:OCOM {:s},"+self.ch_to_str(ch_list)).format(fw_char,val))

    def get_resistance_zcomp(self, ch_list, fw=False):
        fw_char = "F" if fw else ""
        if self.dmm=="OFF"
            raise Exception("Cannot issue command when DMM is disabled. Enable DMM") 
        else: 
            query_str = ("SENS:{}RES:OCOM? "+self.ch_to_str(ch_list)).format(fw_char)
            output = self.interface.query_ascii_values(query_str, converter=u'd')
            return {ch: val for ch, val in zip(ch_list, output) }

class AgilentN5183A(SCPIInstrument):
    """AgilentN5183A microwave source"""

    frequency = FloatCommand(scpi_string=":freq")
    power     = FloatCommand(scpi_string=":power")
    phase     = FloatCommand(scpi_string=":phase")

    alc       = StringCommand(scpi_string=":power:alc", value_map={True: '1', False: '0'})
    mod       = StringCommand(scpi_string=":output:mod", value_map={True: '1', False: '0'})

    output    = StringCommand(scpi_string=":output", value_map={True: '1', False: '0'})

    def __init__(self, resource_name=None, *args, **kwargs):
        #If we only have an IP address then tack on the raw socket port to the VISA resource string
        super(AgilentN5183A, self).__init__(resource_name, *args, **kwargs)

    def connect(self, resource_name=None, interface_type=None):
        if resource_name is not None:
            self.resource_name = resource_name
        if is_valid_ipv4(self.resource_name):
            self.resource_name += "::5025::SOCKET"
        print(self.resource_name)
        super(AgilentN5183A, self).connect(resource_name=resource_name, interface_type=interface_type)
        self.interface._resource.read_termination = u"\n"
        self.interface._resource.write_termination = u"\n"
        self.interface._resource.timeout = 3000 #seem to have trouble timing out on first query sometimes

    def set_all(self, settings):
        settings['frequency'] = settings['frequency']*1e9
        super(AgilentN5183A, self).set_all(settings)

class AgilentE8363C(SCPIInstrument):
    """Agilent E8363C VNA"""

    power              = FloatCommand(scpi_string=":SOURce:POWer:LEVel:IMMediate:AMPLitude", value_range=(-27, 20))
    frequency_center   = FloatCommand(scpi_string=":SENSe:FREQuency:CENTer")
    frequency_span     = FloatCommand(scpi_string=":SENSe:FREQuency:SPAN")
    frequency_start    = FloatCommand(scpi_string=":SENSe:FREQuency:STARt")
    frequency_stop     = FloatCommand(scpi_string=":SENSe:FREQuency:STOP")
    sweep_num_points   = IntCommand(scpi_string=":SENSe:SWEep:POINts")
    averaging_factor   = IntCommand(scpi_string=":SENSe1:AVERage:COUNt")
    averaging_enable   = StringCommand(get_string=":SENSe1:AVERage:STATe?", set_string=":SENSe1:AVERage:STATe {:c}", value_map={False:"0", True:"1"})
    averaging_complete = StringCommand(get_string=":STATus:OPERation:AVERaging1:CONDition?", value_map={False:"+0", True:"+2"})

    def __init__(self, resource_name=None, *args, **kwargs):
        #If we only have an IP address then tack on the raw socket port to the VISA resource string
        super(AgilentE8363C, self).__init__(resource_name, *args, **kwargs)

    def connect(self, resource_name=None, interface_type="VISA"):
        if resource_name is not None:
            self.resource_name = resource_name
        print(self.resource_name)
        if is_valid_ipv4(self.resource_name):
            self.resource_name += "::hpib7,16::INSTR"
        else:
            logger.error("The resource name for the Agilent E8363C: {} is " +
                "not a valid IPv4 address.".format(self.resource_name))
        super(AgilentE8363C, self).connect(resource_name=None,
            interface_type=interface_type)
        self.interface._resource.read_termination = u"\n"
        self.interface._resource.write_termination = u"\n"

    def averaging_restart(self):
        """ Restart trace averaging """
        self.interface.write(":SENSe1:AVERage:CLEar")

    def reaverage(self):
        """ Restart averaging and block until complete """
        self.averaging_restart()
        while not self.averaging_complete:
            #TODO with Python 3.5 turn into coroutine and use await asyncio.sleep()
            time.sleep(0.1)

    def get_trace(self, measurement=None):
        """ Return a tupple of the trace frequencies and corrected complex points """
        #If the measurement is not passed in just take the first one
        if measurement is None:
            traces = self.interface.query(":CALCulate:PARameter:CATalog?")
            #traces come e.g. as  u'"CH1_S11_1,S11,CH1_S21_2,S21"'
            #so split on comma and avoid first quote
            measurement = traces.split(",")[0][1:]
        #Select the measurment
        self.interface.write(":CALCulate:PARameter:SELect '{}'".format(measurement))

        #Take the data as interleaved complex values
        interleaved_vals = self.interface.values(":CALCulate:DATA? SDATA")
        vals = interleaved_vals[::2] + 1j*interleaved_vals[1::2]

        #Get the associated frequencies
        freqs = np.linspace(self.frequency_start, self.frequency_stop, self.sweep_num_points)

        return (freqs, vals)

class AgilentE9010A(SCPIInstrument):
    """Agilent E9010A SA"""

    frequency_center = FloatCommand(scpi_string=":FREQuency:CENTer")
    frequency_span   = FloatCommand(scpi_string=":FREQuency:SPAN")
    frequency_start  = FloatCommand(scpi_string=":FREQuency:STARt")
    frequency_stop   = FloatCommand(scpi_string=":FREQuency:STOP")

    # This seems to return incorrect numbers for large sweeps?
    num_sweep_points = FloatCommand(scpi_string="OBW:SWE:POIN")

    def __init__(self, resource_name, *args, **kwargs):
        #If we only have an IP address then tack on the raw socket port to the VISA resource string
        if is_valid_ipv4(resource_name):
            resource_name += "::5025::SOCKET"
        super(AgilentE9010A, self).__init__(resource_name, *args, **kwargs)

    def connect(self, resource_name=None, interface_type=None):
        super(AgilentE9010A, self).connect(resource_name=resource_name, interface_type=interface_type)
        self.interface._resource.read_termination = u"\n"
        self.interface._resource.write_termination = u"\n"
        self.interface._resource.timeout = 3000 #seem to have trouble timing out on first query sometimes

    def get_axis(self):
        return np.linspace(self.frequency_start, self.frequency_stop, self.num_sweep_points)

    def get_trace(self, num=1):
        self.interface.write(':FORM:DATA REAL,32')
        return self.interface.query_binary_values(":TRACE:DATA? TRACE{:d}".format(num),
            datatype="f", is_big_endian=True)
