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
:ref:`3bus_tgov1 <3bus_tgov1>`, :ref:`3bus_sexst <3bus_sexst>` and
:ref:`3bus_avrst1a <3bus_avrst1a>`. The table reports the worst error
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
