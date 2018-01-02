.. _configuration:

Configuration
=============

Both *Auspex* and `QGL <https://github.com/bbn-q/qgl>`_ require a minimal amount of configuration
to work correctly.  In *Auspex*, experimental information is separated into
three YAML configuration files: **measure.yml**, **filters.yml** and
**instruments.yml**.  The segmentation reflects the way Auspex conceptualizes
the data taking process.  Roughly speaking, parameters for the things you'd
like to measure are listed in the measure.yml file, how the data is processed
in its software pipeline is in specified in filters.yml and specific
instrument parameters you might want to set or sweep are listed in
instruments.yml.  It's worth noting the measure.yml file has an `include!`
keyword that points to the information in the filters and instruments files.
A very short example measure file might be:

.. code-block:: YAML

    qubits:
      q1:
        measure:
          AWG: BBNAPS1 12
          trigger: BBNAPS1 12m1
          receiver: q1-RawSS
          generator: Holz1
          autodyne_freq: 10000000.0
          pulse_params:
            amp: 1.0
            cutoff: 2.0
            length: 5.0e-07
            shape_fun: tanh
            sigma: 1.0e-09
        control:
          AWG: BBNAPS2 12
          generator: Holz2
          pulseParams:
            cutoff: 2.0
            length: 7.0e-08
            pi2Amp: 0.4
            piAmp: 0.8
            shape_fun: drag
            drag_scaling: 0.0
            sigma: 5.0e-09

    instruments: !include instruments.yml
    filters: !include filters.yml

We'll detail what all the parameters here mean below.  The important thing to
notice here is the file structure.  There's a top level qubit structure in the
file followed by any number of qubits.  In this case there's just one qubit
called *q1*.  Each qubit structure will have a measure and control section
describing some of the parameters necessary for controlling and reading out
the qubit state.  Finally, there are two include statements which tell Auspex
where to load the additional information it will need to run an experiment.
Those files will have a similar structure with a label identifying the top
entity and inside will be associated parameters.  For now let's focus on the
*measure.yml* file.

To simplify integration with our pulse sequence compiler

More in-depth documentation coming...

Config Files
************

Auspex uses a `YAML <http://www.yaml.org>`_ configuration file to describe qubit experiments. By default, the measurement file is assumed to be in the location specified by the environment variable *BBN_MEAS_FILE*. Otherwise, the user can manually specify where the configuration file is located using the *meas_file* keyword argument of the :ref:`QubitExpFactory <qubitexpfactory>` *create()* and *run()* methods.

The config file, which is shared by QGL, must contain a few different blocks. First the *config* section specifies where the waveform files, integration kernels, and logs should reside:

.. code-block:: yaml

  config:
    AWGDir: /tmp/awg
    KernelDir: /tmp/kern
    LogDir: /tmp/alog

In a departure from the channel centric behavior of our legacy *PyQLab* stack, the configuration is qubit centric. The *qubit* definition section will resemble the following:

.. code-block:: yaml

  qubits:
    q1:
      measure:
        AWG: BBNAPS1 12
        trigger: BBNAPS1 12m1
        receiver: q1-IntegratedSS
        generator: Holz1
        autodyne_freq: 10000000.0
        pulse_params:
          amp: 1.0
          cutoff: 2.0
          length: 5.0e-07
          shape_fun: tanh
          sigma: 1.0e-09
      control:
        AWG: BBNAPS2 12
        generator: Holz2
        frequency: -49910002.0
        pulse_params:
          cutoff: 2.0
          length: 7.0e-08
          pi2Amp: 0.50045
          piAmp: 1.0009
          shape_fun: drag
          drag_scaling: 0.0
          sigma: 5.0e-09

The control and measurement configurations are specified separately. If a generator is defined for either, Auspex infers that we are mixing up from a lower speed AWG. Otherwise, Auspex infers that direct synthesis is being performed.

Qubit Parameters
****************

Below is a detailed list of pulse parameters and what they control inside the
software stack.  The names and design implicitly assume a heterodyne-like measurement
and qubit control with an IQ mixer.  If you're using a different control or
measurement scheme you'll need to modify the underlying instrument drivers.
For more documentation on this see the :ref:`instruments` section.  Note that most of
the pulse parameters will be used by both QGL and Auspex.

Measurement params
##################

- AWG:
      Each qubit channel assumes an AWG channel (IQ) pair for both control and
      readout.  A generalization of the AWG instrument class would allow for control
      different from the expected all microwave control with an IQ mixer.  In the
      example above, the AWG is an APS2 called 'BBNAPS1'.  The '12' specifies the
      AWG analog outputs 1 and 2 on the APS2 as the ones mapped to I an Q quadrature
      control for the measurement.
- trigger:
      This is a simple marker emitted when any signal is played out of the
      associated *AWG* channel.  These are useful for triggering external equipment
      such as digitizer cards like the *X6* or *Alazar*.  QGL will expect a trigger
      to be defined explicitly for each measurement channel to trigger capture of
      the measurement signal.
- receiver:
      The filter StreamSelector associated with the qubit measurement.  This tells
      Auspex which set of digitized data is associated with which qubit and where
      it should flow in the filter pipeline.  The receiver name must be defined in
      the filters.yml file and is a require parameter for each measure channel.
- generator:
      This specifies the microwave generator being used as the local oscillator
      for measurement.  In the above case we're using a generator called 'Holz1'
      that should be defined in the instruments file.
- autodyne_freq:
      This specifies the offset from the *generator* frequency modulated into the
      measurement signal.  The particular measurement scheme we use in our lab
      is referred to as 'autodyne' where a measurement signal is split before being
      sent to the sample, frequency modulated by a certain amount, broadcast and then down
      mixed with itself on return.  See the experimental section of [RJG+15]_
      and [JPM+12]_ for more details.  The result pushes the measurement signal
      away from the carrier such that resonator-freq = generator-freq +
      autodyne_freq. Note this parameter can be set to zero to operate in base
      band mode.
These are pulse specific parameters which are specified in their YAML block.

- amp:
      This is the amplitude on a normalized scale from [-1, 1] where negative values
      correspond to opposite phases in the signal after modulation by the IQ mixer.
- cutoff:
      When gaussian pulses are used it becomes necessary to specify a point at which
      the Arb/DAC/voltage voltage values go to zero.  The cutoff sets the number
      of standard deviations away from the center when the pulse finally reaches
      zero.  For tanh shapes this parameter 'squeezes' the edge tanh envelopes by
      the cutoff value times the sigma value.
- length:
      The length of the pulse in seconds
- shape_fun:
      The shape of the measurement pulse.  Current options are gaussian, square (constant),
      drag, tanh etc...  All the options are defined in the QGL/PulseShapes.py file.
      The most relevant for measurement are constant, tanh (a rounded pulse
      composed of two tanh shapes ), exp_decay, CLEAR.  See the
      QGL `pulse documentation`_ for more details.
- sigma:
      Sets the length of a standard deviation in seconds for Guassian pulses and
      sets the edge profile for tanh pulses as ``tanh(x)/sigma``.

.. _pulse documentation: https://bbn-q.github.io/QGL/#pulse-shapes-and-waveforms

The *instruments* section gives the instrument configuration parameters:

.. code-block:: yaml

  instruments:
    BBNAPS1:
      type: APS2
      master: true
      slave_trig: 12m4
      address: 192.168.5.20
      seq_file: thing.h5
      trigger_interval: 5.0e-06
      trigger_source: Internal
      delay: 0.0
      tx_channels:
        '12':
          phase_skew: -11.73
          amp_factor: 0.898
          '1':
            offset: 0.1
            amplitude: 0.9
          '2':
            offset: 0.02
            amplitude: 0.8
      markers:
        12m1:
          delay: -5.0e-08
        12m2:
          delay: 0.0
        12m3:
          delay: 0.0
        12m4:
          delay: 0.0
      enabled: true
    BBNAPS2:
      type: APS2
      master: false
      address: 192.168.5.21
      seq_file: thing2.h5
      trigger_interval: 5.0e-06
      trigger_source: External
      delay: 0.0
      tx_channels:
        '12':
          phase_skew: 10
          amp_factor: 0.898
          '1':
            offset: 0.10022
            amplitude: 0.9
          '2':
            offset: 0.020220000000000002
            amplitude: 0.8
      markers:
        12m1:
          delay: -5.0e-08
        12m2:
          delay: 0.0
        12m3:
          delay: 0.0
        12m4:
          delay: 0.0
      enabled: true
    X6-1:
      type: X6
      address: 0
      acquire_mode: digitizer
      gen_fake_data: true
      ideal_data: cal_fake_data
      reference: external
      record_length: 1024
      nbr_segments: 1
      nbr_round_robins: 20
      rx_channels:
        '1':
        '2':
      streams: [raw, result1, result2]
      enabled: true
      exp_step: 0
    Holz1:
      type: HolzworthHS9000
      address: HS9004A-009-1
      power: -10
      frequency: 6000000000.0
      enabled: true
    Holz2:
      type: HolzworthHS9000
      address: HS9004A-009-2
      power: -10
      frequency: 5000090023.0
      enabled: true

Note how the APS2 devices are defined. Each instrument *should* (have patience) possess the *yaml_template* class property that gives an example of the yaml configuration that can be found by running, e.g.:

.. code-block:: python

  from auspex.instruments import APS2
  APS2.yaml_template

Also, note that the instruments referenced in the *qubits* section are defined in the *instruments* section. The *filter* pipeline, which controls the processing of data, can be defined as follows:

.. code-block:: yaml

  filters:
    q1-RawSS:
      type: X6StreamSelector
      source: X6-1
      stream_type: Raw
      channel: 1
      dsp_channel: 1
      enabled: true
    q1-IntegratedSS:
      type: X6StreamSelector
      source: X6-1
      stream_type: Integrated
      channel: 1
      dsp_channel: 0
      kernel: np.ones(1024, dtype=np.float64)
      enabled: true
    Demod-q1:
      type: Channelizer
      source: q1-RawSS
      decimation_factor: 4
      frequency: 10000000.0
      bandwidth: 5000000.0
      enabled: true
    Int-q1:
      type: KernelIntegrator
      source: Demod-q1
      box_car_start: 5.0e-07
      box_car_stop: 9.0e-07
      enabled: true
    avg-q1:
      type: Averager
      source: Int-q1
      axis: round_robins
      enabled: true
    avg-q1-int:
      type: Averager
      source: q1-IntegratedSS
      axis: round_robins
      enabled: true
    final-avg-buff:
      type: DataBuffer
      source: avg-q1 final_average
      enabled: false
    final-avgint-buff:
      type: DataBuffer
      source: avg-q1-int final_average
      enabled: false
    partial-avg-buff:
      type: DataBuffer
      source: avg-q1 partial_average
      enabled: false
    q1-IntPlot:
      type: Plotter
      source: avg-q1 final_average
      plot_dims: 1
      plot_mode: real/imag
      enabled: false
    q1-DirectIntPlot:
      type: Plotter
      source: avg-q1-int final_average
      plot_dims: 1
      plot_mode: real/imag
      enabled: false
    q1-DirectIntPlot-unroll:
      type: Plotter
      source: q1-IntegratedSS final_average
      plot_dims: 0
      plot_mode: real/imag
      enabled: false
    q1-WriteToHDF5:
      source: avg-q1-int final_average
      enabled: true
      compression: true
      type: WriteToHDF5
      filename: .\test
      groupname: main
      add_date: false
      save_settings: false

**However**, we advise that the user not directly edit the filter section when possible. Our GUI node editor `Quince <https://github.com/bbn-q/quince>`_ can be used to graphically edit the filter pipeline, and can be easily launched from the python environment by running.

.. code-block:: python

    from from auspex.exp_factory import quince
    quince() # takes an optional argument giving the measurement file

In order to split configuration across multiple files, Auspex extends the YAML loader to provide an *!import* macro that can be employed as follows:

.. code-block:: yaml

  instruments: !include instruments.yml

Auspex will try to repsect these macros, but pathological cases will probably fail.

References
**********

.. [JPM+12] Appl. Phys. Lett. 101, 042604 (2012); https://doi.org/10.1063/1.4739454
.. [RJG+15] Phys. Rev. A 91, 022118 (2015); https://journals.aps.org/pra/abstract/10.1103/PhysRevA.91.022118
