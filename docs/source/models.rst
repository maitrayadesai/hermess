.. _models:

Dynamic Models
==============

Everything dynamic in HERMESS is implemented in a **pluggable-strategy**
manner. A device class implements the physical core of a component and is
selected in a system file by its class name in the first column: for a
synchronous machine that core is the electromagnetic model, for a converter it
is the power path through the output filter. The controllers are separate
*strategy* objects plugged onto that core and chosen by keyword on the same
line of the system file::

   SynchronousSubtransientSP, idx = "SG1", bus = "1", Sn = 300, avr = "SEXST", governor = "TGOV1", ...
   GridForming, idx = "GFM1", bus = "3", Sn = 100, filter = "LCL_static", ...

Machines take an automatic voltage regulator, a governor, a power system
stabilizer and a shaft; converters take an output filter, an angle source, a
voltage controller, an inner controller and a PLL. Every combination composes,
the names accepted at any moment (shipped and user-registered together) are
returned by :func:`hermess.registered`, and a model of your own becomes
selectable once registered with :func:`hermess.register` (see
:ref:`user_models`).

The sections below describe what each model represents; the parameters and
defaults of every class are listed in the class documentation itself, which is
generated from the source, so it always matches the installed version. Each
class documents its equations exactly as implemented and a table mapping the
code parameter names to the mathematical symbols used in those equations.

Base class
----------

All devices derive from ``Element``; devices that inject current into the
network in rectangular coordinates derive from ``DeviceRect``.

.. autoclass:: hermess.devices.device.DeviceRect
   :no-index:

The method that builds the differential and algebraic equations of a model is:

.. autofunction:: hermess.devices.device.DeviceRect.fgcall()
   :no-index:

Synchronous machines
--------------------

A synchronous machine is specified with the **electromagnetic model as the
machine class**, and the various controller strategies are plugged onto it.
The electromagnetic model exchanges the air-gap power :math:`P_e` and the
rotor motion :math:`\delta, \omega` with the shaft strategy, reads the field
voltage :math:`E_{fd}` from the AVR strategy (which sums the stabilizing
signal :math:`V_s` of the PSS strategy into its voltage error) and the
mechanical power :math:`p_m` from the governor strategy, and injects its
stator current into the network:

.. figure:: /_static/schematics/sm_composition.svg
   :alt: Synchronous machine composition
   :width: 560px

   How a machine is composed: the machine class implements the
   electromagnetic model; shaft, governor, AVR and PSS are pluggable
   strategies selected by keyword on the machine line.

Machine models
^^^^^^^^^^^^^^

.. _synchronous_generator_transient_model:

Transient (two-axis) model
""""""""""""""""""""""""""

A two-axis dynamic approximation of a synchronous generator, following [1]_.

.. autoclass:: hermess.devices.synchronous.SynchronousTransient
   :no-index:

.. _synchronous_generator_subtransient_model:

Subtransient model
""""""""""""""""""

A subtransient (Anderson-Fouad) approximation, following [1]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransient
   :no-index:

Sauer-Pai model, with stator dynamics
"""""""""""""""""""""""""""""""""""""

Extends the subtransient model with stator flux dynamics, following [3]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP
   :no-index:

Sauer-Pai model, without stator dynamics
""""""""""""""""""""""""""""""""""""""""

The Sauer-Pai formulation with the stator transients neglected, a sixth-order
model [3]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP6
   :no-index:

Explicit-DAE variants
"""""""""""""""""""""

The same two Sauer-Pai machines with the stator equations kept as algebraic
constraints instead of being eliminated. Useful when the stator algebraic
variables are needed explicitly, for instance together with dynamic line
models.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP_DAE
   :no-index:

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP6DAE
   :no-index:

PSS/E-style machines
""""""""""""""""""""

Round-rotor and salient-pole machines in the PSS/E parameter convention, used
by the 14-generator South East Australian benchmark.

.. autoclass:: hermess.devices.synchronous.GENROU
   :no-index:

.. autoclass:: hermess.devices.synchronous.GENSAL
   :no-index:

Marconato model
"""""""""""""""

The Milano/Marconato six-state machine with stator flux dynamics, the
counterpart of the PSID ``MarconatoMachine`` used by the PSCAD-benchmarked
multi-machine case.

.. autoclass:: hermess.devices.synchronous.Marconato
   :no-index:

.. _strategies:

Machine controller strategies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The controllers plugged onto a machine, selected by keyword on the machine
line, for example ``avr = "SEXST"``, ``governor = "TGOV1"``,
``pss = "PSSKundur"``, ``shaft = "Shaft4Mass"``.

Automatic voltage regulators (``avr = ...``)
""""""""""""""""""""""""""""""""""""""""""""

.. figure:: /_static/schematics/avr_sexst.svg
   :alt: SEXST block diagram
   :width: 380px

   SEXST: first-order static exciter.

.. autoclass:: hermess.devices.avr.SEXST
   :no-index:

.. figure:: /_static/schematics/avr_ieeedc1a.svg
   :alt: IEEE DC1A block diagram
   :width: 480px

   IEEE DC1A: regulator, rotating exciter and stabilizing rate feedback.

.. autoclass:: hermess.devices.avr.IEEEDC1A
   :no-index:

.. figure:: /_static/schematics/avr_st1a.svg
   :alt: ST1A block diagram
   :width: 560px

   IEEE ST1A: transducer, two lead-lags and the regulator lag.

.. autoclass:: hermess.devices.avr.AVRST1A
   :no-index:

.. figure:: /_static/schematics/avr_ac1a.svg
   :alt: AC1A block diagram
   :width: 480px

   IEEE AC1A: regulator, rotating exciter and washout rate feedback.

.. autoclass:: hermess.devices.avr.AVRAC1A
   :no-index:

.. figure:: /_static/schematics/avr_kundur.svg
   :alt: Kundur AVR family block diagram
   :width: 520px

   The Kundur two-area AVR family: transducer, gain and
   transient-gain-reduction lead-lag, in four realizations.

.. autoclass:: hermess.devices.avr.AVRKundur
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_ODE
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_Filter
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_NoTGR
   :no-index:

Two minimal exciters close the family, useful as limiting cases and for
matching references without excitation dynamics. ``AVRCONST`` holds the
field voltage constant at its operating point, and ``AVRSimple`` integrates
the voltage error, :math:`\dot{E}_{fd} = K_v \left( V_{ref} - V_t \right)`.

.. autoclass:: hermess.devices.avr.AVRCONST
   :no-index:
.. autoclass:: hermess.devices.avr.AVRSimple
   :no-index:

Governors (``governor = ...``)
""""""""""""""""""""""""""""""

.. figure:: /_static/schematics/gov_tgov1.svg
   :alt: TGOV1 block diagram
   :width: 470px

   TGOV1: droop, servo and reheater lags (``GOVCONST`` holds :math:`p_m`
   constant; ``Droop`` keeps only the droop).

.. autoclass:: hermess.devices.governor.GOVCONST
   :no-index:
.. autoclass:: hermess.devices.governor.Droop
   :no-index:
.. autoclass:: hermess.devices.governor.TGOV1
   :no-index:

.. figure:: /_static/schematics/gov_tgtype2.svg
   :alt: Type II governor block diagram
   :width: 420px

   Type II governor: the frequency deviation acts through the droop and one
   lead-lag, added to the constant reference power.

.. autoclass:: hermess.devices.governor.TGTypeII
   :no-index:

Power system stabilizers (``pss = ...``)
""""""""""""""""""""""""""""""""""""""""

.. figure:: /_static/schematics/pss.svg
   :alt: PSS block diagram
   :width: 520px

   Speed-input stabilizer: gain, washout and lead-lag stages.

.. autoclass:: hermess.devices.pss.PSSKundur
   :no-index:
.. autoclass:: hermess.devices.pss.PSSSEA
   :no-index:

Shafts (``shaft = ...``)
""""""""""""""""""""""""

.. figure:: /_static/schematics/shaft_chain.svg
   :alt: Multi-mass shaft
   :width: 620px

   The torsional shaft as a chain of rotor masses coupled by stiffness
   :math:`K_{ij}`; the single-mass default keeps only the GEN mass.

.. autoclass:: hermess.devices.shaft.SingleMass
   :no-index:
.. autoclass:: hermess.devices.shaft.Shaft4Mass
   :no-index:
.. autoclass:: hermess.devices.shaft.Shaft5Mass
   :no-index:

Converters
----------

A converter is composed in exactly the same manner: the **converter class
implements the power path** (the voltage-source converter behind its LCL
output filter), and the control blocks are pluggable strategies on five
axes, the output filter, the angle source, the voltage control, the inner
control and the PLL. Three converter classes ship, differing in how they
synchronize and in which strategies they plug in by default.
:class:`~hermess.devices.inverter.GridForming` sets its own frequency and
voltage from an active-power droop.
:class:`~hermess.devices.inverter.GridSupporting` rides on a PLL and adds
the droop on the PLL frequency, keeping the full voltage-mode cascade.
:class:`~hermess.devices.inverter.GridFollowing` also rides on a PLL but
replaces that cascade by a current-injecting chain of power-PI and
current-PI controllers.

In the voltage-mode chain of the grid-forming and grid-supporting
converters, the filter strategy carries the plant states
:math:`v_f, i_f, i_t`; the angle source sets the converter frequency
:math:`\omega_c` and angle :math:`\delta_c` (from the active-power droop
for a grid-forming unit, from the PLL for a grid-supporting unit); the
voltage controller turns the reactive-power error into the voltage command
:math:`V_{cd}`; the inner controller closes the cascaded voltage and
current loops and produces the switching voltage :math:`v_{sw}^{*}`; and
the PLL tracks the filter-voltage phasor:

.. figure:: /_static/schematics/conv_structure.svg
   :alt: Converter composition, voltage-mode chain
   :width: 560px

   How a grid-forming or grid-supporting converter is composed: the
   converter class implements the power path; filter, angle source, voltage
   control, inner control and PLL are pluggable strategies selected by
   keyword on the converter line.

In the current-injecting chain of the grid-following converter, the
converter frame is the PLL frame itself. PI controllers on the filtered
active and reactive power occupy the angle and voltage slots and produce
the dq current commands, and a current-mode inner loop tracks them on the
same LCL filter:

.. figure:: /_static/schematics/conv_gfl.svg
   :alt: Converter composition, current-injecting chain
   :width: 560px

   How a grid-following converter is composed: the same power path, with
   the power-PI outers and the current-mode inner loop in the strategy
   slots and the PLL fixing the converter frame.

Converter models
^^^^^^^^^^^^^^^^

.. _metaclass_converter:

Converter base class
""""""""""""""""""""

The parent class of all converter models. It introduces the shared parameters
and the initialization procedure, and wires the five pluggable control blocks.

.. autoclass:: hermess.devices.inverter.Inverter
   :members:
   :no-index:

.. _grid_forming_converter:

Grid-forming converter
""""""""""""""""""""""

A grid-forming converter, which sets its own frequency and voltage. The
small-signal behavior in low-inertia systems follows [2]_.

.. autoclass:: hermess.devices.inverter.GridForming
   :no-index:

.. _grid_supporting_converter:

Grid-supporting converter
"""""""""""""""""""""""""

A grid-supporting converter, which synchronizes to the grid through a PLL
and adds the active-power droop on the PLL frequency, keeping the full
voltage-mode cascade [2]_. The class was named ``GridFollowing`` before
v1.1, when that name moved to the current-injecting chain below.

.. autoclass:: hermess.devices.inverter.GridSupporting
   :no-index:

.. _grid_following_converter:

Grid-following converter
""""""""""""""""""""""""

A grid-following converter in the literature-standard current-injecting
form, matching the PowerSimulationsDynamics.jl reference model and its
PSCAD benchmarks: the frame rides on the PLL, power-PI outers produce the
current commands and a current-mode inner loop tracks them.

.. autoclass:: hermess.devices.inverter.GridFollowing
   :no-index:

Converter control strategies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The blocks plugged onto a converter, selected by keyword on the converter
line, for example ``filter = "LCL_static"``, ``angle = "Droop"``,
``pll = "SRF_PLL"``.

Output filters (``filter = ...``)
"""""""""""""""""""""""""""""""""

.. figure:: /_static/schematics/lcl.svg
   :alt: LCL filter circuit
   :width: 520px

   The LCL output filter between the switching voltage and the bus.

.. autoclass:: hermess.devices.inverter_filter.LCL
   :no-index:
.. autoclass:: hermess.devices.inverter_filter.LCL_static
   :no-index:

Angle sources (``angle = ...``)
"""""""""""""""""""""""""""""""

The angle source fixes how the converter synchronizes. ``Droop`` is the
grid-forming active-power droop, and ``PLL`` adds the same droop on the
PLL frequency for a grid-supporting unit. ``VSM`` is a
virtual-synchronous-machine swing with virtual inertia, damped against the
PLL frequency. ``PLLPowerPI`` is the grid-following choice, which aliases
the converter frame to the PLL frame and turns the active-power error into
the d-axis current command.

.. autoclass:: hermess.devices.inverter_angle.DroopAngle
   :no-index:
.. autoclass:: hermess.devices.inverter_angle.PLLAngle
   :no-index:
.. autoclass:: hermess.devices.inverter_angle.VSMAngle
   :no-index:
.. autoclass:: hermess.devices.inverter_angle.PLLPowerPI
   :no-index:

Voltage control (``voltage = ...``)
"""""""""""""""""""""""""""""""""""

``QVDroop`` turns the reactive-power error into the voltage-magnitude
command of the voltage-mode cascade. ``QPowerPI`` replaces it in the
current-injecting chain and produces the q-axis current command instead.

.. autoclass:: hermess.devices.inverter_voltage.QVDroop
   :no-index:
.. autoclass:: hermess.devices.inverter_voltage.QPowerPI
   :no-index:

Inner control (``inner = ...``)
"""""""""""""""""""""""""""""""

``Cascaded`` closes the voltage and current loops of the voltage-mode
cascade, and ``CascadedDamped`` adds capacitor-voltage active damping on
top of it. ``CurrentPI`` is the current-mode loop of the grid-following
chain, tracking the commands of the power PIs directly.

.. autoclass:: hermess.devices.inverter_inner.Cascaded
   :no-index:
.. autoclass:: hermess.devices.inverter_inner.CascadedDamped
   :no-index:
.. autoclass:: hermess.devices.inverter_inner.CurrentPI
   :no-index:

Phase-locked loops (``pll = ...``)
""""""""""""""""""""""""""""""""""

.. figure:: /_static/schematics/pll_srf.svg
   :alt: SRF-PLL block diagram
   :width: 520px

   Synchronous-reference-frame PLL: the q-component of the filter voltage is
   driven to zero, locking :math:`\delta_{pll}` to the filter-voltage phasor.

``SRF_PLL`` is the synchronous-reference-frame loop of the figure.
``ReducedPLL`` low-pass filters the measured q-voltage before the loop, and
``Kaura`` filters both axes and acts on the phase angle of the filtered
phasor.

.. autoclass:: hermess.devices.inverter_pll.SRF_PLL
   :no-index:
.. autoclass:: hermess.devices.inverter_pll.ReducedPLL
   :no-index:
.. autoclass:: hermess.devices.inverter_pll.KauraPLL
   :no-index:

Static var compensator
----------------------

.. figure:: /_static/schematics/svc.svg
   :alt: SVC block diagram
   :width: 470px

   The SVC voltage regulator: integrator with reactive droop; the susceptance
   :math:`B` is injected as a shunt at the bus.

.. autoclass:: hermess.devices.svc.SVC
   :no-index:

.. _user_models:

Adding your own model
---------------------

A model written outside the package becomes selectable from a system file once
it is registered. The kind is inferred from the base class, so one call covers
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
:func:`hermess.register`. Registering the same name twice replaces the earlier
entry, which is convenient while iterating on a model in a notebook, and
:func:`hermess.unregister` removes one again.

References
----------

.. [1] Federico Milano, *Power System Modelling and Scripting*, Springer Berlin Heidelberg, 2010, Power Systems series. Available at: https://books.google.ch/books?id=MQu7IqoLrfYC.

.. [2] U\. Markovic, O. Stanojev, P. Aristidou, E. Vrettos, D. Callaway, and G. Hug, *Understanding Small-Signal Stability of Low-Inertia Systems*, IEEE Transactions on Power Systems, vol. 36, no. 5, pp. 3997-4017, Sep. 2021, doi: 10.1109/TPWRS.2021.3061434.

.. [3] P\. W. Sauer and M. A. Pai, *Power System Dynamics and Stability*, University of Illinois at Urbana-Champaign, 1998.
