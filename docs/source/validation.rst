.. _validation:

Validation
==========

Most of the test suite pins HERMESS against its own past output, which catches
regressions but cannot catch a model that has been wrong from the start. The
cases on this page pin the shipped dynamic models against implementations that
are not ours: an independently developed simulator, or published benchmark
tables. Each case is asserted in CI on every run.

Cross-tool cases against ANDES
------------------------------

`ANDES <https://github.com/CURENT/andes>`_ is an open-source power system
simulator that is itself validated against PSS/E and DSATools TSAT. For each
model below, a small three-bus system is built identically in HERMESS and in
ANDES, disturbed by the loss of a line at t = 1 s, and compared on three
levels, in increasing order of strength:

1. the initialized operating point (every state, setpoint and power-flow
   voltage both tools expose),
2. the eigenvalues of the linearization at that point, matched pairwise, and
3. the disturbed trajectory over 10 s (infinity norm per quantity: rotor
   speeds, all bus voltage magnitudes, machine active and reactive power, and
   the governor states where present).

The reference data, the scripts that generated it, and the tolerances live in
``hermess/tests/references/`` and are asserted by
``hermess/tests/test_reference_traces.py``; the systems themselves ship as
:ref:`3bus_genrou <3bus_genrou>`, :ref:`3bus_gensal <3bus_gensal>`,
:ref:`3bus_tgov1 <3bus_tgov1>`, :ref:`3bus_sexst <3bus_sexst>`,
:ref:`3bus_avrst1a <3bus_avrst1a>`, :ref:`3bus_ieeedc1a <3bus_ieeedc1a>`,
:ref:`3bus_avrac1a <3bus_avrac1a>` and
:ref:`3bus_psskundur <3bus_psskundur>`. The table reports the worst error
actually achieved (ANDES 2.0.0, August 2026), not the test tolerance, which
is set a factor 10 to 50 above it.

.. list-table::
   :header-rows: 1
   :widths: 14 22 20 11 11 11

   * - Model
     - Compared against
     - Disturbance
     - Operating point
     - Eigenvalues
     - Trajectory
   * - :class:`~hermess.devices.synchronous.GENROU`
     - ANDES ``GENROU``
     - line trip, 10 s
     - 1.8e-7
     - 3.0e-7
     - 3.7e-5
   * - :class:`~hermess.devices.synchronous.GENSAL`
     - ANDES ``GENROU`` reduced to GENSAL (see below)
     - line trip, 10 s
     - 1.4e-7
     - 4.3e-7
     - 2.9e-5
   * - :class:`~hermess.devices.governor.TGOV1`
     - ANDES ``TGOV1`` (lead-lag disabled)
     - line trip, 10 s
     - 1.8e-7
     - 3.0e-7
     - 3.7e-5
   * - :class:`~hermess.devices.avr.SEXST`
     - ANDES ``SEXS`` (lead-lag disabled)
     - line trip, 10 s
     - 1.8e-7
     - 1.3e-5
     - 1.8e-4
   * - :class:`~hermess.devices.avr.AVRST1A`
     - ANDES ``EXST1`` (rate feedback removed)
     - line trip, 10 s
     - 1.8e-7
     - 3.7e-7
     - 4.9e-4
   * - :class:`~hermess.devices.avr.IEEEDC1A`
     - ANDES ``IEEET1`` (transducer removed)
     - line trip, 10 s
     - 1.8e-7
     - 3.0e-7
     - 4.6e-5
   * - :class:`~hermess.devices.avr.AVRAC1A`
     - ANDES ``IEEET1`` (transducer removed)
     - line trip, 10 s
     - 1.8e-7
     - 1.1e-6
     - 5.5e-4
   * - :class:`~hermess.devices.pss.PSSKundur`
     - ANDES ``ST2CUT`` (transducer lag removed)
     - line trip, 10 s
     - 1.8e-7
     - 1.7e-5
     - 2.1e-4

Operating point and trajectory entries are the worst absolute error over all
compared quantities in per unit (radians for angles); the eigenvalue entry is
the worst distance between paired eigenvalues in rad/s. Rotor speeds agree to
about 2e-7 p.u. throughout the disturbed trajectory in every case; the worst
trajectory column is the fastest-moving quantity (reactive power, or the
field voltage in the exciter cases), which also carries the interpolation
error of the reference grid. Errors of this size mean the two
implementations are the same model to within integration accuracy, not
merely similar models.

What the cases hold fixed
-------------------------

A cross-tool comparison is meaningful only when both runs solve the same
physics. The cases fix, on both sides: a quasi-static network
(``line_dyn=False``, matching the ANDES phasor model), the nominal
synchronous reference frame (``omega_mode="nom"``), all limiters inactive,
saturation disabled, one per-unit base (Sn = Sb = 100 MVA) and the same
output grid. Excitation and turbine dynamics are excluded through the
constant strategies :class:`~hermess.devices.avr.AVRCONST` and
:class:`~hermess.devices.governor.GOVCONST`, which is exactly what ANDES does
with a machine that has no exciter or governor attached.

Where the two tools do not ship the same block diagram, the ANDES model is
reduced exactly to ours, and the reduction is documented in the case's
``generate.py`` rather than absorbed into a looser tolerance:

- ANDES ships no GENSAL. Its GENROU with ``xq1 = xq`` reduces exactly to the
  GENSAL equations (the q-axis transient voltage stays identically zero and
  the remaining q-axis state maps onto :math:`\psi''_q`); the two eigenvalues
  of the decoupled state are dropped from the comparison.
- The ANDES TGOV1 covers ours with its lead-lag disabled (``T2 = 0``), which
  turns it into the same droop, valve lag and steam-chest lag chain.
- The ANDES SEXS with ``TATB = 1`` reduces to the single-lag SEXST; the
  then-decoupled lead-lag state is dropped from the eigenvalue comparison.
- The ANDES EXST1 with its rate feedback removed (``KF = 0``) is the
  AVRST1A chain (transducer, lead-lag, regulator lag); each side keeps one
  decoupled state, both placed at the same pole so their eigenvalues pair
  with each other.
- The ANDES IEEET1 with its transducer removed (``TR = 0``, which ANDES
  turns into an algebraic pass-through and excludes from its eigenvalue
  analysis) is exactly the IEEEDC1A chain; its saturation is inert at the
  defaults. The AVRAC1A, which in its small-signal form (no saturation,
  ``KC = KD = 0``) coincides with that same chain, is validated against the
  identical reduction at its own parameter regime.
- The ANDES ST2CUT with its transducer lag removed (``T1 = 0``), the second
  input channel silenced and the spare third lead-lag made unity is the
  PSSKundur block for block and in the same order; the silenced and unity
  blocks contribute unmatched reference modes at documented poles.

Against PSS/E reference trajectories
------------------------------------

A second reference family compares against trajectories produced by PSS/E,
the industry reference tool. The data is the benchmark set committed by the
`PowerSimulationsDynamics.jl
<https://github.com/Sienna-Platform/PowerSimulationsDynamics.jl>`_ project
(BSD-3, generated by driving PSS/E through its Python API and used there to
validate its own models); hermess transcribes the published ``.raw``/``.dyr``
system exactly and compares against the published channel output. These
references pin only the rotor-angle trajectory, so the assertion is weaker
per case than the ANDES three-level checks, but the source is the tool a
reader is most likely to trust. The system ships as
:ref:`3bus_genrou_psse <3bus_genrou_psse>`.

.. list-table::
   :header-rows: 1
   :widths: 14 30 20 13 13

   * - Model
     - Case
     - Disturbance
     - Initial angle
     - Trajectory
   * - :class:`~hermess.devices.synchronous.GENROU`
     - ThreeBusMulti (60 Hz), no saturation, infinite bus
     - line trip, 20 s
     - 2.5e-8 rad
     - 8.4e-4 rad

For scale, the upstream project's own acceptance against the same data is
0.1 rad. The remaining upstream PSS/E references embed features hermess
deliberately omits today (machine saturation, the TGOV1 lead-lag, exciter
input lags); ``hermess/tests/references/psse/README.md`` records, per case,
exactly which feature would unlock it.

Against PowerSimulationsDynamics.jl
-----------------------------------

The third reference family compares against `PowerSimulationsDynamics.jl
<https://github.com/Sienna-Platform/PowerSimulationsDynamics.jl>`_ (PSID),
the Julia simulator whose converter carries the same six-state LCL filter as
ours and which is itself benchmarked against PSCAD. These references are
generated locally by running PSID from a pinned Julia environment; each case
folder in ``hermess/tests/references/psid/`` carries the ``generate.jl`` that
produced it. This family covers the part of the model space where hermess
claims to be interesting and a reader has the least reason to trust it: the
grid-forming converter, the Sauer-Pai machine, the multi-mass torsional
shaft, and the dynamic network.

.. list-table::
   :header-rows: 1
   :widths: 16 26 16 11 11 11

   * - Model
     - Compared against
     - Disturbance
     - Operating point
     - Eigenvalues
     - Trajectory
   * - :class:`~hermess.devices.inverter.GridForming`
     - PSID droop + VoltageModeControl + LCL (``kad = 0``)
     - load step, 8 s
     - 3e-6
     - 1.7e-6
     - 2.0e-5
   * - :class:`~hermess.devices.synchronous.SynchronousSubtransientSP`
     - PSID ``SauerPaiMachine``
     - load step, 8 s
     - 2.8e-7
     - 8.1e-7
     - 7.8e-5
   * - :class:`~hermess.devices.shaft.Shaft5Mass`
     - PSID ``FiveMassShaft``
     - load step, 8 s
     - 2.8e-7
     - 8.9e-7
     - 1.6e-4
   * - dynamic lines (``line_dyn``)
     - PSID ``DynamicBranch`` network
     - load step, 8 s
     - 1.0e-7
     - 1.6e-7
     - 2.5e-5

All thirteen states of the grid-forming converter (filter, droop, and every
PI integrator) compare directly: the two tools' internal dq frames turn out
to coincide, so this is a state-by-state identity, not a terminal-quantity
match. The dynamic-lines case pins the network itself: every line current
and every bus voltage is a differential state on both sides. The reductions
are documented in the case folders: PSID's active damping off (``kad = 0``,
two inert reference states), one shared power-filter frequency, PSID's
five-mass shaft as our ``F_hp = 1``, and constant-frame rotation
(``ConstantFrequency``) matching ``omega_mode = "nom"``.

One model has no PSID counterpart and awaits a different reference tool:
``GridSupporting``, the PLL-anchored droop with the voltage-mode cascade
(named ``GridFollowing`` before v1.1); in PSID the frequency-anchor choice
is welded to the actuation type. One measurement finding from building this
family: the PowerSystems.jl PSS/E parser ignores the frequency in the raw
header and defaults to 60 Hz, which barely moved the trajectories of a
mildly disturbed machine while shifting every oscillatory eigenvalue by the
base-frequency ratio — caught by the eigenvalue level of the comparison,
and the reason the suite checks spectra rather than trajectories alone.

Against PSCAD electromagnetic trajectories
------------------------------------------

The fourth family is the strongest evidence in the suite: comparison
against PSCAD, a full electromagnetic-transients simulator, on the four
benchmark systems whose PSCAD runs the PSID project publishes. Enabling
them drove the v1.1 model additions: the active-damped inner control, the
virtual-synchronous-machine angle source with the Kaura PLL, the
literature-standard current-injecting :class:`~hermess.devices.inverter.GridFollowing`
chain, the :class:`~hermess.devices.synchronous.Marconato` machine with
:class:`~hermess.devices.avr.AVRSimple` and
:class:`~hermess.devices.governor.TGTypeII`, and the ``SETPOINT``
reference-step disturbance. Each case in ``hermess/tests/references/pscad/``
carries two references for the same system: a locally generated PSID
reference giving the full three-level check (initial states and eigenvalues
agree to about 1e-9 for the inverter cases), and the PSCAD trajectory on
top. The table reports the achieved agreement with PSCAD itself, next to
the acceptance the upstream project uses for its own PSID-vs-PSCAD
comparison of the same data.

.. list-table::
   :header-rows: 1
   :widths: 24 20 14 14 24

   * - Case
     - PSCAD quantity
     - Achieved (inf)
     - Achieved (2-norm)
     - Upstream acceptance (2-norm)
   * - droop grid-forming (Test23)
     - converter angle
     - 1.3e-2 rad
     - 5.0e-2
     - 3e-2
   * - virtual synchronous machine (Test08)
     - converter frequency
     - 1.3e-4 p.u.
     - 7.3e-4
     - 1e-4
   * - grid following (Test24)
     - filtered power
     - 1.1e-1 p.u.
     - 2.9e-1
     - none: upstream keeps this assertion disabled
   * - two Marconato machines, dynamic lines (Test25)
     - bus voltage
     - 3.2e-3 p.u.
     - 9.2e-2
     - 1e-1 ("relaxed to account for mismatch in damping")

These are electromagnetic-vs-phasor comparisons, so the residuals are
physics, not implementation error: the same-system PSID references agree
with hermess to 1e-5 or better on every state, and the Test24 power trace
is a discrepancy the upstream project itself carries (its assertion is
commented out). The systems ship as :ref:`omib_gfm_pscad <omib_gfm_pscad>`,
:ref:`omib_vsm_pscad <omib_vsm_pscad>`,
:ref:`omib_gfl_pscad <omib_gfl_pscad>` and
:ref:`3bus_marconato_pscad <3bus_marconato_pscad>`.

Benchmark tables
----------------

The South East Australian 14-generator benchmark (``sea14gen``) is checked
against the published tables of Gibbard and Vowles (2014): the load flow and
the rotor modes of the six operating cases. This validates the GENROU and
GENSAL machines with their full controller chains (AVR, PSS) on a realistic
multi-machine system, complementing the single-model precision of the ANDES
cases. See ``docs/sea_benchmark.md`` in the repository.

Regenerating the references
---------------------------

CI compares against the committed reference files and does not need ANDES.
Regeneration is a deliberate act::

   uv sync --group validation
   uv run python hermess/tests/references/andes/<case>/generate.py

The versions that produced each reference are recorded in its
``reference_meta.json``. ``hermess/tests/references/README.md`` documents the
layout, the regeneration workflow, and what to check before touching a
tolerance when a comparison fails.
