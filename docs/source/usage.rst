.. _usage:

Usage
=====

From the command line
---------------------

The package installs a ``hermess`` command (equivalently ``python -m hermess``):

.. code-block:: bash

   hermess list                             # the systems that ship with the package
   hermess run 3bus --t-end 5               # simulate one and plot the trajectories
   hermess run ieee39_conv --small-signal   # the shipped demo scenario

``hermess run`` plots the bus voltages and the internal states unless
``--no-plot`` is given, and takes ``--t-end``, ``--ts`` and, for systems of
your own, ``--system-root``. Every other simulation setting of
:class:`hermess.config.Config` is reachable with ``--set KEY=VALUE``, for
example ``--set line_dyn=false --set omega_mode=coi``.

From Python
-----------

To run a system from a script or a notebook, without touching ``config.py``:

.. code-block:: python

   import hermess

   hermess.list_systems()                              # what is available
   dae = hermess.simulate("3bus", T_end=5.0)          # run one, get the finished model back
   dae = hermess.simulate("ieee39", line_dyn=False, T_end=10.0, small_signal_analysis=True)

Any field of :class:`~hermess.config.Config` can be passed as a keyword argument
(see :ref:`configuration` for the full list), and ``system_root`` points at a
directory of systems of your own:

.. code-block:: python

   dae = hermess.simulate("my_case", system_root="~/my_systems", T_end=10.0)

Plotting is off by default in :func:`hermess.simulate`, unlike the shipped
configuration, so the call returns quietly and you plot what you want from the
returned object.

Reading the results
-------------------

The returned :class:`~hermess.system.DaeSim` holds both the symbolic model and
the trajectories:

.. code-block:: python

   dae.time_steps                       # the time grid
   dae.x_full, dae.y_full               # differential and algebraic trajectories
   dae.grid.yf                          # bus voltages
   dae.grid.power_flow_tables(dae)      # initial power flow as two pandas DataFrames

After a run with ``small_signal_analysis=True``:

.. code-block:: python

   dae.A                                # reduced state matrix at the operating point
   dae.eigenvalues                      # its spectrum
   dae.state_names                      # rows and columns of dae.A
   dae.participation_table(mode=1)      # participation factors of the least damped mode
   dae.print_modal_report()             # the same information as a text report
   dae.plot_eigenvalues()               # s-plane scatter

Individual devices keep their own states, so ``device.xf["omega"]`` gives the
trajectory of one state of one device.

Using your own models
---------------------

A model written outside the package, a device class or one of the pluggable
strategies (AVR, governor, PSS, shaft, and the converter's filter, angle,
voltage, inner and PLL blocks), becomes selectable from a system file once it is
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
``sim_param.txt``. See :ref:`models` for the shipped models and
:ref:`user_models` for the details.

Examples
--------

The notebooks in
`examples/ <https://github.com/maitrayadesai/hermess/tree/main/examples>`_ work
through complete studies, including the IEEE 39-bus case with converters
(``examples/renewables/39bus_inv.ipynb``) and a grid-forming converter example
that bridges the simulator to PyTorch (``examples/neural_gfm_control``). The
systems that ship with the package are described in :ref:`test_cases`.

Next steps
----------

:ref:`configuration` lists every simulation setting, and :ref:`advanced_usage`
describes the system-file format, the disturbances and the analysis outputs.
