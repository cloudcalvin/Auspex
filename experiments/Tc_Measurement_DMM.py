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
from auspex.filters.plot import Plotter
from auspex.filters.average import Averager
import asyncio
import numpy as np
import time
import datetime
import h5py

# from auspex.log import logger
# import logging
# logger.setLevel(logging.DEBUG)

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
		self.sheet_res.add_axis(DataAxis("channel",self.chan_list))
		self.temp_A.add_axis(DataAxis("channel",self.chan_list))
		self.temp_B.add_axis(DataAxis("channel",self.chan_list))
		self.sys_time.add_axis(DataAxis("channel",self.chan_list))

	def init_instruments(self):

		print("Initializing Instrument: {}".format(self.mux.interface.IDN()))

		self.mux.scanlist = self.chan_list
		self.mux.set_resistance_chan(self.chan_list,True)
		self.mux.set_resistance_range(self.res_range,self.chan_list,True)
		self.mux.set_resistance_resolution(self.plc,self.chan_list,True)
		self.mux.set_resistance_zcomp(self.zcomp,self.chan_list,True)

		print("Initializing Instrument: {}".format(self.lakeshore.interface.IDN()))

		self.lakeshore.config_sense_A = self.A_config
		self.lakeshore.config_sense_B = self.B_config

		self.index.assign_method(int)


	async def run(self):

		self.mux.scan()

		# Everything needs len(chan_list) copies since sheet_res is read in len(chan_list) at a time. This preserves the dimensionality of the data
		await self.temp_A.push([self.lakeshore.Temp("A")]*len(self.chan_list))
		await self.temp_B.push([self.lakeshore.Temp("B")]*len(self.chan_list))
		await self.sys_time.push([time.time()]*len(self.chan_list))

		while self.mux.interface.OPC() == 0:
			await asyncio.sleep(len(self.chan_list)*self.plc/60)
		await self.sheet_res.push(self.mux.read())

def main():

	exp = Cooldown()

	# Define data file name and path
	sample_name = "TOX_14_15_18_19"
	date        = datetime.datetime.today().strftime('%Y-%m-%d')
	file_path   = "data\Tc\{samp:}\{samp:}-Tc_{date:}.h5".format(samp=sample_name, date=date)

	# Setup datafile and define which data to write, plot ect.
	print("Writing Data to file: {}".format(file_path))
	wr = WriteToHDF5(file_path)

	edges = [(exp.sheet_res, wr.sink),(exp.temp_A, wr.sink),(exp.temp_B, wr.sink),(exp.sys_time, wr.sink)]
	exp.set_graph(edges)

	# Add points 10 at a time until base temp is reached
	async def while_temp(sweep_axis, experiment):

		if experiment.lakeshore.Temp("B") < 5: 
			return False

		print("Running refinement loop: Temp %f, Num_points: %d, last i %d" % (experiment.lakeshore.Temp("B"), sweep_axis.num_points(), sweep_axis.points[-1]))

		last_i = sweep_axis.points[-1]
		sweep_axis.add_points(range(last_i+1,last_i+10))

		return True

	# Defines index as sweep axis where while_temp function determines end condition
	sweep_axis = exp.add_sweep(exp.index, range(2), refine_func=while_temp)

	# Run the experiment
	print("Running Experiment")
	exp.run_sweeps()

if __name__ == '__main__':

	main()




