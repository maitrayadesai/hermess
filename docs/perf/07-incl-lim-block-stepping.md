# 07 — Limiter loop: block stepping

**File:** `hermess/system.py` — `DaeSim.simulate` (the
`incl_lim=True` branch), `DaeSim.fgcall` (new `tout` parameter),
`DaeSim._line_dyn_integrate` (new `FG` parameter).

This addresses the worst-case configuration: **dynamic lines, very small
time step, `incl_lim=True`**.

## 1. The problem

With limiters enabled, every output step ran

```python
res = self.FG(x0=x0, z0=y0, p=s0)      # one ca.integrator call per ts
x0  = clip(xf, xmin, xmax)
```

Each `Function` call of a SUNDIALS integrator pays a full solver setup:
IDACalcIC (consistent initial conditions for the algebraic block), the BDF
method restarting at order 1 with a small initial internal step, fresh
Jacobian factorization, plus the Python/DM marshalling around the call.
**This cost is independent of `ts`** — so as the step size shrinks (EMT-scale
studies need `ts ≤ 1e-4` s), the restart overhead dominates: at 624 buses and
`ts = 2e-5` the per-step loop spent 11.2 ms/step where a continuous
integration of the same trajectory costs ~3 ms/step.

## 2. The fix

Integrate *runs* of steps with one integrator call (a block of up to
`sim_block_max = 64` output points), falling back to single steps exactly
where the per-step semantics can differ:

**(a) Disturbances.** `check_disturbance(dist, k)` executes an event iff
`dist.time[0] ≤ k·ts`. The first step index that can fire is

```
k_event = ⌈ dist.time[0] / ts ⌉   (with an 1e-9 guard for float rounding)
```

A block may *end at* `k_event` but never cross it; interior block steps are
then exactly the steps for which `check_disturbance` was a guaranteed no-op,
so skipping their per-step check changes nothing. After every accepted batch
the check runs once at the batch's final index — the same index at which the
old loop would have executed the event. When an event executes it rebuilds
the equations and `self.FG` (via `exec_dist`/`dist_load`); the cached block
integrators are invalidated by watching `dist.time.size` shrink.

**(b) Limits.** The old loop applied `x ← clip(x, xmin, xmax)` after every
step. On any step where the state is inside the limits the clip is the
identity, so a *violation-free* sequence of single steps computes the same
trajectory as one continuous integration over the same grid (up to solver
restart noise — see §4). Therefore a block is accepted **only up to
(excluding) the first output column where the clip would alter the state**:

```
first_hit = min{ j : clip(x_j) ≠ x_j }      (column-wise test)
accept columns 0 … first_hit−1
```

From there the loop drops to single-step mode (clip applied per step, exactly
the historical semantics, including the parameter switches `s`) and only
returns to block mode after 8 consecutive clip-free steps. If the very first
block column already clips, the whole block is discarded and redone
step-by-step — progress is guaranteed because single-step mode always
accepts one step.

**(c) Integrators.** `ca.integrator` binds its output grid at construction,
but the DAE is autonomous, so one block integrator with relative grid
`T_start + ts·(1…B)` is reused for every block (the same property the old
loop relied on for its single-step `FG`). `fgcall(tout=...)` builds and
returns such an integrator without touching the canonical single-step
`self.FG`; they are cached per block length.

`dae_sim.sim_block_max = 1` reproduces the historical loop exactly (every
batch is a single step on `self.FG` with per-step clip and per-step
disturbance check).

## 3. Cost model

Let `c_setup` be the per-call solver setup and `c_int(Δt)` the genuine
integration work. Old loop: `nts · (c_setup + c_int(ts))`. Block mode:
`(nts/B) · (c_setup + c_int(B·ts))` ≈ `nts·c_int(ts) + (nts/B)·c_setup` —
the setup term shrinks by the block factor B. Since `c_setup` is
ts-independent, the speedup grows as ts shrinks.

## 4. Equivalence and validation

`benchmarks/check_block_stepping_equivalence.py` runs the same faulted
IEEE-39 simulation with `sim_block_max = 64` and `= 1`, with rotor-speed
limits tightened to `1 ± 5e-4` so clipping genuinely engages:

- identical clip-hit counts (149 = 149),
- max trajectory difference **3·10⁻¹³ over the 1000 pre-disturbance steps**
  (machine precision — the two modes are the same map when nothing clips),
- ≤ 2.4·10⁻⁵ through the post-fault clipped swing, which is
  integrator-restart noise (the two modes restart IDAS at different times)
  amplified by marginally-stable post-fault dynamics — the same order of
  difference one gets from changing solver build or tolerances, not a
  semantic deviation.

## 5. Measured effect

`IEEE39_tiled_inv_16` (624 buses, 160 converter/machine units,
`line_dyn=True`, `incl_lim=True`, idas, JIT, reltol 1e-14):

| ts | per-step loop | block stepping | speedup |
|---|---:|---:|--:|
| 1e-4 | 12.9 ms/step | 6.5 ms/step | 2.0× |
| 2e-5 | 11.2 ms/step | 3.1 ms/step | 3.6× |

Block stepping even beats the *no-limiter* continuous mode at the same
settings (7.1 ms/step), because a 64-step block also amortizes the
per-call Python/DM marshalling.
