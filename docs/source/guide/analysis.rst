.. _analysis:

Analysis and plotting
=====================

``hermess.analysis`` turns a finished run into tables and figures with one
import. It is built around a single idea: **every quantity in a run has an
address**, ``owner:quantity``, and everything that takes a "what to plot"
argument accepts the same selector.

.. code-block:: python

   from hermess.analysis import *

   root = copy_system("3bus_loadstep")   # editable local copy of a shipped system
   dae = simulate("3bus_loadstep", system_root=root, T_end=5.0, quiet=True)
   plot(dae, ["*:f", "bus*:v"])

Signal addresses
----------------

.. code-block:: text

   SG1:omega      a machine state           GFMI2:Pc_tilde   a converter state
   SG1:f          frequency [Hz]            GFMI2:f          frequency [Hz]
   SG1:P          power injection [MW]      bus3:v           voltage magnitude
   bus3:theta     voltage angle [deg]       line1-2:P        branch flow [MW]

:func:`~hermess.analysis.signals` lists every address of a run with its unit
and meaning. Selectors are case-insensitive, understand ``*`` and ``?`` globs,
and come in several shapes:

.. code-block:: python

   plot(dae, "SG1:omega")                  # one signal
   plot(dae, "*:f")                        # that quantity on every device
   plot(dae, "f")                          # same, the "*:" is implied
   plot(dae, ["bus1:v", "bus3:v"])         # a list
   plot(dae, "bus*:v")                     # a glob
   plot(dae, {"SG1": ["omega", "delta"]})  # a dict
   plot_states(dae, "GFMI2")               # every state of one device
   compare({"droop": d1, "VSM": d2}, "GFMI2:f")   # across runs

An unknown name raises with suggestions. Buses and branches may be addressed
with or without their prefix (``"3:v"`` is ``"bus3:v"``).

Signals come in five kinds: device ``state`` trajectories, private
``algebraic`` variables, ``derived`` quantities evaluated from the model's own
symbolic expressions (frequency, electrical power), and ``bus`` and ``branch``
network quantities. The derived frequencies use the same segment-aware
machinery as :func:`hermess.results.extract_results`, so they stay correct
across a ``SETPOINT`` disturbance.

Tables and exports
------------------

.. code-block:: python

   signals(dae)                  # the address book, as a DataFrame
   get(dae, "*:f")               # {name: numpy array}
   to_dataframe(dae, "*:f")      # DataFrame indexed by time
   to_csv(dae, "f.csv", "*:f")   # t plus one named column per signal
   metrics(dae)                  # pre-event value, nadir/peak, final, max rate
   summary(dae)                  # one paragraph: size, devices, disturbances

For the operating point and the small-signal analysis:

.. code-block:: python

   power_flow_table(dae)             # the initial power flow ("bus" or "branch")
   small_signal(dae)                 # run (if needed) and return the mode list
   modal_table(dae)                  # eigenvalue, frequency, damping, dominant states
   participation_table(dae, mode=1)  # participation factors of one mode
   state_matrix(dae, as_frame=True)  # the linearization, labeled

Plotting
--------

:func:`~hermess.analysis.plot` groups signals by unit into panels;
:func:`~hermess.analysis.plot_states` shows one small panel per state;
:func:`~hermess.analysis.compare` overlays several runs;
:func:`~hermess.analysis.plot_frequency`,
:func:`~hermess.analysis.plot_voltages` and
:func:`~hermess.analysis.plot_active_power` are one-line shortcuts;
:func:`~hermess.analysis.plot_modes` draws the s-plane; and
:func:`~hermess.analysis.mark_events` adds the disturbance times to any axes.
The plots follow the active matplotlib style; pass ``color=`` (or ``colors=``
on :func:`~hermess.analysis.compare` and
:func:`~hermess.analysis.plot_system`) to override.

:func:`~hermess.analysis.plot_system` draws the single-line diagram of the
run: buses joined by their branches, each device with the classic symbol,
colored by category and labeled with its model type. ``color_by="bus*:v"``
colors the buses by a result and turns the diagram into a map.

System files
------------

Text-level conveniences for working on a local copy of a system:

.. code-block:: python

   root = copy_system("3bus_loadstep")   # copy out of the installed package
   show_system(root, "3bus_loadstep")    # print the files, license header stripped
   set_param(root, "3bus_loadstep", "GFMI2", Kp=0.05, angle='"VSM"')
   set_disturbances(root, "3bus_loadstep", [
       'Disturbance, time = 1.0, type = "FAULT_BUS", bus = "2", y = 20',
       'Disturbance, time = 1.1, type = "CLEAR_FAULT_BUS", bus = "2"',
   ])
   read_events(root, "3bus_loadstep")    # [(time, type, where), ...]

A finished run carries the same event list as ``dae.events``, and the resolved
configuration as ``dae.cfg``. To run without terminal output, pass
``quiet=True`` to :func:`hermess.simulate` (no progress bar, warnings-only
logging), or set the ``show_progress`` configuration field directly.

The full reference is in the :ref:`API section <api_analysis>`.
