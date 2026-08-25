# Cross-tool validation: a plan

## Why this exists

Today the test suite pins **our own past output**. `hermess/tests/baselines/*.pkl` are pickled
state trajectories, and `test_recur_sim.py` asserts that a fresh run still matches them. That
catches a regression, which is worth having, but it cannot catch a model that has been wrong
since the day it was written: the baseline was produced by the same code.

The one genuine external reference we have is the South-East Australian benchmark
(`docs/sea_benchmark.md`), where the load flow and the rotor modes are checked against the
published tables in the Gibbard and Vowles report. That is real validation, and it covers one
system and two machine models.

The gap this plan closes: **for each dynamic model we ship, a small system, a disturbance, and
a reference trajectory produced by a tool that is not ours, checked into the repository and
asserted in CI.**

---

## Where to look in the PSID repository

`PowerSimulationsDynamics.jl` does exactly this, and its layout is a working template worth
copying. The repository is now at **`github.com/Sienna-Platform/PowerSimulationsDynamics.jl`**
(the older `NREL-Sienna` and `NREL-SIIP` URLs redirect).

### The reference data

```
test/benchmarks/
├── psse/            31 model folders + the scripts that generated them
│   ├── GENROU/
│   │   ├── ThreeBusMulti.raw              network, PSS/E raw
│   │   ├── ThreeBusMulti_LessLoad.raw
│   │   ├── ThreeBus_GENROU.dyr            dynamic data, one model under test
│   │   ├── TEST_GENROU.csv                the reference trajectory from PSS/E
│   │   ├── TEST_GENROU_NO_SAT.csv         one file per parameter variant
│   │   └── TEST_GENROU_HIGH_SAT.csv
│   ├── TGOV1/       ThreeBusMulti.raw · ThreeBus_TGOV1.dyr · TEST_TGOV1.csv
│   ├── AC1A/ ESST1A/ EXAC1/ EXST1/ SCRX/ SEXS/ ST6B/ ST8C/          exciters
│   ├── GAST/ HYGOV/ DEGOV/ DEGOV1/ PIDGOV/ WPIDHY/                  governors
│   ├── GENCLS/ GENROE/ GENSAE/ GENSAL/                              machines
│   ├── IEEEST/ STAB1/ PSS2A/ PSS2B/ PSS2C/                          stabilisers
│   ├── CSVGN1/ DERA/ RENA/ LOAD/ MultiGen/ Test01/                  other
│   └── python_scripts/
│       ├── PSSEInterface34.py    drives PSS/E 34 through its Python API
│       ├── PSSEInterface35.py    and PSS/E 35
│       └── main.py               runs the case and writes the CSV
├── psat/            Test01 … Test04, Test45
│   └── Test01/      Test01.m · Test01_script.m · Test01_delta.csv
├── pscad/           Test08, Test23, Test24, Test25   (the electromagnetic comparison)
│   └── Test23/      test23.pscx · PSID_Library.pslx · Test23_theta.csv
└── andes/
    └── test36/      11BUS_KUNDUR.raw · 11BUS_KUNDUR_TGOV.dyr
                     andes_script.py · eigs_tgov_andes.csv    (eigenvalues, not a trajectory)
```

Two things to notice. Every reference folder carries **the generating script**, not just the
numbers, so a reader can regenerate it. And the validation is organised **per model**, not per
system: one small network, one model under test, one or more parameter variants.

### The tests that consume it

```
test/test_case15_genrou.jl        one file per model; 63 such files
test/test_case17_genrou_avr.jl
test/test_case20_ac1a.jl
test/test_case22_SteamTurbineGov1.jl
test/results/results_initial_conditions.jl    expected initial conditions, per case
test/results/results_eigenvalues.jl           expected eigenvalues, per case
test/runtests.jl
```

`test_case15_genrou.jl` is the one to read first. It asserts three things per parameter variant:

| check | against | tolerance |
|---|---|---|
| initial conditions | a stored dict in `results_initial_conditions.jl` | `norm < 1e-3` |
| eigenvalues | a stored vector in `results_eigenvalues.jl` | `norm < 1e-3` |
| rotor-angle trajectory | the PSS/E CSV | `norm(δ − δ_psse·π/180, Inf) ≤ 1e-1` |

Note the asymmetry, and copy it: **1e-3 against our own stored values, 1e-1 against another
tool.** Cross-tool trajectory agreement on a 20-second transient is loose, and pretending
otherwise produces a test that fails for reasons nobody can act on. Their disturbance is a
`BranchTrip` at t = 1.0 s over a 20 s span with `dtmax = saveat = 0.005`.

---

## Which reference tool to use

We do not have to start where they started.

**Start with ANDES.** It is `pip install andes`, GPL, pure Python, and it drives from a script
in the same environment as our tests, so regenerating a reference is a command rather than a
licensed desktop session. It is itself validated against PSS/E and DSATools TSAT, so agreement
with ANDES is a meaningful, if second-hand, claim. This is the same pragmatic call PSID made
for its eigenvalue comparison.

**Then add a licensed tool if one is reachable.** PSS/E or PowerFactory through the department
would let us claim agreement with an industry reference directly. Their
`python_scripts/PSSEInterface34.py` shows the shape of that automation. Do not block the first
milestone on it.

**PSAT** is a reasonable third: free, MATLAB, and the source of PSID's `Test01…Test45`
references.

### The comparison must be apples to apples

Most of the work in this plan is not writing tests, it is making the two runs comparable.
Getting any of these wrong produces a disagreement that is physics rather than a bug:

- **Run quasi-static.** ANDES is positive-sequence phasor with algebraic lines. Compare against
  `line_dyn=False`. A dynamic-network run will differ in the first tens of milliseconds by
  construction, and that difference is the feature, not an error.
- **Limiters off on both sides**, at least initially (`incl_lim=False`), or matched exactly.
- **Reference frame.** Fix `omega_mode` and know what the other tool uses. Rotor angles are
  frame-dependent; either compare frame-invariant quantities (speed, terminal voltage,
  active power) or align the frames explicitly. Comparing raw `delta` across tools is the
  classic way to manufacture a discrepancy.
- **Per-unit base.** Our machine parameters are on `Sn`, network on `Sb`. Confirm what the
  reference tool assumes before concluding anything.
- **Same disturbance, same instant, same clearing.** And keep `T_end` at least one output step
  past the last event (see the guard in `system.py`).
- **Same output grid**, so the traces can be compared without interpolation.
- **Saturation.** GENROU/GENSAL saturation conventions differ between tools. This is the single
  most likely source of a "failure" that is really a modelling convention; the PSID GENROU case
  carries three saturation variants for exactly this reason.

---

## Layout to adopt here

Mirroring their structure, in our idiom:

```
hermess/tests/references/
├── README.md                     how to regenerate everything, and with what versions
├── andes/
│   ├── genrou/
│   │   ├── system/               a hermess system: sim_param.txt + sim_dist.txt
│   │   ├── andes_case.xlsx       or .raw/.dyr, whatever ANDES consumes
│   │   ├── generate.py           the script that produced the reference
│   │   └── reference.csv         t, omega, v_terminal, p_e  (frame-invariant quantities)
│   ├── gensal/
│   ├── tgov1/
│   └── ...
└── psse/                         later, if a licence is reachable
```

and one test module:

```
hermess/tests/test_reference_traces.py
```

parametrised over the reference folders, so adding a model is adding a folder rather than
writing a test. Keep the reference CSVs small: 20 s at 5 ms is 4000 rows, which is fine in git;
do not check in full state trajectories.

---

## What one validation case asserts

For each model, in order of strength:

1. **Initial conditions.** The operating point after `finit`, against the other tool's
   initialisation. This catches most modelling errors immediately and costs nothing to compare.
   Tolerance `1e-4` relative on states that both tools expose.
2. **Eigenvalues at the operating point.** We have `dae.A` and `dae.eigenvalues`; ANDES has
   `ss.EIG.mu`. Compare the sorted spectra. This is a sharp test of the model's structure
   independent of any integrator. Tolerance `1e-3` absolute on the slow modes, looser on the
   fast ones.
3. **Trajectory after a disturbance.** Infinity norm on speed and terminal voltage, tolerance
   `1e-2` p.u. to start, tightened per model once we see the real agreement.

Record the achieved error in the test's assertion message, so a future tightening is informed
by what we actually get rather than by a guess.

---

## Model checklist

Ordered by what we ship, what a reader is most likely to doubt, and what the other tools also
have. The counterpart column is the model to compare against; entries marked *confirm* need
checking against that tool's documentation before starting (`andes doc <Model>` lists
parameters and equations).

| # | our model | file | counterpart | status |
|---|---|---|---|---|
| 1 | `GENROU` | `devices/synchronous.py` | ANDES `GENROU` | direct |
| 2 | `GENSAL` | `devices/synchronous.py` | ANDES `GENSAL` | direct |
| 3 | `TGOV1` | `devices/governor.py` | ANDES `TGOV1` | direct |
| 4 | `SynchronousSubtransientSP` | `devices/synchronous.py` | ANDES `GENROU` (Sauer-Pai vs standard: expect a structural difference, document it) | *confirm* |
| 5 | `IEEEDC1A` | `devices/avr.py` | ANDES `EXDC2` / `IEEEX1` | *confirm* |
| 6 | `AVRST1A` | `devices/avr.py` | ANDES `EXST1` | *confirm* |
| 7 | `SEXST` | `devices/avr.py` | ANDES `SEXS` | *confirm* |
| 8 | `AVRAC1A` | `devices/avr.py` | ANDES `ESAC1A` / `EXAC1` | *confirm* |
| 9 | `PSSKundur` | `devices/pss.py` | ANDES `IEEEST` or `ST2CUT` | *confirm* |
| 10 | `PSSSEA` | `devices/pss.py` | no direct counterpart; keep the SEA published-mode check as its validation | published tables |
| 11 | `Shaft4Mass` / `Shaft5Mass` | `devices/shaft.py` | PSID `FiveMassShaft` (structure matches; parameters differ) | *confirm* |
| 12 | `StaticZIP` | `devices/static.py` | ANDES `PQ` with the same conversion | direct |
| 13 | `SVC` | `devices/svc.py` | ANDES `SVC`? | *confirm* |
| 14 | `GridForming` / `GridFollowing` | `devices/inverter.py` | hardest: ANDES `REGF1` is phasor with an algebraic filter, ours has a dynamic LCL. Compare against **PSID** instead, whose LCL has the same six states | *confirm* |

Items 1 to 3 are the first milestone: they are unambiguous, widely implemented, and if any of
them disagrees we want to know today.

Item 14 is the one worth doing eventually and last. A converter comparison against PSID would
be the strongest validation this project could publish, because it is the part of the model
space where we claim to be interesting and where a reader has the least reason to trust us.

---

## Milestones

1. **One case, end to end.** GENROU on a three-bus system against ANDES: initial conditions,
   eigenvalues, trajectory. Establish the folder layout, the generate script, the comparison
   helper and the pytest parametrisation. Everything after this is repetition.
2. **Machines and governor:** GENSAL, TGOV1, Sauer-Pai. Write down the structural differences
   found rather than tuning tolerances until they pass.
3. **Excitation and stabilisers:** the AVR set, then the PSS.
4. **Publish the table.** A page in the docs listing each model, the tool it was checked
   against, the disturbance, and the achieved error. This is the artefact that changes how the
   project is read, more than the tests themselves.
5. **Converters against PSID**, and if a licence is reachable, a PSS/E pass on the machines.

## Notes for whoever implements this

- Pin the reference tool's version in `references/README.md` and in each `generate.py`. A
  reference trace without the version that produced it is not reproducible.
- Keep `generate.py` runnable but **not** part of the test run: regeneration is a deliberate
  act, and CI must not depend on ANDES being installed. Add it as an optional test dependency
  and mark the tests `skipif` when absent, or commit the CSVs and compare only.
- When a comparison fails, resist changing the tolerance first. Check the frame, the base, the
  saturation convention and the limiter state in that order.
- A disagreement that survives all of that is a finding, whichever tool turns out to be wrong,
  and is worth writing up either way.
