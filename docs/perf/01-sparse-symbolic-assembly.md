# 01 — Sparse assembly of the symbolic network matrices

**Files:** `hermess/system.py` — `Grid.build_y_sym`,
`Grid.build_bus_rotation_T`, new helper `Grid._branch_selectors`.

**Type of change:** pure reformulation. The assembled matrices contain exactly
the same entries as before; only *how* they are constructed changes.

## 1. What the matrices are

`build_y_sym` assembles, in the real-valued (rectangular) formulation with
interleaved coordinates `[v_re_1, v_im_1, v_re_2, …]`:

- the bus admittance matrix `Y ∈ SX^(2nn × 2nn)`,
- the branch terminal-current maps `C_fwd, C_rev ∈ SX^(2nb × 2nn)`,

from the π-model of each branch *k* between from-bus *i(k)* and to-bus *j(k)*
with series impedance `z_k = r_k + j x_k`, total shunt `g_k + j b_k`, and
off-nominal tap `τ_k` on the from side. With `y_k = 1/z_k` the complex 2×2
branch admittance block is the standard

```
        ⎡ (y_k + y_sh,i)/τ_k²    −y_k/τ_k ⎤
Y_k  =  ⎢                                 ⎥ ,   y_sh = (g_k + j b_k)/2
        ⎣ −y_k/τ_k               y_k + y_sh,j ⎦
```

and each complex entry `a + jb` maps to the real 2×2 block `[[a, −b], [b, a]]`
— except that this code base stores the susceptance rows with the sign
convention visible in the per-entry expressions (`y_diag_imag = −b/2 + x·|y|²`
etc.); those expressions are **unchanged** by this commit. In `dyn_update`
mode the entries are CasADi expressions of the bus/line frequencies
(`x = ω_line·L`, `b_i = ω_bus,i·C`), so the matrix must be symbolic.

## 2. The problem

The old code allocated the targets as

```python
self.y_adm_matrix      = ca.SX.zeros(2*nn, 2*nn)
self.C_branches_forward = ca.SX.zeros(2*nb, 2*nn)
```

and filled them in a Python loop over branches, ~32 scalar insertions per
branch. Two separate scaling pathologies:

1. **`ca.SX.zeros(m, n)` is dense.** Unlike `ca.SX(m, n)` (structurally
   empty), `SX.zeros` *stores every zero* as an `SXElem`. The admittance
   matrix alone holds `4·nn²` stored scalars (1.56 M at nn = 624); the two
   branch maps hold `2·(2nb·2nn)` more. Everything downstream that touches
   these matrices — `Tᵀ(Y(Tv))` in `gcall`, the per-bus row products
   `u_power @ Y[2i:2i+2,:] @ y` inside the init power flow's rootfinder, the
   integrator's Jacobian — then operates on **dense** symbolic matrices.

2. **Elementwise insertion into an SX matrix rebuilds the sparsity pattern
   per write.** Each `M[a, b] += v` is O(nnz) in the worst case, so the loop
   is O(nb·nnz) ≈ O(nb²) pattern work.

Profiling a 624-bus / 751-branch case put 2.05 s inside `build_y_sym`
(of which 0.6 s was just allocating the dense zeros) and a further ~0.85 s in
the power flow whose symbolic graph had become dense.

## 3. The fix: accumulation as selector products

Every assignment in the old loop has the shape

```
M[a_k, b_k] += v_k        for k = 1 … nb
```

with **constant** index vectors `a, b` (topology) and per-branch values `v`
(symbolic or numeric). Define the *selector matrix* `E_a ∈ R^(m × nb)` with

```
(E_a)[a_k, k] = 1,    all other entries 0.
```

Then, writing `e_p` for the p-th unit vector,

```
Σ_k  v_k · e_{a_k} e_{b_k}ᵀ  =  E_a · diag(v) · E_bᵀ
```

— the left side is exactly what the loop accumulated (duplicate `(a_k, b_k)`
pairs, e.g. parallel lines, sum correctly on both sides). So each of the 16
accumulation patterns of `Y` (4 entries × {off-diag i→j, off-diag j→i,
diag i, diag j}) becomes one product, e.g. the real off-diagonal block:

```python
Y += E_ire @ diag(y_off_diag_real) @ E_jre.T      # Y[i_re_k, j_re_k] += yodr_k
```

The selectors are `ca.DM.ones(Sparsity.triplet(m, nb, rows, cols))` —
constant, one nonzero per column — built once per topology and cached
(`_branch_selectors`). The products are sparse-times-diagonal-times-sparse:
**O(nnz) work, O(nnz) storage**, and the resulting `Y` has the true network
sparsity (~16·nb nonzeros instead of 4·nn² stored entries).

`C_fwd` / `C_rev` follow the same pattern with row selectors `R_e`, `R_o`
(branch k → its even/odd row), e.g. the from-side entries of the forward map:

```
C_fwd[2k, i_re_k] += −yodr_k/τ_k + g_k/(2τ_k²)   ⇒   R_e @ diag(−yodr/τ + g/(2τ²)) @ E_ireᵀ
```

The bus-rotation matrix `T(θ)` (distributed-reference-frame mode), formerly
also `SX.zeros(2nn, 2nn)` plus 4·nn elementwise writes, is the same identity
with per-bus values `cos θ, sin θ`:

```
T = E_re diag(cos θ) E_reᵀ − E_re diag(sin θ) E_imᵀ + E_im diag(sin θ) E_reᵀ + E_im diag(cos θ) E_imᵀ
```

Bus-fault shunt admittances (a handful of diagonal entries) are still added
elementwise *after* assembly — the diagonal pattern already exists, so the
insertions are cheap — preserving the previous numerical content exactly.

## 4. Equivalence & ordering

Entry-for-entry the new matrices equal the old ones. The only difference is
floating-point *association order where several patterns hit the same entry*
(e.g. a diagonal entry receiving diag-i terms of several branches plus a
fault shunt): the loop interleaved them per branch, the product form sums per
pattern. For symbolic entries this changes the expression tree shape, not its
value; numerically the difference is ≤ machine-epsilon re-association noise.
The full test suite (97 tests, incl. baseline-trajectory comparisons) passes
unchanged.

## 5. Measured effect (624 buses, 751 branches, 160 machines)

| phase | before | after |
|---|---:|---:|
| load + init power flow | 2.75 s | 0.17 s |
| simulate (incl. integrator build) | 5.62 s | 3.66 s |

The simulate-phase gain is a by-product: the equation graph fed to the
integrator no longer contains dense matrix products, so differentiation,
code generation and JIT all shrink. At 2,496 buses the whole setup remains
~2 s, where the dense-zero formulation ran into minutes.
