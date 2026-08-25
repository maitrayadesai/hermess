# Cross-tool validation references

This directory holds reference data produced by tools that are **not ours**,
against which `test_reference_traces.py` validates the shipped dynamic models.
The rest of the test suite pins hermess against its own past output
(`baselines/`); these cases pin it against an independent implementation, so
they can catch a model that has been wrong since the day it was written. The
plan behind the layout is `docs/validation_plan.md`; the published results
table is `docs/source/validation.rst`.

## Layout

```
references/
├── andes/                     reference tool: ANDES (pip install andes, GPL)
│   ├── _common.py             shared builder for the ANDES twin systems
│   └── <case>/                one folder per validated model
│       ├── system/            the hermess system (sim_param.txt + sim_dist.txt)
│       ├── generate.py        the script that produced the reference
│       ├── reference.csv      trajectory on the comparison grid (committed)
│       ├── reference_meta.json  versions, initial states, eigenvalues (committed)
│       └── case.json          comparison spec: state maps and tolerances
└── psse/                      reference tool: PSS/E (trajectories from the
    ├── README.md              PSID benchmark set; provenance and the
    └── <case>/                compatibility table live in its README)
        ├── system/            the hermess transcription of the upstream case
        ├── upstream/          verbatim PSID files: .raw, .dyr, CSV, LICENSE
        └── case.json          comparison spec, tolerances, checksums
```

Adding a model = adding a folder: the test module discovers every folder with
a `case.json`. Keep the hermess system and the ANDES twin in `generate.py` in
lockstep; any edit to one is an edit to both, followed by regeneration.

## Regenerating

Regeneration is a deliberate act, never part of the test run; CI compares the
committed files and does not need ANDES. The `validation` dependency group
carries the reference tool:

```
uv sync --group validation
uv run python hermess/tests/references/andes/<case>/generate.py
```

The versions that produced each reference are recorded in its
`reference_meta.json` (`versions`: andes, numpy, python). The committed data
was generated with ANDES 2.0.0. After regenerating, rerun

```
uv run pytest hermess/tests/test_reference_traces.py
```

and check the achieved errors in the assertion messages against the
`achieved_*` snapshot in `case.json` before committing.

## What each case asserts

1. **Initialized operating point.** Every state, setpoint and power-flow
   voltage both tools expose, absolute tolerance per `case.json`.
2. **Eigenvalues** of the linearization at that point, matched pairwise
   (greedy nearest neighbour), with an absolute + relative tolerance.
3. **Post-disturbance trajectory.** Infinity norm per quantity over the full
   10 s window; algebraic quantities (voltages, powers) skip the samples at a
   switching instant, where the two tools sample opposite sides of the
   discontinuity.

## When a comparison fails

Resist changing the tolerance first. Check, in this order: the reference
frame (`omega_mode` must be `nom`), the per-unit base (everything here is on
Sn = Sb = 100 MVA), the saturation convention (disabled on both sides), and
the limiter state (`incl_lim = False`, ANDES limits wide open). A
disagreement that survives all of that is a finding about one of the two
tools, and is worth writing up either way.

## Tool-specific notes

- ANDES ships no GENSAL; the `gensal` case uses the exact reduction of ANDES
  GENROU with `xq1 = xq` (see `gensal/generate.py`).
- The ANDES TGOV1 covers ours with its lead-lag disabled (`T2 = 0`).
- The ANDES SEXS with `TATB = 1` reduces to the single-lag SEXST, and the
  ANDES EXST1 with `KF = 0` to the AVRST1A chain; a state left decoupled by
  such a reduction is placed at a distinctive fast pole and either dropped
  from the eigenvalue comparison (`case.json`) or paired with its
  counterpart on the other side (see each case's `generate.py`).
- The ANDES integration grid leaves the output step after a switching event,
  so `generate.py` runs it at a 1 ms fixed step and interpolates once onto
  the 5 ms comparison grid.
- hermess machines carry a rotor-friction term `f`; the reference cases set
  `f = 0`, which matches the absent term in the ANDES swing equation.
