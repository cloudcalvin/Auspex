# Copyright 2016 Raytheon BBN Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

import json
import sys
import os
import importlib
import pkgutil
import inspect
import re

import base64
import datetime
import subprocess
import copy

if sys.platform == 'win32' or 'NOFORKING' in os.environ:
    from threading import Thread as Process
    from threading import Event
else:
    from multiprocessing import Process
    from multiprocessing import Event

import numpy as np
import networkx as nx

import auspex.config as config
import auspex.instruments
import auspex.filters
from auspex.stream import DataAxis
import bbndb
from .qubit_exp import QubitExperiment
from auspex.log import logger

def correct_resource_name(resource_name):
    substs = {"USB::": "USB0::", }
    for k, v in substs.items():
        resource_name = resource_name.replace(k, v)
    return resource_name

class QubitExpFactory(object):
    """Create and run Qubit Experiments."""
    def __init__(self):
        self.pipeline      = None
        self.qubit_proxies = {}
        self.meas_graph    = None

        if bbndb.session:
            self.session = bbndb.session
        else:
            raise Exception("Auspex expects db to be loaded already by QGL")

        self.stream_hierarchy = [
            bbndb.auspex.Demodulate,
            bbndb.auspex.Integrate,
            bbndb.auspex.Average,
            bbndb.auspex.OutputProxy
        ]
        self.filter_map = {
            bbndb.auspex.Demodulate: auspex.filters.Channelizer,
            bbndb.auspex.Average: auspex.filters.Averager,
            bbndb.auspex.Integrate: auspex.filters.KernelIntegrator,
            bbndb.auspex.Write: auspex.filters.WriteToHDF5,
            bbndb.auspex.Buffer: auspex.filters.DataBuffer,
            bbndb.auspex.Display: auspex.filters.Plotter
        }
        self.stream_sel_map = {
            'X6-1000M': auspex.filters.X6StreamSelector,
            'AlazarATS9870': auspex.filters.AlazarStreamSelector
        }
        self.instrument_map = {
            'X6-1000M': auspex.instruments.X6,
            'AlazarATS9870': auspex.instruments.AlazarATS9870,
            'APS2': auspex.instruments.APS2,
            'APS': auspex.instruments.APS,
            'HolzworthHS9000': auspex.instruments.HolzworthHS9000,
            'Labbrick': auspex.instruments.Labbrick,
            'AgilentN5183A': auspex.instruments.AgilentN5183A
        }

        # Dirty trick: push the correct entity defs to the calling context
        for var in ["Demodulate","Average","Integrate","Display","Write","Buffer"]:
            inspect.stack()[1][0].f_globals[var] = getattr(bbndb.auspex, var)

        self.ideal_data = {}

    def set_fake_data(self, receiver, ideal_data):
        self.ideal_data[receiver] = ideal_data

    def clear_fake_data(self):
        self.ideal_data = {}

    def create_default_pipeline(self, qubits=None, buffers=False):
        """Look at the QGL channel library and create our pipeline from the current
        qubits."""
        cdb = self.session.query(bbndb.qgl.ChannelDatabase).filter_by(label="working").first()
        if not cdb:
            raise ValueError("Could not find working channel library.")
        
        if not qubits:
            measurements = [c for c in cdb.channels if isinstance(c, bbndb.qgl.Measurement)]
            meas_labels  = [m.label for m in measurements]
            qubits       = [c for c in cdb.channels if "M-"+c.label in meas_labels]
        else:
            meas_labels = ["M-"+q.label for q in qubits]
            measurements = [c for c in cdb.channels if c.label in meas_labels]
        self.qubits = qubits
        self.qubit_proxies = {q.label: bbndb.auspex.QubitProxy(self, q.label) for q in qubits}

        # Build a mapping of qubits to receivers, construct qubit proxies
        receiver_chans_by_qubit = {}
        available_streams_by_qubit = {}
        for m in measurements:
            q = [c for c in cdb.channels if c.label==m.label[2:]][0]
            receiver_chans_by_qubit[q] = m.receiver_chan
            available_streams_by_qubit[q] = m.receiver_chan.receiver.stream_types

        for q, r in receiver_chans_by_qubit.items():
            qp = self.qubit_proxies[q.label]
            qp.available_streams = [st.strip() for st in r.receiver.stream_types.split(",")]
            qp.stream_type = qp.available_streams[-1]

        # generate the pipeline automatically
        self.meas_graph = nx.DiGraph()
        for qp in self.qubit_proxies.values():
            qp.auto_create_pipeline(buffers=buffers)

        for el in self.meas_graph.nodes():
            self.session.add(el)
        self.session.commit()

    def create(self, meta_file, averages=100):
        with open(meta_file, 'r') as FID:
            meta_info = json.load(FID)

        if self.qubit_proxies is {}:
            logger.info("No filter pipeline has been created, loading default")

        # Create our experiment instance
        exp = QubitExperiment()

        # Make database bbndb.auspex.connection
        db_provider      = meta_info['database_info']['db_provider']
        db_resource_name = meta_info['database_info']['db_resource_name']
        library_name     = meta_info['database_info']['library_name']
        library_id       = meta_info['database_info']['library_id']

        # Load the channel library by ID
        exp.channelDatabase = cdb = self.session.query(bbndb.qgl.ChannelDatabase).filter_by(id=library_id).first()
        all_channels        = cdb.channels
        all_generators      = cdb.generators
        all_transmitters    = cdb.transmitters
        all_receivers       = cdb.receivers
        all_transceivers    = cdb.transceivers
        all_qubits          = [c for c in all_channels if isinstance(c, bbndb.qgl.Qubit)]
        all_measurements    = [c for c in all_channels if isinstance(c, bbndb.qgl.Measurement)]

        # Restrict to current qubits, channels, etc. involved in this actual experiment
        # Based on the meta info
        exp.controlled_qubits = controlled_qubits = [c for c in cdb.channels if c.label in meta_info["qubits"]]
        exp.measurements      = measurements      = [c for c in cdb.channels if c.label in meta_info["measurements"]]
        exp.measured_qubits   = measured_qubits   = [c for c in cdb.channels if "M-"+c.label in meta_info["measurements"]]
        exp.phys_chans        = phys_chans        = list(set([e.phys_chan for e in controlled_qubits + measurements]))
        exp.transmitters      = transmitters      = list(set([e.phys_chan.transmitter for e in controlled_qubits + measurements]))
        exp.receiver_chans    = receiver_chans    = list(set([e.receiver_chan for e in measurements]))
        exp.receivers         = receivers         = list(set([e.receiver_chan.receiver for e in measurements]))
        exp.generators        = sources           = list(set([q.phys_chan.generator for q in measured_qubits + controlled_qubits + measurements if q.phys_chan.generator]))

        exp.qubits_by_name    = self.qubits_by_name  = {q.label: q for q in measured_qubits + controlled_qubits}

        # In case we need to access more detailed foundational information
        exp.factory = self

        # If no pipeline is defined, assumed we want to generate it automatically
        if not self.meas_graph:
            raise Exception("No pipeline has been create, do so automatically using exp_factory.create_default_pipeline()")
            #self.create_default_pipeline(measured_qubits)

        # Add the waveform file info to the qubits
        for awg in transmitters:
            awg.sequence_file = meta_info['instruments'][awg.label]

        # Construct the DataAxis from the meta_info
        desc = meta_info["axis_descriptor"]
        data_axis = desc[0] # Data will always be the first axis

        # ovverride data axis with repeated number of segments
        if hasattr(exp, "repeats") and exp.repeats is not None:
            data_axis['points'] = np.tile(data_axis['points'], exp.repeats)

        # Search for calibration axis, i.e., metadata
        axis_names = [d['name'] for d in desc]
        if 'calibration' in axis_names:
            meta_axis = desc[axis_names.index('calibration')]
            # There should be metadata for each cal describing what it is
            if len(desc)>1:
                metadata = ['data']*len(data_axis['points']) + meta_axis['points']
                # Pad the data axis with dummy equidistant x-points for the extra calibration points
                avg_step = (data_axis['points'][-1] - data_axis['points'][0])/(len(data_axis['points'])-1)
                points = np.append(data_axis['points'], data_axis['points'][-1] + (np.arange(len(meta_axis['points']))+1)*avg_step)
            else:
                metadata = meta_axis['points'] # data may consist of calibration points only
                points = np.arange(len(metadata)) # dummy axis for plotting purposes
            # If there's only one segment we can ignore this axis
            if len(points) > 1:
                exp.segment_axis = DataAxis(data_axis['name'], points, unit=data_axis['unit'], metadata=metadata)
        else:
            # No calibration data, just add a segment axis as long as there is more than one segment
            if len(data_axis['points']) > 1:
                exp.segment_axis = DataAxis(data_axis['name'], data_axis['points'], unit=data_axis['unit'])

        # Build a mapping of qubits to receivers, construct qubit proxies
        # We map by the unique database ID since that is much safer
        receiver_chans_by_qubit_label = {}
        for m in measurements:
            q = [c for c in cdb.channels if c.label==m.label[2:]][0]
            receiver_chans_by_qubit_label[q.label] = m.receiver_chan

        # Impose the qubit proxy's stream type on the receiver
        for qubit_label, receiver in receiver_chans_by_qubit_label.items():
            receiver.stream_type = self.qubit_proxies[qubit_label].stream_type

        # Now a pipeline exists, so we create Auspex filters from the proxy filters in the db
        proxy_to_filter      = {}
        connector_by_qp      = {}
        exp.chan_to_dig      = {}
        exp.chan_to_oc       = {}
        exp.qubit_to_dig     = {}
        exp.qubits_by_output = {}

        # Create microwave sources and receiver instruments from the database objects.
        # We configure the receivers later after adding channels.
        exp.instrument_proxies = sources + receivers + transmitters
        exp.instruments = []
        for instrument in exp.instrument_proxies:
            instr = self.instrument_map[instrument.model](instrument.address, instrument.label) # Instantiate
            # For easy lookup
            instr.proxy_obj = instrument
            instrument.instr = instr
            # Add to the experiment's instrument list
            exp._instruments[instrument.label] = instr
            exp.instruments.append(instr)
            # Add to class dictionary for convenience
            if not hasattr(exp, instrument.label):
                setattr(exp, instrument.label, instr)

            # Add fake data if necessary
            if instrument in self.ideal_data.keys():
                instr.ideal_data = self.ideal_data[instrument]

        for mq in measured_qubits:

            # Create the stream selectors
            rcv = receiver_chans_by_qubit_label[mq.label]
            dig = rcv.receiver
            stream_sel = self.stream_sel_map[dig.model](name=rcv.label+'-SS')
            stream_sel.configure_with_proxy(rcv)
            stream_sel.receiver = stream_sel.proxy = rcv

            # Construct the channel from the receiver
            channel = stream_sel.get_channel(rcv)

            # Get the base descriptor from the channel
            descriptor = stream_sel.get_descriptor(rcv)

            # Update the descriptor based on the number of segments
            # The segment axis should already be defined if the sequence
            # is greater than length 1
            if hasattr(exp, "segment_axis"):
                descriptor.add_axis(exp.segment_axis)

            # Add averaging if necessary
            if averages > 1:
                descriptor.add_axis(DataAxis("averages", range(averages)))

            # Add the output connectors to the experiment and set their base descriptor
            mqp = self.qubit_proxies[mq.label]

            connector_by_qp[mqp.id] = exp.add_connector(mqp)
            connector_by_qp[mqp.id].set_descriptor(descriptor)

            # Add the channel to the instrument
            dig.instr.add_channel(channel)
            exp.chan_to_dig[channel] = dig.instr
            exp.chan_to_oc [channel] = connector_by_qp[mqp.id]
            exp.qubit_to_dig[mq.id]  = dig

        # Find the number of measurements
        segments_per_dig = {receiver_chan.receiver: meta_info["receivers"][receiver.label] for receiver_chan in receiver_chans
                                                         if receiver.label in meta_info["receivers"].keys()}

        # Configure receiver instruments from the database objects
        # this must be done after adding channels.
        for dig in receivers:
            dig.number_averages  = averages
            dig.number_waveforms = 1
            dig.number_segments  = segments_per_dig[dig]
            dig.instr.proxy_obj  = dig

        # Restrict the graph to the relevant qubits
        measured_qubit_names = [q.label for q in measured_qubits]
        self.session.commit()
        # Configure the individual filter nodes
        for node in self.meas_graph.nodes():
            if isinstance(node, bbndb.auspex.FilterProxy):
                if node.qubit_name in measured_qubit_names:
                    new_filt = self.filter_map[type(node)]()
                    # logger.info(f"Created {new_filt} from {node}")
                    new_filt.configure_with_proxy(node)
                    new_filt.proxy = node
                    proxy_to_filter[node.id] = new_filt
                    if isinstance(node, bbndb.auspex.OutputProxy):
                        exp.qubits_by_output[new_filt] = node.qubit_name

        # Connect the filters together
        graph_edges = []
        self.session.commit()
        for node1, node2 in self.meas_graph.edges():
            if node1.qubit_name in measured_qubit_names and node2.qubit_name in measured_qubit_names:
                if isinstance(node1, bbndb.auspex.FilterProxy):
                    filt1 = proxy_to_filter[node1.id]
                    oc   = filt1.output_connectors["source"]
                elif isinstance(node1, bbndb.auspex.QubitProxy):
                    oc   = connector_by_qp[node1.id]
                filt2 = proxy_to_filter[node2.id]
                ic   = filt2.input_connectors["sink"]
                graph_edges.append([oc, ic])

        # # For lookup
        # exp.proxy_to_filter = proxy_to_filter
        # exp.filter_to_proxy = {v: k for k,v in proxy_to_filter.items()}

        # Define the experiment graph
        exp.set_graph(graph_edges)

        return exp

    def run(self, *args, **kwargs):
        exp = self.create(*args, **kwargs)
        exp.run_sweeps()
        return exp

    def qubit(self, qubit_name):
        return self.qubit_proxies[qubit_name]
        # return []

    def save_pipeline(self, name):
        cs = [bbndb.auspex.Connection(pipeline_name=name, node1=n1, node2=n2, time=datetime.datetime.now()) for n1, n2 in self.meas_graph.edges()]
        for c in cs:
            self.session.add(cs)

    def load_pipeline(self, pipeline_name):
        cs = select(c for c in bbndb.auspex.Connection if c.pipeline_name==pipeline_name)
        if len(cs) == 0:
            print(f"No results for pipeline {pipeline_name}")
            return
        else:
            temp_edges = [(c.node1, c.node2) for c in cs]
            self.meas_graph.clear()
            self.meas_graph.add_edges_from(temp_edges)
            for c in cs:
                c.node1.exp = c.node2.exp = self

    def show_pipeline(self, pipeline_name=None):
        """If a pipeline name is specified query the database, otherwise show the
        current pipeline."""
        if pipeline_name:
            cs = select(c for c in bbndb.auspex.Connection if c.pipeline_name==pipeline_name)
            if len(cs) == 0:
                print(f"No results for pipeline {pipeline_name}")
                return
            temp_edges = [(c.node1, c.node2) for c in cs]
            graph = nx.DiGraph()
            graph.add_edges_from(temp_edges)
        else:
            graph = self.meas_graph

        labels = {n: n.node_label() for n in graph.nodes()}
        colors = ["#3182bd" if isinstance(n, bbndb.auspex.QubitProxy) else "#ff9933" for n in graph.nodes()]
        self.plot_graph(graph, labels, colors=colors)

    def reset_pipelines(self):
        for qp in self.qubit_proxies.values():
            qp.clear_pipeline()
            qp.auto_create_pipeline()

    def clear_pipelines(self):
        for qp in self.qubit_proxies.values():
            qp.clear_pipeline()

    def show_connectivity(self):
        pass

    def plot_graph(self, graph, labels, prog="dot", colors='r'):
        import matplotlib.pyplot as plt
        plt.figure(figsize=(12, 4))
        pos = nx.drawing.nx_pydot.graphviz_layout(graph, prog=prog)

        # Create position copies for shadows, and shift shadows
        pos_shadow = copy.copy(pos)
        pos_labels = copy.copy(pos)
        for idx in pos_shadow.keys():
            pos_shadow[idx] = (pos_shadow[idx][0] + 0.01, pos_shadow[idx][1] - 0.01)
            pos_labels[idx] = (pos_labels[idx][0] + 0, pos_labels[idx][1] + 15 )
        nx.draw_networkx_nodes(graph, pos_shadow, node_size=100, node_color='k', alpha=0.5)
        nx.draw_networkx_nodes(graph, pos, node_size=100, node_color=colors, linewidths=1, alpha=1.0)
        nx.draw_networkx_edges(graph, pos, width=1)
        nx.draw_networkx_labels(graph, pos_labels, labels, font_size=10, bbox=dict(facecolor='white', alpha=0.95), horizontalalignment="center")

        ax = plt.gca()
        ax.axis('off')
        ax.set_xlim((ax.get_xlim()[0]-20.0, ax.get_xlim()[1]+20.0))
        ax.set_ylim((ax.get_ylim()[0]-20.0, ax.get_ylim()[1]+20.0))
        plt.show()

    def __getitem__(self, key):
        return self.qubit(key)
