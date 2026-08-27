# Parametric equations: making the model differentiable in its parameters

*A design note. Self-contained: it assumes no context beyond the repository.*

## The problem

The assembled equations carry parameter **values**, not parameter **symbols**. After a run,
the virtual-synchronous-machine row of `dae.f` prints as

```
(((0.5025 - x_19) - (20*(x_21 - 1))) / 16)
```

where `20` is the damping `D_v` and `16` is `2·H_v`. They are constants in the expression tree.
The same is true of every device parameter: `_params` entries become numpy arrays on the device
(`hermess/devices/device.py`), and `fgcall` uses them in arithmetic that folds the numbers into
the CasADi graph.

The consequence: **∂f/∂p does not exist to ask for.** We can differentiate freely with respect
to states, because `dae.x` and `dae.y` are genuine symbols, but a parameter is indistinguishable
from a literal by the time the model is built.

## Why this is worth fixing

Differentiating a trajectory with respect to parameters is the one capability neither ANDES nor
PowerSimulationsDynamics.jl has today (see `docs/validation_plan.md` for the comparison
context, and PSID issue #369 for their side of it). We can already do it, but only by *symbolic
surgery*: take the assembled right-hand side, and rewrite the one row that contains the
parameter with a symbolic version. That is three lines when the parameter lives in a single row,
as the VSM gains do. It is impractical for a machine reactance, which is spread through
`electromagnetic()`.

Measured on the current code, with the gain lifted by hand:

| | one trajectory | + exact gradient | vs finite differences |
|---|---|---|---|
| 3-bus, 38 states | 0.09 s | 0.41 s | 8e-5 |
| IEEE 39-bus with converters, 306 states | 7.6 s | 26 s | 6e-5 |

and the gradient cost is independent of the number of parameters (5.4x a trajectory at one
parameter, 6.9x at 1024) because CasADi resolves a scalar objective in reverse mode. So the
capability is real and it scales; what is missing is that it should not require hand surgery.

**Goal:** every device parameter is a symbol in `dae.f`, with the numeric model recovered by
substitution, so that `ca.jacobian(anything, p)` works without touching model code.

## The fact that makes this cheap

In `hermess/run.py` the build order is:

```python
for item in system.device_list_sim:      # line ~199
    if item.properties["finit"]:
        item.finit(system.dae_sim)        # numeric: power flow + device initialisation

for item in system.device_list_sim:      # line ~203
    if item.properties["fgcall"]:
        item.fgcall(system.dae_sim)       # symbolic: writes dae.f, dae.g, dae.fnode
```

**Initialisation is finished, numerically, before any equation is assembled.** So parameters can
be swapped from numbers to symbols *between the two loops*, and no model body has to change:
`fgcall` bodies only do arithmetic on the attributes, and CasADi arithmetic on an `SX` of length
`n` behaves like the numpy array of length `n` it replaces.

That is the whole difference in scale between this refactor and PSID's, which touches 73 files
because their parameters are read inside every model function at every call.

## Phase 1 — parametric right-hand side, fixed operating point

1. **Collect.** After `finit`, walk `dae.device_list` and build a registry: for each device and
   each name in `device._params`, an entry `(device, name, n, values)`. Ordering must be stable
   and reproducible; reuse the pattern of the existing state indexing.
2. **Swap.** Replace each attribute with `ca.SX.sym(f"{device}_{name}", n)`, keeping the numeric
   values in a parallel vector `p_val`. Stack the symbols into `dae.p` and store `dae.p_val`.
3. **Build.** Run the existing `fgcall` loop unchanged. `dae.f`, `dae.g`, `dae.fnode` and
   `dae.fl` now contain parameter symbols.
4. **Substitute.** `DaeSim.fgcall` already substitutes the reference-frequency placeholders and
   the limiter/line switch vectors before constructing the integrator. Add `dae.p → dae.p_val`
   at the same point. Everything downstream — integration, `eigenvalue_analysis`, the baselines
   — sees exactly the model it sees today.
5. **Expose.** A small accessor, e.g. `dae.parametric_rhs()`, returning `(z, rhs, p, p_val)`
   so a user can build their own sensitivity problem. `notebooks/helpers.vector_field` in the
   workshop repository is the shape to follow.
6. **Restore.** Put the numeric attributes back after the build, or keep both, so anything that
   reads `device.H` numerically afterwards still works.

### Risks, in the order they will bite

- **Not all arithmetic survives the swap.** Anything doing `np.where`, a comparison, `float()`,
  `.copy()`, boolean indexing or an `np.` function on a parameter will fail on an `SX`. These are
  the real cost of the phase. Find them by running the suite; they should be a handful, and each
  is either a CasADi equivalent (`ca.if_else`, `ca.fmax`) or a value that genuinely must stay
  numeric.
- **Setpoints are not parameters.** `_setpoints` (`Pref`, `Vref`, `Qref`, …) are *overwritten*
  by initialisation to match the power flow. Differentiating with respect to them is meaningless
  unless the initialisation is differentiated too. Keep them numeric in phase 1 and say so.
- **Expression size.** Symbols cannot be constant-folded, so `dae.f` grows and both build time
  and integration may slow. Measure it on the 39-bus case: the numbers in the table above are
  the baseline to preserve. If the cost is real, make the parametric build opt-in
  (`Config.parametric = True`) rather than the default.
- **The baselines.** `hermess/tests/baselines/*.pkl` pin state trajectories bit-for-bit. After
  substitution the model should be numerically identical, but floating-point association may
  change. If a baseline moves, understand why before regenerating it.

### Done when

- `dae.p` exists, `ca.jacobian(dae.f, dae.p)` is non-trivial, and substituting `p_val`
  reproduces today's `dae.f` to machine precision.
- The full test suite passes unchanged.
- The 3-bus and 39-bus timings above are within a small factor.
- A test asserts the gradient of a trajectory functional with respect to a machine `H` and a
  droop `Kp` against finite differences, at fixed initial condition.

## Phase 2 — differentiating the operating point

The total derivative is

  dx(t)/dp = (∂x(t)/∂x₀)·(dx₀/dp) + ∂x(t)/∂p

and phase 1 delivers only the second term. That is exact for parameters the operating point does
not depend on — the VSM gains are the clean example, since initialisation pins ω = ω_net and
Pref = Pc whatever the gains are — and incomplete for a reactance, a line parameter or a load.

The encouraging part: our initialisation is *already* built from CasADi rootfinders —

```
hermess/system.py:809                 power flow
hermess/devices/device.py:709         device joint initialisation
hermess/devices/static.py:497         static power-flow init
hermess/devices/inverter_{filter,inner,pll}.py   sequential inits
```

and `ca.rootfinder` propagates sensitivities through the implicit function theorem natively. So
dx₀/dp should be reachable by making the init residuals functions of `p` rather than of numbers,
without hand-writing an adjoint. **This is untested.** Before planning phase 2 in detail, verify
the premise on the smallest possible case: a rootfinder whose residual depends on a symbolic
parameter, and check that `ca.jacobian(root, p)` matches finite differences.

Phase 2 is worth doing only if phase 1 is used. Do not build it speculatively.

## Sequencing note

Phase 1 subsumes the hand surgery currently demonstrated in the workshop notebook
(`02_advanced_stability`), which lifts the VSM gains by rewriting one row. Once the parametric
build exists, that notebook cell becomes two lines and the demonstration gets stronger, not
weaker: the point stops being "you can edit the equations" and becomes "the equations were
always differentiable".
