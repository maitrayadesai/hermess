.. _models:

Dynamic Models
==============

Dynamic models are the components that contribute differential states to the DAE
system. Their classes live in ``hermess/devices``. A model is selected in a
system file by the class name in the first column, for example::

   SynchronousSubtransientSP, idx = "SG1", bus = "1", Sn = 100, ...

The pages below describe what each model represents; the parameters and defaults
of every class are listed in the class documentation itself, which is generated
from the source, so it always matches the installed version.

Machines are composed rather than hard-wired: a synchronous machine takes a
separate automatic voltage regulator, governor, power system stabilizer and shaft
strategy, and a converter takes a filter, angle source, voltage control, inner
control and PLL. Each of those is chosen by keyword in the same line of the
system file (see :ref:`strategies` below and :ref:`advanced_usage`).

To add a model of your own, subclass the corresponding base class and register
it with :func:`hermess.register`, after which it is selectable by name exactly
like a shipped model. See :ref:`user_models`.

Base class
----------

All devices derive from ``Element``; devices that inject current into the network
in rectangular coordinates derive from ``DeviceRect``.

.. autoclass:: hermess.devices.device.DeviceRect
   :no-index:

The method that builds the differential and algebraic equations of a model is:

.. autofunction:: hermess.devices.device.DeviceRect.fgcall()
   :no-index:

Synchronous machines
--------------------

.. _synchronous_generator_transient_model:

Transient (two-axis) model
^^^^^^^^^^^^^^^^^^^^^^^^^^

A two-axis dynamic approximation of a synchronous generator, following [1]_.

.. autoclass:: hermess.devices.synchronous.SynchronousTransient
   :no-index:

.. _synchronous_generator_subtransient_model:

Subtransient model
^^^^^^^^^^^^^^^^^^

A subtransient (Anderson-Fouad) approximation, following [1]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransient
   :no-index:

Sauer-Pai model, with stator dynamics
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Extends the subtransient model with stator flux dynamics, following [3]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP
   :no-index:

Sauer-Pai model, without stator dynamics
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Sauer-Pai formulation with the stator transients neglected, a sixth-order
model [3]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP6
   :no-index:

Explicit-DAE variants
^^^^^^^^^^^^^^^^^^^^^

The same two Sauer-Pai machines with the stator equations kept as algebraic
constraints instead of being eliminated. Useful when the stator algebraic
variables are needed explicitly, for instance together with dynamic line models.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP_DAE
   :no-index:

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP6DAE
   :no-index:

PSS/E-style machines
^^^^^^^^^^^^^^^^^^^^

Round-rotor and salient-pole machines in the PSS/E parameter convention, used by
the 14-generator South East Australian benchmark.

.. autoclass:: hermess.devices.synchronous.GENROU
   :no-index:

.. autoclass:: hermess.devices.synchronous.GENSAL
   :no-index:

Converters
----------

.. _metaclass_converter:

Converter base class
^^^^^^^^^^^^^^^^^^^^

The parent class of all converter models. It introduces the shared parameters and
the initialization procedure, and wires the five pluggable control blocks.

.. autoclass:: hermess.devices.inverter.Inverter
   :members:
   :no-index:

.. _grid_forming_converter:

Grid-forming converter
^^^^^^^^^^^^^^^^^^^^^^

A grid-forming converter, which sets its own frequency and voltage. The
small-signal behavior in low-inertia systems follows [2]_.

.. autoclass:: hermess.devices.inverter.GridForming
   :no-index:

.. _grid_following_converter:

Grid-following converter
^^^^^^^^^^^^^^^^^^^^^^^^

A grid-following converter, which synchronizes to the grid through a PLL [2]_.

.. autoclass:: hermess.devices.inverter.GridFollowing
   :no-index:

Static var compensator
----------------------

.. autoclass:: hermess.devices.svc.SVC
   :no-index:

.. _strategies:

Pluggable control strategies
----------------------------

The blocks below are selected by keyword on the device line of a system file, for
example ``avr = "SEXST"``, ``shaft = "Shaft4Mass"`` or ``angle = "Droop"``. The
names accepted at any moment, shipped and user-registered together, are returned
by :func:`hermess.registered`.

Automatic voltage regulators (``avr = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.avr.SEXST
   :no-index:
.. autoclass:: hermess.devices.avr.IEEEDC1A
   :no-index:
.. autoclass:: hermess.devices.avr.AVRST1A
   :no-index:
.. autoclass:: hermess.devices.avr.AVRAC1A
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_ODE
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_Filter
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_NoTGR
   :no-index:

Governors (``governor = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.governor.GOVCONST
   :no-index:
.. autoclass:: hermess.devices.governor.Droop
   :no-index:
.. autoclass:: hermess.devices.governor.TGOV1
   :no-index:

Power system stabilizers (``pss = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.pss.PSSKundur
   :no-index:
.. autoclass:: hermess.devices.pss.PSSSEA
   :no-index:

Shafts (``shaft = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.shaft.SingleMass
   :no-index:
.. autoclass:: hermess.devices.shaft.Shaft4Mass
   :no-index:
.. autoclass:: hermess.devices.shaft.Shaft5Mass
   :no-index:

Converter output filters (``filter = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.inverter_filter.LCL
   :no-index:
.. autoclass:: hermess.devices.inverter_filter.LCL_static
   :no-index:

Converter angle sources (``angle = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.inverter_angle.DroopAngle
   :no-index:
.. autoclass:: hermess.devices.inverter_angle.PLLAngle
   :no-index:

Converter voltage control (``voltage = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.inverter_voltage.QVDroop
   :no-index:

Converter inner control (``inner = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.inverter_inner.Cascaded
   :no-index:

Phase-locked loops (``pll = ...``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.inverter_pll.SRF_PLL
   :no-index:

.. _user_models:

Adding your own model
---------------------

A model written outside the package becomes selectable from a system file once it
is registered. The kind is inferred from the base class, so one call covers
devices and every strategy axis:

.. code-block:: python

   import hermess
   from hermess.devices.inverter_angle import AngleSource

   class VSMAngle(AngleSource):
       """Virtual synchronous machine angle dynamics."""
       ...

   hermess.register(VSMAngle, "VSM")   # now:  angle = "VSM"  in sim_param.txt
   hermess.registered("angle")         # ['Droop', 'PLL', 'VSM']

A registered *device* is addressed by its class name in the first column of the
system file; a registered *strategy* by the name given to
:func:`hermess.register`. Registering the same name again replaces the earlier
entry, which is convenient while iterating in a notebook, and
:func:`hermess.unregister` removes one again.

References
----------

.. [1] Federico Milano, *Power System Modelling and Scripting*, Springer Berlin Heidelberg, 2010, Power Systems series. Available at: https://books.google.ch/books?id=MQu7IqoLrfYC.

.. [2] U. Markovic, O. Stanojev, P. Aristidou, E. Vrettos, D. Callaway, and G. Hug, *Understanding Small-Signal Stability of Low-Inertia Systems*, IEEE Transactions on Power Systems, vol. 36, no. 5, pp. 3997-4017, Sep. 2021, doi: 10.1109/TPWRS.2021.3061434.

.. [3] P. W. Sauer and M. A. Pai, *Power System Dynamics and Stability*, University of Illinois at Urbana-Champaign, 1998.
