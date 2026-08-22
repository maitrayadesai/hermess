# 03 — Sparse Levenberg–Marquardt in device initialization

**File:** `hermess/devices/device.py` — `Device._finit_joint`.

## 1. The initialization problem

`_finit_joint` initializes all *n* instances of one device class in a single
square Newton system. Unknowns and residuals, stacked over instances:

```
unknowns   z = [ x (device states) | u (setpoints) | y_priv (private algebraics) ]
residuals  h(z) = [ f(x, v̂, u) ;  g_vre ;  g_vim ;  g_priv ;  anchors ] = 0
```

with the bus voltages `v̂` *fixed* to the power-flow solution. The primary
solver is CasADi's `rootfinder('newton')`; for device classes whose init
Jacobian is rank-deficient at the guess (a benign gauge in the d-axis
excitation chain of the subtransient models with private algebraics) it
diverges, and a damped Gauss–Newton (Levenberg–Marquardt) fallback runs
instead:

```
(JᵀJ + λI) Δz = −Jᵀ r ,      J = ∂h/∂z
λ ↓ on accepted steps, λ ↑ on rejected steps.
```

This LM fallback is the *standard* path for the SG subtransient models — not
an exotic corner case.

## 2. The problem

Because the bus voltages are frozen, instance *p*'s residuals depend only on
instance *p*'s unknowns: **J is block-diagonal** with n blocks of size
s × s (s = states + setpoints + privates per instance, ~14 for an SG6).

The old code densified it anyway:

```python
J = np.array(Jh(z))                         # dense (n·s)² conversion
step = np.linalg.solve(JtJ + lam*np.eye(...), -J.T @ r)   # dense LAPACK
```

Per LM iteration that is O((n·s)³) flops for what is mathematically an
O(n·s³) problem — a factor n² of pure waste. At n = 160 machines
(z ≈ 2,200 unknowns) profiling showed 1.9 s in the dense `np.array(DM)`
conversions plus 0.8 s in `np.linalg.solve` over ~19 LM iterations; both
grow cubically with fleet size.

## 3. The fix

CasADi already computes `J` sparse; hand its compressed-column data straight
to `scipy.sparse` and keep every step of the normal equations sparse:

```python
J_dm = Jh(z)                       # CasADi DM, CCS storage
J = scipy.sparse.csc_matrix(
    (J_dm.nonzeros(), J_sp.row(), J_sp.colind()), shape=J_dm.shape)
JtJ = (J.T @ J).tocsc()            # block-diagonal again
step = spsolve(JtJ + λ·I_csc, −Jᵀr)   # SuperLU on n independent s×s blocks
```

`JᵀJ + λI` inherits the block-diagonal pattern, so the sparse LU factors it
in O(n·s³) — linear in the fleet — and the dense (n·s)² conversion
disappears entirely.

## 4. Equivalence

The iteration is unchanged: same residuals, same Jacobian values, same
damping schedule, same convergence test (‖r‖ < 1e-10). Only the linear
solver differs (SuperLU vs LAPACK `gesv`), which perturbs each step at
rounding level; since LM iterates to a fixed residual tolerance, the
converged initial state is the same within that tolerance. All
baseline-trajectory tests pass unchanged.

## 5. Measured effect

160 SG6 machines (624-bus system): device finit **3.30 s → 0.08 s** (41×),
with growth now ~linear in fleet size (0.18 s at 640 machines, where the
dense version would extrapolate to minutes).
