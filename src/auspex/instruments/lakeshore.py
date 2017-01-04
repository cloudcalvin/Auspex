# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

from .instrument import SCPIInstrument, StringCommand, FloatCommand, IntCommand
import numpy as np

class LakeShore335(SCPIInstrument):
    """LakeShore 335 Temperature Controller"""

# Allowed value arrays

    T_VALS   		= ['A', 'B']
    SENTYPE_VALS 	= [0, 1, 2, 3, 4]
    ZO_VALS			= [0, 1]
    R_VALS			= [0, 1, 2, 3, 4, 5, 6, 7, 8]
    UNIT_VALS		= [1, 2, 3]

    HTR_VALS 		= SENTYPE_VALS.append(5)


# Generic init and connect methods

    def __init__(self, resource_name=None, *args, **kwargs):
        super(LakeShore335, self).__init__(resource_name, *args, **kwargs)
        self.name = "LakeShore 335 Temperature Controller"

    def connect(self, resource_name=None, interface_type=None):
        if resource_name is not None:
            self.resource_name = resource_name
        super(LakeShore335, self).connect(resource_name=self.resource_name, interface_type=interface_type)
        self.interface._resource.read_termination = u"\n"

# Sensor config checker
	def check_sense_msg(self, vals):
		if len(vals) != 5: 
			raise Exception("Invalid number of parameters. Must specify: Sensor Type, Auto Range Option, Range, Compensation Option, Units")
		if vals[0] is not in self.SENTYPE_VALS: 
    		raise Exception("Invalid sensor type:\n0 = Disabled\n1 = Diode\n2 = Platinum RTD\n 3 = NTC RTD\n 4 = Thermocouple")
    	if vals[1] is not in self.ZO_VALS:
    		raise Exception("Invalid autoranging option:\n0 = OFF\n1 = ON")
    	if vals[2] is not in self.R_VALS: 
    		raise Exception("Invalid range specificed. See Lake Shore 335 Manual")
    	if vals[3] is not in self.ZO_VALS:
    		raise Exception("Invalid compenstation option:\n0 = OFF\n1 = ON")
    	if vals[4] is not in self.UNIT_VALS:
    		raise Exception("Invalid units specified:\n1 = Kelvin\n2 = Celsius\n3 = Sensor (Ohms or Volts)")

	def check_htr_msg(self, vals):
		if len(vals) != 3: 
			raise Exception("Invalid number of parameters. Must specify: Control Mode, Input, Powerup Enable")
		if vals[0] is not in self.HTR_VALS
			raise Exception("Invalid Control mode:\n0 = OFF\n1 = PID Loop\n2 = Zone\n3 = Open Loop\n4 = Monitor Out\n5 = Warmup Supply")
		if vals[1] is not in self.ZO_VALS.append(2)
			raise Exception("Invalid Control input:\n0 = None\n1 = A\n2 = B")
		if vals[2] is not in self.ZO_VALS
			raise Exception("Invalid Powerup Enable mode:\n0 = OFF\n1 = ON")

# Read Temperature

    def Temp(self,sense='A'):
        if sense is not in self.T_VALUES: 
        	raise Exception("Must read sensor A or B")
        else: 
        	return self.interface.query(("KRDG? {}").format(sense))

# Configure T senses

    @property
    def  config_sense_A(self):
        return self.interface.query_ascii_values("INTYPE? A",converter=u'd')
       

    @scanlist.setter
    def config_sense_A(self, vals):
    	self.check_sense_msg(vals)
        self.interface.write(("INTYPE A,"+','.join(['{:d}']*len(vals))).format(*vals))

    @property
    def  config_sense_B(self):
        return self.interface.query_ascii_values("INTYPE? B",converter=u'd')
       

    @scanlist.setter
    def config_sense_B(self, vals):
    	self.check_sense_msg(vals)
        self.interface.write(("INTYPE B,"+','.join(['{:d}']*len(vals))).format(*vals))

# Heater and PID Control
	
	@property
    def  control_htr_1(self):
        return self.interface.query_ascii_values("OUTMODE? 1",converter=u'd')
       

    @scanlist.setter
    def control_htr_1(self, vals):
    	self.check_htr_msg(vals)
        self.interface.write(("OUTMODE 1,"+','.join(['{:d}']*len(vals))).format(*vals))

    @property
    def  control_htr_2(self):
        return self.interface.query_ascii_values("OUTMODE? 2",converter=u'd')
       

    @scanlist.setter
    def control_htr_2(self, vals):
    	self.check_htr_msg(vals)
        self.interface.write(("OUTMODE 2,"+','.join(['{:d}']*len(vals))).format(*vals))

    @property
    def  pid_htr_1(self):
        return self.interface.query_ascii_values("PID? 1",converter=u'd')
       

    @scanlist.setter
    def pid_htr_1(self, vals):
    	self.check_htr_msg(vals)
        self.interface.write(("PID 1,"+','.join(['{:d}']*len(vals))).format(*vals))

    @property
    def  pid_htr_2(self):
        return self.interface.query_ascii_values("PID? 2",converter=u'd')
       

    @scanlist.setter
    def pid_htr_2(self, vals):
    	self.check_htr_msg(vals)
        self.interface.write(("PID 2,"+','.join(['{:d}']*len(vals))).format(*vals))


