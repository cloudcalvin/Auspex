import logging
import inspect
import time
import itertools
import asyncio

import numpy as np
import scipy as sp
import pandas as pd
import networkx as nx
import h5py

from .instruments.instrument import Instrument
from .stream import DataStream, DataAxis, DataStreamDescriptor, InputConnector, OutputConnector

logger = logging.getLogger('pycontrol')
logging.basicConfig(format='%(name)s-%(levelname)s: \t%(message)s')
logger.setLevel(logging.INFO)

class Quantity(object):
    """Physical quantity to be measured."""
    def __init__(self, name=None, unit=None):
        super(Quantity, self).__init__()
        self.name   = name
        self.unit   = unit
        self.method = None
        self._value = None
        self.delay_before = 0
        self.delay_after = 0

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    def assign_method(self, method):
        logger.debug("Setting method of Quantity %s to %s" % (self.name, str(method)) )
        self.method = method

    def measure(self):
        logger.debug("%s Being asked to measure" % self.name)
        if self.delay_before is not None:
            time.sleep(self.delay_before)

        try:
            self._value = self.method()
        except:
            self._value = None
            print("Unable to measure %s." % self.name)

        if self.delay_after is not None:
            time.sleep(self.delay_after)

    def __str__(self):
        result = ""
        result += "%s" % str(self._value)
        if self.unit:
            result += " %s" % self.unit
        return result

    def __repr__(self):
        result = "<Quantity(name='%s'" % self.name
        result += ",value=%s" % repr(self._value)
        if self.unit:
            result += ",unit='%s'" % self.unit
        return result + ")>"

class Parameter(object):
    """ Encapsulates the information for an experiment parameter"""

    def __init__(self, name=None, unit=None, default=None, abstract=False):
        self.name     = name
        self._value   = default
        self.unit     = unit
        self.default  = default
        self.method   = None
        self.abstract = abstract # Is this something we can actually push?

        # Hooks to be called before or after updating a sweep parameter
        self.pre_push_hooks = []
        self.post_push_hooks = []

    def add_pre_push_hook(self, hook):
        self.pre_push_hooks.append(hook)

    def add_post_push_hook(self, hook):
        self.post_push_hooks.append(hook)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    def __str__(self):
        result = ""
        result += "%s" % str(self.value)
        if self.unit:
            result += " %s" % self.unit
        return result

    def __repr__(self):
        result = "<Parameter(name='%s'" % self.name
        result += ",value=%s" % repr(self.value)
        if self.unit:
            result += ",unit='%s'" % self.unit
        return result + ")>"

    def assign_method(self, method):
        logger.debug("Setting method of Parameter %s to %s" % (self.name, str(method)) )
        self.method = method

    def push(self):
        if self.method is None:
            raise Exception("No method for this parameter is defined...")
        if not self.abstract:
            for pph in self.pre_push_hooks:
                pph()
            logger.debug("Calling method of Parameter %s with value %s" % (self.name, self._value) )
            self.method(self._value)
            for pph in self.post_push_hooks:
                pph()

class FloatParameter(Parameter):

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        try:
            self._value = float(value)
        except ValueError:
            raise ValueError("FloatParameter given non-float value of "
                             "type '%s'" % type(value))

    def __repr__(self):
        result = super(FloatParameter, self).__repr__()
        return result.replace("<Parameter", "<FloatParameter", 1)

class IntParameter(Parameter):

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        try:
            self._value = int(value)
        except ValueError:
            raise ValueError("IntParameter given non-int value of "
                             "type '%s'" % type(value))

    def __repr__(self):
        result = super(IntParameter, self).__repr__()
        return result.replace("<Parameter", "<IntParameter", 1)

class SweptParameter(object):
    """Data structure for a swept Parameters, contains the Parameter
    object rather than subclassing it since we just need to keep track
    of some values"""
    def __init__(self, parameter, values):
        self.parameter = parameter
        self.associated_axes = []
        self.update_values(values)
        self.push = self.parameter.push
        
    def update_values(self, values):
        self.values = values
        self.length = len(values)
        for axis in self.associated_axes:
            axis.points = self.values

    @property
    def value(self):
        return self.parameter.value
    @value.setter
    def value(self, value):
        self.parameter.value = value

    def __repr__(self):
        return "<SweptParameter: {}>".format(self.parameter.name)

class SweptParameterGroup(object):
    """For unstructured (meshed) coordinate tuples. The actual values 
    are stored locally as _values, and we acces each tuples by indexing
    into that array."""
    def __init__(self, parameters, values):
        self.parameters = parameters
        self.associated_axes = []
        self.update_values(values)

    def push(self):
        # Values here will just be the index
        for p in self.parameters:
            p.push()

    def update_values(self, values):
        self._values = values
        self.length = len(values)
        self.values = list(range(self.length)) # Dummy index list for sweeper
        for axis in self.associated_axes:
            axis.points = self._values

    @property
    def value(self):
        return [p.value for p in self.parameters]
    @value.setter
    def value(self, index):
        for i, p in enumerate(self.parameters):
            p.value = self._values[index, i]

    def __repr__(self):
        return "<SweptParameter: {}>".format([p.name for p in self.parameters])

class ExperimentGraph(object):
    def __init__(self, edges, loop):
        self.dag = None
        self.edges = []
        self.loop = loop
        self.create_graph(edges)

    def dfs_edges(self):
        # Edge depth-first traversal of the graph

        # Find the input nodes
        input_nodes = [n for n in self.dag.nodes() if self.dag.in_degree(n) == 0]
        logger.debug("Input nodes for DFS are '%s'", input_nodes)

        dfs_edge_iters  = [nx.edge_dfs(self.dag, input_node) for input_node in input_nodes]
        processed_edges = [] # Keep track of what we've initialized

        for ei in dfs_edge_iters:
            for edge in ei:
                if edge not in processed_edges:
                    processed_edges.append(edge)
                    yield edge

    def create_graph(self, edges):
        dag = nx.DiGraph()
        self.edges = []
        for edge in edges:
            obj = DataStream(name="{}_TO_{}".format(edge[0].name, edge[1].name),
                             loop=self.loop)
            edge[0].add_output_stream(obj)
            edge[1].add_input_stream(obj)
            self.edges.append(obj)
            dag.add_edge(edge[0].parent, edge[1].parent, object=obj)

        self.dag = dag

class MetaExperiment(type):
    """Meta class to bake the instrument objects into a class description
    """

    def __init__(self, name, bases, dct):
        type.__init__(self, name, bases, dct)
        logger.debug("Adding controls to %s", name)
        self._parameters        = {}
        self._quantities        = {}
        self._instruments       = {}
        self._traces            = {}

        # Beware, passing objects won't work at parse time
        self._output_connectors = []

        for k,v in dct.items():
            if isinstance(v, Instrument):
                logger.debug("Found '%s' instrument", k)
                self._instruments[k] = v
            elif isinstance(v, Parameter):
                logger.debug("Found '%s' parameter", k)
                if v.name is None:
                    v.name = k
                self._parameters[k] = v
            elif isinstance(v, Quantity):
                logger.debug("Found '%s' quantity", k)
                if v.name is None:
                    v.name = k
                self._quantities[k] = v
            elif isinstance(v, OutputConnector):
                logger.debug("Found '%s' output connector.", k)
                self._output_connectors.append(k)

class Experiment(metaclass=MetaExperiment):
    """The measurement loop to be run for each set of sweep parameters."""
    def __init__(self):
        super(Experiment, self).__init__()

        # Iterable that yields sweep values
        self._sweep_generator = None

        # Container for patameters that will be swept
        self._swept_parameters = []

        # This holds the experiment graph
        self.graph = None

        # Things we can't metaclass
        self.output_connectors = {}
        for oc in self._output_connectors:
            a = OutputConnector(name=oc, parent=self)
            a.parent = self
            self.output_connectors[oc] = a
            setattr(self, oc, a)

        # Create the asyncio measurement loop
        self.loop = asyncio.get_event_loop()

        # Run the stream init
        self.init_streams()

    def set_graph(self, edges):
        unique_nodes = []
        for eb, ee in edges:
            if eb.parent not in unique_nodes:
                unique_nodes.append(eb.parent)
            if ee.parent not in unique_nodes:
                unique_nodes.append(ee.parent)
        self.nodes = unique_nodes
        self.graph = ExperimentGraph(edges, self.loop)
        self.update_descriptors()

    def init_streams(self):
        """Establish the base descriptors for any internal data streams and connectors."""
        pass

    def init_instruments(self):
        """Gets run before a sweep starts"""
        pass

    def shutdown_instruments(self):
        """Gets run after a sweep ends, or when the program is terminated."""
        pass

    async def run(self):
        """This is the inner measurement loop, which is the smallest unit that
        is repeated across various sweep variables. For more complicated run control
        than can be provided by the automatic sweeping, the full experimental 
        operation should be defined here"""
        pass

    def run_loop(self):
        """This runs the asyncio main loop."""
        tasks = [n.run() for n in self.nodes]
        self.loop.run_until_complete(asyncio.wait(tasks))

    def reset(self):
        for edge in self.graph.edges:
            edge.reset()
        self.update_descriptors()
        self.generate_sweep()

    def update_descriptors(self):
        logger.debug("Starting descriptor update in experiment.")
        for oc in self.output_connectors.values():
            oc.update_descriptors()

    async def sweep(self):
        # Keep track of the previous values
        last_param_values = None
        logger.debug("Starting experiment sweep.")
        for param_values in self._sweep_generator:

            # Update the parameter values. Unles set and push if there has been a change
            # in the value from the previous iteration.
            for i, sp in enumerate(self._swept_parameters):
                if last_param_values is None or param_values[i] != last_param_values[i]:
                    logger.debug("Pushing value %s to parameter %s.", param_values[i], sp)
                    sp.value = param_values[i]
                    sp.push()

            # update previous values
            last_param_values = param_values

            # Run the procedure
            await self.run()

    def run_sweeps(self):
        # We don't want to wait for the run method explicitly
        other_nodes = self.nodes[:]
        other_nodes.remove(self)
        tasks = [n.run() for n in other_nodes]
        tasks.append(self.sweep())
        self.loop.run_until_complete(asyncio.wait(tasks))
        
    def add_sweep(self, param, sweep_list):
        """Add a good-old-fasioned one-variable sweep."""
        p = SweptParameter(param, sweep_list)
        self._swept_parameters.append(p)
        self.generate_sweep()
        for oc in self.output_connectors.values():
            ax = DataAxis(param.name, sweep_list)
            logger.debug("Adding sweep axis %s to connector %s.", ax, oc.name)
            oc.descriptor.add_axis(ax)
            p.associated_axes.append(ax)
        self.update_descriptors()
        return p

    def add_unstructured_sweep(self, parameters, coords):
        p = SweptParameterGroup(parameters, coords)
        self._swept_parameters.append(p)
        self.generate_sweep()
        for oc in self.output_connectors.values():
            ax = DataAxis("Unstructured", coords, unstructured=True, coord_names=[p.name for p in parameters])
            logger.debug("Adding unstructred sweep axis %s to connector %s.", ax, oc.name)
            oc.descriptor.add_axis(ax)
            p.associated_axes.append(ax)
        self.update_descriptors()
        return p

    def generate_sweep(self):
        self._sweep_generator = itertools.product(*[sp.values for sp in self._swept_parameters])
