# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

from auspex.instruments.agilent import Agilent34970A
from auspex.instruments.lakeshore import LakeShore335

from auspex.experiment import FloatParameter, IntParameter, Experiment
from auspex.stream import DataStream, DataAxis, DataStreamDescriptor, OutputConnector
from auspex.filters.io import WriteToHDF5

import asyncio
import numpy as np
import time
import datetime
import h5py

# Experimental Topology
# Sweep dummy index (time proxy) 
# Lakeshore Output -> T senses A and B
# MUX Output -> Sheet resistance of 4 channels
# System time Output -> time of measurement

class Cooldown(Experiment):

	# Define Experiment Axis
	index		= IntParameter(default=0,unit="none")
	#chan_num	= IntParameter(default=101,unit="channel")

	# Setup Output Connectors (Measurements)
	sheet_res	= OutputConnector()
	temp_A		= OutputConnector()
	temp_B		= OutputConnector()
	sys_time	= OutputConnector()

	# Constants (instrument parameters ect.)

	# Configure channels 101:104 for 4 wire resistance measurements
	# 100 Ohm range, 10 PLC integration time, 0 Compenstaion ON
	chan_list	= [101,102,103,104]
	res_range	= 100
	plc			= 10
	zcomp		= "ON"

	# Configure Tsense A: Diode,2.5V,Kelvin units
	# Configure Tsense B: NTC RTD,30 Ohm,Compensation ON,Kelvin units
	# This configuration will change with measurement setup
	A_config	= [1,0,0,0,1]
	B_config	= [3,1,0,1,1]

	#Instrument Resources
	mux			= Agilent34970A("GPIB0::10::INSTR")
	lakeshore	= LakeShore335("GPIB0::2::INSTR")

	def init_streams(self):

		# Since Mux sweeps over channels itself, channel number must be added explicitly as a data axis to each measurement
		self.sheet_res.add_axis(DataAxis("channel",chan_list))
		self.temp_A.add_axis(DataAxis("channel",chan_list))
		self.temp_B.add_axis(DataAxis("channel",chan_list))
		self.sys_time.add_axis(DataAxis("channel",chan_list))

	def init_instruments(self):

		self.mux.scanlist = chan_list
		self.mux.set_resistance_chan(chan_list,True)
		self.mux.set_resistance_range(res_range,chan_list,True)
		self.mux.set_resistance_resolution(plc,chan_list,True)
		self.mux.set_resistance_zcomp(zcomp,chan_list,True)

		self.lakeshore.config_sense_A = A_config
		self.lakeshore.config_sense_B = B_config

		self.index.assign_method(int)


	async def run(self):

		self.mux.scan()
		await self.temp_A.push(self.lakeshore.Temp("A"))
		await self.temp_B.push(self.lakeshore.Temp("B"))
		await self.sys_time.push(time.time())

		while self.mux.interface.OPC() == 0:
			await asyncio.sleep(len(chan_list)*plc/60)

		await self.sheet_res.push(self.mux.read())



if __name__ == '__main__':

    exp = Cooldown()

    # 
    sample_name = "TOX_14_15_18_19"
    date        = datetime.datetime.today().strftime('%Y-%m-%d')
    file_path   = "data\Tc\{samp:}\{samp:}-Tc_{date:}.h5".format(samp=sample_name, date=date)

    # Setup datafile and define which data to write, plot ect.
    wr = WriteToHDF5(file_path)
    edges = [(exp.sheet_res, wr),(exp.temp_A, wr),(exp.temp_B,wr),(exp.sys_time,wr)]
    exp.set_graph(edges)

    # Add points 10 at a time until base temp is reached
    def while_temp(sweep_axis):

    	if exp.lakeshore.Temp("B") < 5: 
    		return False

    	sweep_axis.add_points(range(10))

    	return True

    # Defines index as sweep axis where while_temp function determines end condition
    sweep_axis = exp.add_sweep(exp.index, range(1), refine_func=while_temp)

    # Run the experiment
    exp.run_sweeps()


