.. _advanced_usage:

Advanced Usage
==============

Every system is fully defined by two text files in its own folder under
``hermess/systems/``:

- ``hermess/systems/<case>/sim_param.txt`` — the network, the devices connected
  to it, and the initialization data used to solve the power flow.
- ``hermess/systems/<case>/sim_dist.txt`` — the disturbances applied during the
  time-domain simulation.

Together they specify everything the simulator needs. To work on a system of your
own, copy a folder, edit it, and point the simulator at its parent directory with
``system_root``:

.. code-block:: python

   import hermess

   dae = hermess.simulate("my_case", system_root="~/my_systems", T_end=10.0)
   hermess.list_systems("~/my_systems")

Lines beginning with ``#`` are comments, and a device entry may be wrapped over
several lines by indenting the continuation.

.. _sim_param:

Simulation parameters
---------------------

**File:** ``hermess/systems/<case>/sim_param.txt``

.. _grid_param:

1) Grid topology and parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   Line, bus_i = "1", bus_j = "2", r = 0.01, x = 0.08, g = 0.001, b = 0.03, trafo = 1

Every branch of the grid is listed this way. The values are per unit on the
system base, so resistance, reactance, conductance and susceptance are given in
per unit and no separate transformer model is needed: the ``trafo`` field holds
the off-nominal tap ratio of that branch, ideally close to 1.0. See
:ref:`models_static_line` for the parameter list.

.. _dyn_param:

2) Dynamic models
^^^^^^^^^^^^^^^^^

::

   SynchronousSubtransientSP, idx = "SG1", bus = "1", Sn = 300, H = 6.5, x_d = 1.8, ...

The first field is the class name of the model; ``bus`` is mandatory. Parameters
that are omitted fall back to the defaults declared in the corresponding Python
class, which are listed in :ref:`models`.

Machines and converters are composed from pluggable strategies, selected by
keyword on the same line:

::

   GENROU, idx = "BPS_2", bus = "201", avr = "AVRST1A", governor = "GOVCONST", pss = "PSSSEA"
   GridForming, idx = "GFM1", bus = "3", filter = "LCL_static", Kp = 0.01, ...

The available keywords are:

- ``avr`` — automatic voltage regulator.
- ``governor`` — turbine-governor.
- ``pss`` — power system stabilizer.
- ``shaft`` — single or multi-mass shaft.
- ``filter``, ``angle``, ``voltage``, ``inner``, ``pll`` — the five converter
  control blocks.

The names accepted at any moment, shipped and user-registered together, are
returned by :func:`hermess.registered`:

.. code-block:: python

   hermess.registered()          # every axis
   hermess.registered("avr")     # just the voltage regulators

Models of your own become selectable the same way once registered with
:func:`hermess.register`; see :ref:`user_models`.

.. _static_param:

3) Static models
^^^^^^^^^^^^^^^^

::

   StaticZIP, bus = "2", z_share = 1.0

The bus is mandatory. Active and reactive power may be given but are overwritten
during initialization by the values that make t = 0 s a steady state. The
available static models are listed in :ref:`models_static`.

4) Initialization data
^^^^^^^^^^^^^^^^^^^^^^

The simulation is initialized by a power flow, whose input is given in the same
file with the ``BusInit`` keyword. Every bus is specified separately, and there
must be exactly one slack bus.

::

   BusInit, bus = "1", p = 0,   v = 1.0, type = "slack"
   BusInit, bus = "3", p = -50, v = 1.0, type = "PV"
   BusInit, bus = "2", p = 100, q = 10,  type = "PQ"

**Parameters:**

- **bus** (*str*) – Name of the bus.
- **p** (*float*) – Injected active power in MW. Positive corresponds to consumption.
- **q** (*float*) – Injected reactive power in MVAr. Positive corresponds to consumption.
- **v** (*float*) – Bus voltage magnitude in per unit.
- **type** (*str*) – One of ``"PQ"``, ``"PV"`` or ``"slack"``.

Simulation disturbances
-----------------------

**File:** ``hermess/systems/<case>/sim_dist.txt``

Each line schedules one event:

::

   Disturbance, time = 7.0,  type = "FAULT_LINE", bus_i = "1", bus_j = "2", y = 30
   Disturbance, time = 7.04, type = "OPEN_LINE",  bus_i = "1", bus_j = "2"

The supported types are:

**FAULT_LINE** — a three-phase short circuit in the middle of a line. The
specified admittance is added between ground and the middle of the line by
converting the T model of the line to a PI model.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"FAULT_LINE"``.
- **bus_i** (*str*) – Name of the sending-end bus.
- **bus_j** (*str*) – Name of the receiving-end bus.
- **y** (*float*) – Fault admittance in per unit.

**CLEAR_FAULT_LINE** — removes a short circuit on a line.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"CLEAR_FAULT_LINE"``.
- **bus_i** (*str*) – Name of the sending-end bus.
- **bus_j** (*str*) – Name of the receiving-end bus.

**FAULT_BUS** — a three-phase short circuit at a bus. The specified admittance is
added to the shunt element of that bus.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"FAULT_BUS"``.
- **bus** (*str*) – Name of the affected bus.
- **y** (*float*) – Fault admittance in per unit.

**CLEAR_FAULT_BUS** — removes a short circuit at a bus.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"CLEAR_FAULT_BUS"``.
- **bus** (*str*) – Name of the bus.

**OPEN_LINE** — opens a line. If the line carried a fault, the fault is thereby
neutralized.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"OPEN_LINE"``.
- **bus_i** (*str*) – Name of the sending-end bus.
- **bus_j** (*str*) – Name of the receiving-end bus.

**LOAD** — a load change at a bus. The active and reactive power given are added
to the consumption, in the same units as ``Sb`` (MW and MVAr by default).

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"LOAD"``.
- **bus** (*str*) – Name of the affected bus.
- **p_delta** (*float*) – Active power change in MW.
- **q_delta** (*float*) – Reactive power change in MVAr.

The shipped systems in :ref:`test_cases` are worked examples of both files, and
the notebooks under ``examples/`` walk through them step by step.

.. note::

   Give ``T_end`` at least one time step beyond the last disturbance. A segment
   shorter than one output step has nothing to integrate, and the simulator stops
   at the last disturbance rather than producing an empty result.

Reading the results
-------------------

:func:`hermess.simulate` returns the finished
:class:`~hermess.system.DaeSim`, which holds both the symbolic model and the
trajectories:

.. code-block:: python

   dae = hermess.simulate("3bus", T_end=5.0, small_signal_analysis=True)

   dae.time_steps                       # the time grid
   dae.x_full, dae.y_full               # differential and algebraic trajectories
   dae.grid.yf                          # bus voltages
   dae.A                                # reduced state matrix at the operating point
   dae.eigenvalues                      # spectrum of dae.A
   dae.participation_table(mode=1)      # participation factors of one mode
   dae.print_modal_report()             # the same as a text report
   dae.grid.power_flow_tables(dae)      # initial power flow as two DataFrames

Individual devices keep their own states, so ``device.xf["omega"]`` gives the
trajectory of one state of one device.

Limitations
-----------

- Only one injector is allowed per bus, because the initialization would
  otherwise be ambiguous: initialization overwrites production and consumption
  values so that the system starts in steady state. To place a second component
  at the same location, add a bus connected through a branch of very small
  impedance.
