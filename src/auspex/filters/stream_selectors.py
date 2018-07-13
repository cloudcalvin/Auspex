# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

__all__ = ['AlazarStreamSelector', 'X6StreamSelector']

from auspex.log import logger
from auspex.instruments import *
from auspex.parameter import Parameter, IntParameter
from .filter import Filter
from auspex.stream import DataStreamDescriptor, DataAxis, InputConnector, OutputConnector

import numpy as np

class AlazarStreamSelector(Filter):
    """Digital demodulation and filtering to select a particular frequency multiplexed channel"""

    sink    = InputConnector()
    source  = OutputConnector()
    channel = IntParameter(value_range=(1,2), snap=1)

    # def __init__(self, name=""):
    #     super(AlazarStreamSelector, self).__init__(name=name)
        # self.channel.value = 1 # Either 1 or 2
        # self.quince_parameters = [self.channel]

    def get_channel(self, channel_proxy):
        """Create and return a channel object corresponding to this stream selector"""
        return AlazarChannel(channel_proxy)

    def get_descriptor(self, channel_proxy):
        """Get the axis descriptor corresponding to this stream selector. For the Alazar cards this
        is always just a time axis."""
        samp_time = 1.0/channel_proxy.dig.sampling_rate
        descrip = DataStreamDescriptor()
        descrip.add_axis(DataAxis("time", samp_time*np.arange(channel_proxy.digitizer.nbr_samples)))
        return descrip


class X6StreamSelector(Filter):
    """Digital demodulation and filtering to select a particular frequency multiplexed channel"""

    sink   = InputConnector()
    source = OutputConnector()
    
    channel     = IntParameter(value_range=(1,3), snap=1)
    dsp_channel = IntParameter(value_range=(0,4), snap=1)
    stream_type = Parameter(allowed_values=["Raw", "Demodulated", "Integrated"], default='Demodulated')

    # def __init__(self, name=""):
    #     super(X6StreamSelector, self).__init__(name=name)
        # self.stream_type.value = "Raw" # One of Raw, Demodulated, Integrated
        # self.quince_parameters = [self.channel, self.dsp_channel, self.stream_type]

    def get_channel(self, channel_proxy):
        """Create and return a channel object corresponding to this stream selector"""
        return X6Channel(channel_proxy)

    def get_descriptor(self, channel_proxy):
        """Get the axis descriptor corresponding to this stream selector. If it's an integrated stream, 
        then the time axis has already been eliminated. Otherswise, add the time axis."""
        descrip = DataStreamDescriptor()
        if channel_proxy.stream_type == 'Raw':
            samp_time = 4.0e-9
            descrip.add_axis(DataAxis("time", samp_time*np.arange(channel_proxy.digitizer.record_length//4)))
            descrip.dtype = np.float64
        elif channel_proxy.stream_type == 'Demodulated':
            samp_time = 32.0e-9
            descrip.add_axis(DataAxis("time", samp_time*np.arange(channel_proxy.digitizer.record_length//32)))
            descrip.dtype = np.complex128
        else: # Integrated
            descrip.dtype = np.complex128
        return descrip

