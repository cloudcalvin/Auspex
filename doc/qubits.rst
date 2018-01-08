.. _qubit_experiments:

Qubit Experiments
=================

Instrument Drivers
******************

For `libaps2 <https://github.com/bbn-q/libaps2>`_, `libalazar <https://github.com/bbn-q/libalazar>`_, and `libx6  <https://github.com/bbn-q/libx6>`_, one should be able to *conda install -c bbn-q xxx* in order to obtain binary distributions of the relevant packages. Otherwise, one must obtain and build those libraries (according to their respective documentation), then make the shared library build products and any python packages available to Auspex by placing them on the path.  Due to the number of issues that can crop up during this process we strongly recommend users install these drivers from the bbn-q conda channel unless there's a strong reason not to.

The Qubit Experiment Factory
****************************

:ref:`QubitExpFactory <qubitexpfactory>` reads in the configuration YAML flat files and contructs an Auspex *Experiment* from them. It also accepts a *meta_file*, generated directly by `QGL <https://github.com/BBN-Q/QGL>`_, that changes the experiment configuration to conform to a desired pulse sequence.


.. code-block:: python

    # Cavity Sweep
    from QGL import *
    from from auspex.exp_factory import QubitExpFactory
    cl = ChannelLibrary()
    q = QubitFactory("q1")
    exp = QubitExpFactory.create(PulsedSpec(q))
    exp.add_qubit_sweep("q1 measure frequency", np.linspace(6e9, 6.5e9, 500))
    exp.run_sweeps()

Pulse Calibrations
******************

Auspex has two built in phase calibration function to make qubit calibration
easier.  The code for calibration is located in
`/src/auspex/pulse_calibration`.  A typical situation for an experimenter might
be calibrating the amplitude of a pulse to implement a pi/2 pulse.  Auspex has
a :py:func:`auspex.pulse_calibration.calibrate` function that takes in a list of
qubit calibration objects and  executes them in order:

.. code-block:: python

    calibrate([RabiAmpCalibration("q1"), Pi2Calibration("q1")]

In the example above, a basic Rabi oscillation experiment is run to get a rough calibration of what the amplitude should be for the given pulse parameters.  Then a finer calibration based on robust phase estimation is run.
