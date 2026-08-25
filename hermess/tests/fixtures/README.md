# Test fixtures

This directory holds input files (`sim_param.txt`, `sim_dist.txt`) used by
the test suite.

**Treat these files as immutable** except when you are deliberately
changing a test's behavior in the same commit. Tests pin specific
disturbance sequences and parameter values to known-good baselines;
casual edits here will silently change test outcomes.

If you want to experiment with a 3-bus or IEEE39 scenario for your
own exploration, work in `hermess/systems/` instead. That
directory is the user-facing demo workspace and is expected to drift.

## Layout

Each subdirectory is a self-contained test scenario, named after the
system definition it pins:

- `3_bus/` — small 3-bus benchmark grid (one synchronous machine at
  bus 1, one grid-forming inverter at bus 3, ZIP load at bus 2). Used
  by `test_compute_i_full.py::test_line_dyn_true`.
- `3_bus_busfault/` — 3-bus grid with a `FAULT_BUS` + `CLEAR_FAULT_BUS`
  pair around t = 1 s. Used by `test_compute_i_full.py` and
  `test_post_fault_omega_modes.py`.
- `3_bus_lineopen/` — 3-bus grid with an `OPEN_LINE` event at t = 1 s.
  Used by `test_post_fault_omega_modes.py`.
- `3_bus_loadstep/` — 3-bus grid with a single 30 MW `LOAD` step at
  t = 1.0 s on bus 2. Test-only scenario; no corresponding entry in
  `systems/`. Used by 4 cases in `test_compute_i_full.py`.
- `IEEE39_bus/` — the standard IEEE 39-bus benchmark. Used by
  `test_recur_sim` and `test_sim_delta_ref`.
- `IEEE39_bus_ideal/` — IEEE 39-bus variant with idealized parameters
  (inherited from the original PowerDynamicEstimator test set).
- `IEEE39_bus_inverter/` — IEEE 39-bus variant with one or more
  inverter-based generators replacing synchronous machines. Used by
  `test_sim_delta_ref`.

Most fixtures are snapshots of folders that also live in
`hermess/systems/` — copies are intentional so that
interactive edits to the demo workspace cannot silently change test
behavior. The fixture folders deliberately keep their original names
(`3_bus`, `IEEE39_bus`, ...) although the folders under
`hermess/systems/` were later renamed (`3bus`, `ieee39`, ...): fixtures
are frozen test inputs and renaming them would churn every pinned test
for no behavioral gain.

When adding a new fixture, prefer copying an existing one and naming
it after the test scenario (`<base_grid>_<disturbance_kind>` is the
established convention).

## How tests reference fixtures

Tests pass `system_root` alongside `testsystemfile`:

```python
from pathlib import Path
FIXTURE_ROOT = Path(__file__).parent / "fixtures"

cfg = config.updated(
    testsystemfile="3_bus_loadstep",
    system_root=FIXTURE_ROOT,
    ...
)
```

`Config.system_root` (declared in `hermess/config.py`)
overrides the default repo `systems/` root used at
`hermess/run.py`. If `system_root` is left `None`, the
loader falls back to `hermess/systems/`, which is what
production / demo code uses.
