.. _usage:

Usage
=====

Basic Usage
------------

To run the simulation configured in ``hermess/config.py``, execute the package from the repository root:

.. code-block:: bash

  python -m hermess

From Python
-----------

To run a ready-made system from a script or a notebook, without touching
``config.py``:

.. code-block:: python

  import hermess

  hermess.list_systems()                              # what is available
  dae = hermess.simulate("3_bus", T_end=5.0)          # run one, get the finished model back
  dae = hermess.simulate("IEEE39_bus", line_dyn=False, T_end=10.0, small_signal_analysis=True)

Any field of :class:`~hermess.config.Config` can be passed as a keyword argument;
``system_root`` points at your own directory of systems. The returned
:class:`~hermess.system.DaeSim` holds both the symbolic model and the
trajectories: ``dae.time_steps``, ``device.xf[state]``, ``dae.grid.yf[bus]``,
``dae.A`` and ``dae.eigenvalues`` after a small-signal analysis,
``dae.participation_table(mode)``, and ``dae.grid.power_flow_tables(dae)`` for the
initial operating point.

Using your own models
---------------------

A model written outside the package -- a device class, or one of the pluggable
strategies (AVR, governor, PSS, shaft, and the converter's filter, angle,
voltage, inner and PLL blocks) -- becomes selectable from a system file once it is
registered:

.. code-block:: python

  import hermess
  from hermess.devices.inverter_angle import AngleSource

  class VSMAngle(AngleSource):
      ...

  hermess.register(VSMAngle, "VSM")      # now:  angle = "VSM"  in sim_param.txt
  hermess.registered("angle")            # what can be selected today

The kind is inferred from the base class, so the same call takes any model type;
a registered *device* is addressed by its class name in the first column of
``sim_param.txt``. See :ref:`models` for the shipped models.

Examples
--------

To get a feeling for different examples of the simulator, we prepared some short `./examples <https://github.com/maitrayadesai/hermess/tree/main/examples>`_
to help you get started.

Modifying Configuration
------------------------

To adjust simulation parameters, you can modify the configuration object located in `./config.py` by calling the appropriate method. See :ref:`configuration`
for details. See also the IEEE 39 bus test case modified to include renewable generation in
``examples/renewables/39bus_inv.ipynb``, and all available test cases in :ref:`test_cases`.





Advanced Usage
--------------

Refer to :ref:`advanced_usage` for more details regarding changing the system parameters or simulated disturbances.
