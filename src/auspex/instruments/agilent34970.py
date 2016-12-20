# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

from .instrument import SCPIInstrument, StringCommand

# Since the 34970A takes as an argument a list of channels for nearly all useful commands we define many getter and 
# setter methods in terms of properties without the use of metacommand expansion
# We define only the commands enabling 2 and 4 wire resistance measurements both with and without the internal DMM
# Support for other measurement capabilites will be added as needed 

class Agilent34970A(SCPIInstrument):
	"""Agilent 34970A MUX"""

# Allowed value arrays
	ONOFF_VALUES	= ['ON','OFF']
	TRIGSOUR_VALUES = ['BUS','IMM','EXT','TIM']
	ADVSOUR_VALUES  = ['EXT','BUS','IMM']

# Commands needed to configure MUX for measurement with an external instrument
	dmm            = StringCommnd(scpi_string="INST:DMM",value_map={'ON': '1', 'OFF': '0'})
	trigger_source = StringCommand(scpi_string="TRIG:SOUR",allowed_values=TRIGSOUR_VALUES)
	advance_source = StringCommand(scpi_string="ROUT:CHAN:ADV:SOUR",allowed_values=ADVSOUR_VALUES)

# FIXME!!!!!!!!!!!! Convert ch_string to array
	@property
    def scanlist(self):
        ch_string = self.interface.query("ROUT:SCAN?")
        return ch_string
    @scanlist.setter
    def scanlist(self, ch_list):
        self.interface.write(("ROUT:SCAN (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))

    def set_fwire(self, val, ch_list):
    	if val not in ONOFF_VALUES:
    		raise ValueError("Channels configured for 4 wire measurement must be ON or OFF")
    	else:
    		self.interface.write(("ROUT:CHAN:FWIR "+val+",(@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
    	return

    def get_fwire(self, ch_list):
    	ch_string = self.interface.query(("ROUT:CHAN:FWIR? (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
    	return ch_string

# Commands that configure resistance measurements with internal DMM

	def set_resistance_range(self, val, ch_list, opts): 
		if opts=="fw":
			self.interface.write(("SENS:FRES:RANG "+val+",(@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		else: 
			self.interface.write(("SENS:RES:RANG "+val+",(@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		return

	def get_resistance_range(self, ch_list, opts):
		if opts=="fw":
			ch_string = self.interface.query(("SENS:FRES:RANG? (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		else: 
			ch_string = self.interface.query(("SENS:RES:RANG? (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		return ch_string

	def set_resistance_resolution(self, val, ch_list, opts):
		if opts=="fw":
			self.interface.write(("SENS:FRES:NPLC "+val+",(@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		else: 
			self.interface.write(("SENS:RES:NPLC "+val+",(@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		return

	def get_resistance_resolution(self, ch_list, opts):
		if opts=="fw":
			ch_string = self.interface.query(("SENS:FRES:NPLC? (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		else: 
			ch_string = self.interface.query(("SENS:RES:NPLC? (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		return ch_string

	def set_resistance_zcomp(self, val, ch_list, opts):
		if opts=="fw":
			self.interface.write(("SENS:FRES:OCOM "+val+",(@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		else: 
			self.interface.write(("SENS:RES:OCOM "+val+",(@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		return

	def get_resistance_zcomp(self, ch_list, opts):
		if opts=="fw":
			ch_string = self.interface.query(("SENS:FRES:OCOM? (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		else: 
			ch_string = self.interface.query(("SENS:RES:OCOM? (@"+','.join(['{:d}']*len(ch_list))+")").format(ch_list))
		return ch_string


# Generic init and connect methods
    def __init__(self, resource_name, *args, **kwargs):
        super(Agilent34970A, self).__init__(resource_name, *args, **kwargs)
        self.name = "Agilent 34970A MUX"

    def connect(self, resource_name=None, interface_type=None):
        super(Agilent34970A, self).connect(resource_name=resource_name, interface_type=interface_type)
        self.interface._resource.read_termination = u"\n"
