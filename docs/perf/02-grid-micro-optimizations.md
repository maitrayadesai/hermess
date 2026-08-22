# 02 — Grid micro-optimizations

**Files:** `hermess/system.py` — `Grid.gcall`, `Grid.guncall`,
`GridSim.gcall`, `Grid.build_y`.

## 1. Skip the identity reference-frame rotation

The network KCL term added to the algebraic equations is

```
g[:2nn] += Tᵀ · Y · T · v
```

where `T(θ)` rotates each bus voltage from its local reference frame
(angle `θ_bus = δ_ref`) into the common frame. The distributed-reference
formulation (`omega_mode='dist'`) is the only mode with per-bus frames; in
every other mode `has_delta_ref = False` and

```
T = I  ⇒  Tᵀ Y T v = Y v .
```

The old code built `T = SX.eye(2nn)` and emitted both products anyway. CasADi
does simplify `1·x` at the scalar level, but the two extra sparse
matrix-product *constructions* still walk O(nnz) entries each — on every
equation rebuild, which happens at setup **and after every disturbance**
(`exec_dist` → `guncall`/`gcall`). Now the `Y v` term is added directly when
no distributed frame is in use.

Correctness constraint honoured by the change: `gcall` and `guncall` must be
**exact mirrors** — `guncall` removes the previously-added admittance term
ahead of a topology change by subtracting the identical expression, so both
sites were switched together (plus the `GridSim.gcall` non-line-dyn override,
which is the simulator-side copy of the same term).

## 2. Drop the write-only dense impedance matrix

`Grid.build_y` (the numeric admittance build) ended with

```python
self.z_imp_matrix = np.linalg.inv(self.y_adm_matrix)   # (2nn × 2nn) dense
```

That inverse is O((2·nn)³) flops and O((2·nn)²) memory — about 8·10⁹ flops
at 1,000 buses — and `build_y()` re-runs at simulation start **and after
every parameter-changing disturbance**. A repository-wide search (package,
tests, examples) found no reader of `z_imp_matrix`; it is pure dead cost, so
it is no longer formed (the attribute is kept, set to `None`).

If some future consumer needs bus-impedance information, the right primitive
is a solve against the few columns actually needed,

```
Z[:, c] = solve(Y, e_c) ,
```

never the full explicit inverse: it is one O(n²)-per-column triangular
backsolve after a single sparse factorization, versus O(n³) for the dense
inverse, and it preserves sparsity of the factors.

The removed code also had a fallback that *mutated the admittance matrix*
(adding 1e-8 shunts at node 0) when `Y` was exactly singular; since nothing
consumed `Z`, that mutation could only mask a genuinely singular network
elsewhere. If singular networks need a guard, it belongs where `Y` is used.

Both items are behavior-preserving for every code path exercised by the test
suite (97/97 pass).
