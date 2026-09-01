.. _advanced_usage:

System files
============

Every system is fully defined by two text files in its own folder under
``hermess/systems/``:

- ``hermess/systems/<case>/sim_param.txt`` — the network, the devices connected
  to it, and the initialization data used to solve the power flow.
- ``hermess/systems/<case>/sim_dist.txt`` — the disturbances applied during the
  time-domain simulation; see :ref:`disturbances`.

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

.. note::

   With ``line_dyn=True`` the line charging ``b`` doubles as the bus
   capacitance of the dynamic network, so every bus needs at least one
   connected branch with ``b > 0``. System files written for quasi-static
   (RMS) studies often set ``b = 0``; such a file runs only with
   ``line_dyn=False``, and the setup rejects it otherwise, naming the buses
   without shunt susceptance.

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

Per-system defaults: ``sim_settings.txt``
-----------------------------------------

A system folder may carry an optional third file, ``sim_settings.txt``, with
the configuration defaults the system needs to run out of the box, one
``field = value`` per line (``#`` comments allowed, values in JSON, fields
from :class:`~hermess.config.Config`):

::

   # Buses of this network carry no shunt susceptance (no line charging b),
   # so it cannot run as a dynamic network; simulate it quasi-static.
   line_dyn = false

:func:`hermess.simulate` (and therefore the command line) applies these
between the package defaults and your own arguments, so anything you pass
explicitly still wins. Building a :class:`~hermess.config.Config` manually
for :func:`hermess.run.run` bypasses the file and keeps full manual control.
Several shipped networks, among them ``kundur``, ``ieee39`` and the South
East Australian family, use it to default to the quasi-static network,
because their transformer branches carry no charging susceptance and the
dynamic network needs a capacitance at every bus.

Limitations
-----------

- Only one injector is allowed per bus, because the initialization would
  otherwise be ambiguous: initialization overwrites production and consumption
  values so that the system starts in steady state. To place a second component
  at the same location, add a bus connected through a branch of very small
  impedance.
