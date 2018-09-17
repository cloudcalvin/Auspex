# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

__all__ = ['X6Channel', 'X6']

import time
import socket
import struct
import datetime
import numpy as np
import os
import queue
import sys

from auspex.log import logger
import auspex.config as config
from .instrument import Instrument, DigitizerChannel
from unittest.mock import MagicMock

from multiprocessing import Value

# win32 doesn't support MSG_WAITALL, so on windows we
# need to do things a slower, less efficient way.
# (we could optimize this, if performance becomes a problem)
#
if sys.platform == 'win32':
    def sock_recvall(s, data_len):
        buf = bytearray()
        while data_len > 0:
            new = s.recv(data_len)
            data_len -= len(new)
            buf.extend(new)
        return bytes(buf)
else:
    def sock_recvall(s, data_len):
        return s.recv(data_len, socket.MSG_WAITALL)

# Dirty trick to avoid loading libraries when scraping
# This code using quince.
if config.auspex_dummy_mode:
    fake_x6 = True
else:
    try:
        import libx6
        fake_x6 = False
    except:
        logger.info("using fake x6")
        fake_x6 = True

class X6Channel(DigitizerChannel):
    """Channel for an X6"""

    def __init__(self, receiver_channel=None):
        self.stream_type       = "Raw"
        self.if_freq           = 0.0
        self.kernel            = None
        self.kernel_bias       = 0.0
        self.threshold         = 0.0
        self.threshold_invert  = False

        self.phys_channel   = 1
        self.dsp_channel    = 0
        self.channel_tuple  = (1,0,0)

        self.dtype = np.float64
        self.ideal_data = None

        if receiver_channel:
            self.set_by_receiver(receiver_channel)

    def set_by_receiver(self, receiver):
        for name in ["stream_type", "kernel_bias", "threshold", "threshold_invert"]:
            if hasattr(receiver, name) and getattr(receiver, name):
                setattr(self, name, getattr(receiver, name))
        if hasattr(receiver, "channel") and receiver.channel:
            self.phys_channel = receiver.channel
        if hasattr(receiver, 'ideal_data') and receiver.ideal_data:
            self.ideal_data = np.load(os.path.abspath(receiver.ideal_data+'.npy'))
        if hasattr(receiver, "kernel") and receiver.kernel:
            if os.path.exists(os.path.join(config.KernelDir, receiver.kernel+'.txt')):
                self.kernel = np.loadtxt(os.path.join(config.KernelDir, receiver.kernel+'.txt'), dtype=complex, converters={0: lambda s: complex(s.decode().replace('+-', '-'))})
            else:
                try:
                    self.kernel = eval(receiver.kernel)
                except:
                    raise ValueError('Kernel invalid. Provide a file name or an expression to evaluate')
        if self.stream_type == "Integrated":
            self.demod_channel = 0
            self.result_channel = self.dsp_channel
            self.dtype = np.complex128
        elif self.stream_type == "Demodulated":
            self.demod_channel = self.dsp_channel
            self.result_channel = 0
            self.dtype = np.complex128
        else: #Raw
            self.demod_channel  = 0
            self.result_channel = 0
            self.dtype = np.float64

        self.channel_tuple = (int(self.phys_channel), int(self.demod_channel), int(self.result_channel))

class X6(Instrument):
    """BBN QDSP running on the II-X6 digitizer"""
    instrument_type = ("Digitizer")

    def __init__(self, resource_name=None, name="Unlabeled X6", gen_fake_data=True):
        # X6Channel objects
        self._channels = []
        # socket r/w pairs for each channel
        self._chan_to_rsocket = {}
        self._chan_to_wsocket = {}

        self.resource_name = resource_name
        self.name          = name

        self.last_timestamp = Value('d', datetime.datetime.now().timestamp())
        self.gen_fake_data = gen_fake_data
        self.ideal_data = None

        self.timeout = 10.0

        if fake_x6:
            self._lib = MagicMock()
        else:
            self._lib = libx6.X6()

    def __str__(self):
        return "<X6({}/{})>".format(self.name, self.resource_name)

    def __del__(self):
        self.disconnect()

    def connect(self, resource_name=None):
        if resource_name is not None:
            self.resource_name = resource_name

        # pass thru functions
        self.acquire    = self._lib.acquire
        self.stop       = self._lib.stop
        # self.disconnect = self._lib.disconnect

        if self.gen_fake_data or fake_x6:
            self._lib = MagicMock()
            logger.warning("Could not load x6 library")
            logger.warning("X6 GENERATING FAKE DATA")
        self._lib.connect(int(self.resource_name))

    def disconnect(self):
        for sock in self._chan_to_rsocket.values():
            sock.close()
        for sock in self._chan_to_wsocket.values():
            sock.close()
        self._chan_to_rsocket.clear()
        self._chan_to_wsocket.clear()
        self._lib.disconnect()

    def configure_with_dict(self, settings_dict):
        # Call the non-channel commands
        # super(X6, self).set_all(settings_dict)
        # Set data for testing
        try:
            if "ideal_data" in settings_dict.keys():
                self.ideal_data = np.load(os.path.abspath(settings_dict["ideal_data"]+'.npy'))
            else:
                self.ideal_data = None
        except:
            logger.warning(f"Could not find ideal data...")
            self.ideal_data = None


        # Take these directly from the proxy obj
        self.number_averages  = self.proxy_obj.number_averages
        self.number_waveforms = self.proxy_obj.number_waveforms
        self.number_segments  = self.proxy_obj.number_segments
        self.record_length    = settings_dict['record_length']

        # perform channel setup
        for chan in self._channels:
            self.channel_setup(chan)
        # pad all kernels to the maximum set length, to ensure that the valid signal is emitted only when all results are ready
        # first find longest kernel
        integrated_channels = [chan for chan in self._channels if chan.stream_type == 'Integrated']
        if integrated_channels:
            max_kernel_length = max([len(chan.kernel) for chan in integrated_channels])
            # pad kernes to the maximum length
            for chan in integrated_channels:
                if len(chan.kernel) < max_kernel_length:
                    np.append(chan.kernel, 1j*np.zeros(max_kernel_length - len(chan.kernel)))
            # then zero disabled channels
            enabled_int_chan_tuples = [chan.channel_tuple for chan in integrated_channels]
            for a in range(1,3):
                for c in range(1,3): # max number of sdp_channels for now
                    if (a, 0, c) not in enabled_int_chan_tuples:
                        self._lib.write_kernel(a, 0, c, 1j*np.zeros(max_kernel_length))

    def channel_setup(self, channel):
        a, b, c = channel.channel_tuple
        self._lib.enable_stream(a, b, c)

        if channel.stream_type == "Raw":
            return
        elif channel.stream_type == "Demodulated":
            self._lib.set_nco_frequency(a, b, channel.if_freq)
        elif channel.stream_type == "Integrated":
            if channel.kernel is None:
                logger.error("Integrated streams must specify a kernel")
                return
            # convert to complex128
            channel.kernel = channel.kernel.astype(complex)
            self._lib.write_kernel(a, b, c, channel.kernel)
            self._lib.set_kernel_bias(a, b, c, channel.kernel_bias)
            self._lib.set_threshold(a, c, channel.threshold)
            self._lib.set_threshold_invert(a, c, channel.threshold_invert)
        else:
            logger.error("Unrecognized stream type %s" % channel.stream_type)

    def data_available(self):
        return self._lib.get_data_available()

    def done(self):
        if self.data_available():
            return False
        if self._lib.get_is_running():
            return False
        return True

    def get_socket(self, channel):
        if channel in self._chan_to_rsocket:
            return self._chan_to_rsocket[channel]

        try:
            rsock, wsock = socket.socketpair()
        except:
            raise Exception("Could not create read/write socket pair")
        self._lib.register_socket(*channel.channel_tuple, wsock)
        self._chan_to_rsocket[channel] = rsock
        self._chan_to_wsocket[channel] = wsock
        return rsock

    def add_channel(self, channel):
        if not isinstance(channel, X6Channel):
            raise TypeError("X6 passed {} rather than an X6Channel object.".format(str(channel)))

        if channel.stream_type not in ['Raw', 'Demodulated', 'Integrated']:
            raise ValueError("Stream type of {} not recognized by X6".format(str(channel.stream_type)))

        # todo: other checking here
        self._channels.append(channel)

    def spew_fake_data(self, counter, ideal_datapoint=0):
        """
        Generate fake data on the stream. For unittest usage.
        ideal_datapoint: mean of the expected signal for stream_type =  "Integrated".

        Returns the total number of fake data points, so that we can
        keep track of how many we expect to receive, when we're doing
        the test with fake data
        """
        total = 0

        for chan, wsock in self._chan_to_wsocket.items():
            if chan.stream_type == "Integrated":
                length = 1
                data = 0.5 + 0.1*(np.random.random(length).astype(chan.dtype) + 1j*np.random.random(length).astype(chan.dtype)) + ideal_datapoint
            elif chan.stream_type == "Demodulated":
                length = int(self._lib.record_length/32)
                data = np.zeros(length, dtype=chan.dtype)
                data[int(length/4):int(3*length/4)] = 1.0 if ideal_datapoint == 0 else ideal_datapoint
                data += 0.1*(np.random.random(length) + 1j*np.random.random(length))
            else: #Raw
                length = int(self._lib.record_length/4)
                signal = np.sin(np.linspace(0,10.0*np.pi,int(length/2)))
                data = np.zeros(length, dtype=chan.dtype)
                data[int(length/4):int(length/4)+len(signal)] = signal * (1.0 if ideal_datapoint == 0 else ideal_datapoint)
                data += 0.1*np.random.random(length)
            total += length
            wsock.send(struct.pack('n', length*data.dtype.itemsize) + data.tostring())
            counter[chan] += length

        return total

    def receive_data(self, channel, oc, exit):
        sock = self._chan_to_rsocket[channel]
        sock.settimeout(1)
        self.last_timestamp.value = datetime.datetime.now().timestamp()

        total = 0

        while not exit.is_set():
            # push data from a socket into an OutputConnector (oc)
            # wire format is just: [size, buffer...]
            # TODO receive 4 or 8 bytes depending on sizeof(size_t)
            try:
                msg = sock.recv(8)
                self.last_timestamp.value = datetime.datetime.now().timestamp()
            except:
                continue

            # reinterpret as int (size_t)
            msg_size = struct.unpack('n', msg)[0]
            buf = sock_recvall(sock, msg_size)
            if len(buf) != msg_size:
                logger.error("Channel %s socket msg shorter than expected" % channel.channel)
                logger.error("Expected %s bytes, received %s bytes" % (msg_size, len(buf)))
                return
            data = np.frombuffer(buf, dtype=channel.dtype)
            total += len(data)
            oc.push(data)

        # logger.info('RECEIVED %d %d', total, oc.points_taken.value)
        # TODO: this is suspeicious
        for stream in oc.output_streams:
            abc = 0
            while True:
                try:
                    dat = stream.queue.get(False)
                    abc += 1
                    time.sleep(0.005)
                except queue.Empty as e:
                    # logger.info(f"All my data {oc} has been consumed {abc}")
                    break
        # logger.info("X6 receive data exiting")

    def get_buffer_for_channel(self, channel):
        return self._lib.transfer_stream(*channel.channel)

    def wait_for_acquisition(self, timeout=15, ocs=None):

        if self.gen_fake_data:
            total_spewed = 0

            counter = {chan: 0 for chan in self._chan_to_wsocket.keys()}
            # logger.info(f"X6 getting {self._lib.nbr_round_robins} {self._lib.nbr_segments} {self._lib.record_length}")
            for j in range(self._lib.nbr_round_robins):
                for i in range(self._lib.nbr_segments):
                    if self.ideal_data is not None:
                        #add ideal data for testing
                        if hasattr(self, 'exp_step'):
                            total_spewed += self.spew_fake_data(
                                    counter, self.ideal_data[self.exp_step][i])
                        else:
                            total_spewed += self.spew_fake_data(
                                    counter, self.ideal_data[i])
                    else:
                        total_spewed += self.spew_fake_data(counter)

                    time.sleep(0.0001)

            # logger.info("Counter: %s", str(counter))
            # logger.info('TOTAL fake data generated %d', total_spewed)
            if ocs:
                while True:
                    total_taken = 0
                    for oc in ocs:
                        total_taken += oc.points_taken.value
                        # logger.info('TOTAL fake data received %d', oc.points_taken.value)
                    if total_taken == total_spewed:
                        break

                    # logger.info('WAITING for acquisition to finish %d < %d', total_taken, total_spewed)
                    time.sleep(0.025)

        else:
            while not self.done():
                if (datetime.datetime.now().timestamp() - self.last_timestamp.value) > timeout:
                    logger.error("Digitizer %s timed out.", self.name)
                    break
                time.sleep(0.1)

    # pass thru properties
    @property
    def reference(self):
        return self._lib.reference
    @reference.setter
    def reference(self, value):
        self._lib.reference = value

    @property
    def acquire_mode(self):
        return self._lib.acquire_mode
    @acquire_mode.setter
    def acquire_mode(self, value):
        self._lib.acquire_mode = value

    @property
    def record_length(self):
        return self._lib.record_length
    @record_length.setter
    def record_length(self, value):
        self._lib.record_length = value

    @property
    def number_waveforms(self):
        return self._lib.nbr_waveforms
    @number_waveforms.setter
    def number_waveforms(self, value):
        self._lib.nbr_waveforms = value

    @property
    def number_segments(self):
        return self._lib.nbr_segments
    @number_segments.setter
    def number_segments(self, value):
        self._lib.nbr_segments = value

    @property
    def number_averages(self):
        return self._lib.nbr_round_robins
    @number_averages.setter
    def number_averages(self, value):
        self._lib.nbr_round_robins = value
