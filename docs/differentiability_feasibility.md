# Parametric equations: feasibility audit

*Findings from a hands-on audit of `docs/differentiability_plan.md` phase 1 against the
current main (0d6be78), on branch `parametric-equations`, 2026-08-27. Method: a probe
script replicates `run()`'s build sequence, swaps every numeric `_params` entry for a
CasADi symbol between the `finit` and `fgcall` loops, builds, substitutes the values
back, and compares against the vanilla build.*

## Verdict

The refactor is safe on this version of the repository, and cheaper than the plan
budgets for. Every shipped system family builds parametrically after exactly two
model-code changes, both applied together with this note:

1. `ca.SX([[...]])` does not accept SX entries. The stator-matrix constructor in
   `SynchronousTransient.input_current`, `SynchronousSubtransient.input_current` and
   `GENROU` (three sites in `devices/synchronous.py`) is now `ca.blockcat`, which is
   behavior-identical for numeric entries. The full suite passes unchanged.
2. `np.isnan` / `np.where` on the `omega_f_q` NaN sentinel (`devices/inverter.py`,
   the Q-side measurement-filter corner) fails when either operand is symbolic. The
   site now guards on `isinstance(..., np.ndarray)`; the parametric build must resolve
   the sentinel numerically when it creates the symbols (swap `omega_f_q` with its NaN
   entries replaced by the numeric `omega_f` values, as one atomic pair).

No other site in any `fgcall` path breaks on symbolic parameters. The remaining NaN
sentinels (`StaticZIP.*_share_q`) are consumed only during initialization, which is
numeric by construction, so the registry can skip or resolve them freely.

## Measured evidence (probe, CasADi 3.7.2)

Build-level, all families: 3bus, 3bus_{genrou, gensal, tgov1, sexst, avrst1a, ieeedc1a,
avrac1a, psskundur, marconato_pscad, sauerpai_psid, shaft5mass_psid, gfm_psid,
dynlines_psid}, omib_{gfm, vsm, gfl}_pscad, kundur, kundur_conv, ieee39, ieee39_conv:

- Parametric assembly succeeds everywhere, including dynamic lines (`fnode`, `fl`) and
  the largest case (ieee39_conv: 395 parameter symbols, jacobian nnz 558). Assembly and
  substitution cost is milliseconds; integrator construction dominates either way.
- `ca.jacobian(dae.f, p)` is non-trivial in every case.
- After `ca.substitute(f, p, p_val)` the expressions are value-equal to the numeric
  build but not bit-identical: numpy pre-folds reciprocals (`0.0769·x`) where the
  symbolic graph keeps a division (`x/13`), a one-ULP difference per affected node.
  `ca.substitute` does constant-fold (`2*H → 13`), so the graphs match in size.

End-to-end on 3bus (5 s, OPEN_LINE at t = 3 s, idas, the shipped tolerances):

- max |x_parametric − x_reference| over the full trajectory: **3.8e-07** (the ULP
  differences, amplified through the disturbance; under the 1e-6 baseline tolerance,
  but not bit-for-bit, so keep the parametric build opt-in or expect to regenerate
  `tests/baselines/*.pkl`).
- eigenvalues at the operating point: **identical to 0.0**.
- simulation wall time: unchanged (substitution restores a numeric graph, so the
  integrator pays nothing; the plan's expression-size risk does not materialize in
  this design).
- correctness of symbol placement: parametric `f(p_val + h·e_H)` matches a genuine
  numeric rebuild with `H + h` to **2.8e-16**.

## One design correction to the plan

Step 4 of phase 1 ("add `dae.p → dae.p_val` at the same substitution point" inside
`DaeSim.fgcall`) is not sufficient. `check_initialization`, `debug_check_initialization`,
`eigenvalue_analysis`, the limiter block-stepping cache and the dist-mode rebuild all
construct `ca.Function`s from `dae.f`/`dae.g` with fixed input signatures; free parameter
symbols make every one of them throw. The safe shape is **substitute once, right after
the build loops in `run()`**: stash the parametric copies (`dae.f_par`, `dae.g_par`,
`dae.fnode_par`, `dae.fl_par`, plus `dae.p`, `dae.p_val`), substitute the values into
`dae.f`/`dae.g`/`dae.fnode`/`dae.fl` in place, and restore the numeric device
attributes. Everything downstream then sees exactly today's pipeline, and
`dae.parametric_rhs()` serves the stashed copies.

Details for the implementation:

- The registry must filter `_params` to float arrays: `Line`, `Disturbance` and
  `BusInit` keep strings and None entries in `_params`, and `bus_i`/`bus_j` are object
  arrays. Iterating `dae.device_list` (devices with `fgcall`) avoids most of this by
  construction. Setpoints live in `_setpoints` and are excluded automatically.
- Published per-device expressions (`self.Pe`, `self.Pc`, `self.Qc`) are assigned
  inside `fgcall` and would carry free symbols; substitute them at the same point.
- `init_symbolic()` resets `self.p` to a fresh zero-length symbol (`self.np = 0`, a
  leftover estimator hook, otherwise unused; the name is free to claim). The
  `exec_setpoint`/`exec_dist` rebuild paths call it mid-run, then rebuild from the
  restored numeric attributes, so the rebuilt model is numeric. That is consistent, but
  the stashed parametric copies describe the pre-disturbance model only; say so in the
  accessor's docstring.
- `Dae.dist_load` reads `q_share()` (a `float()` on the share arrays) mid-run; safe
  once attributes are restored after the build.

## Phase 2 premise: verified

`ca.rootfinder` propagates parameter sensitivities through the implicit function
theorem natively: on a 2-state test residual with a symbolic parameter,
`ca.jacobian(root, p)` matches central finite differences to 7e-11. The plan's
prerequisite experiment is done; making the init residuals functions of `p` is the
remaining (larger) work.

## Suite status

`uv run pytest hermess/tests/` after both model fixes: 236 passed, 1 skipped,
matching the pre-fix state. The numeric equation assembly was additionally
verified string-identical before and after the fixes on six systems covering
every touched code path (3bus_genrou, 3bus_gensal, 3bus, omib_gfm_pscad,
ieee39_conv, kundur).
