# 05 — Small-signal analysis: Schur complement via solve, not inverse

**File:** `hermess/system.py` — `DaeSim.eigenvalue_analysis`.

## 1. The reduction

Linearizing the semi-explicit DAE around the operating point
`(x₀, y₀)`:

```
Δẋ = f_x Δx + f_y Δy
 0 = g_x Δx + g_y Δy
```

eliminating the algebraic variables (assuming `g_y` regular) gives the
reduced state matrix whose eigenvalues are the system modes:

```
A_s = f_x − f_y · g_y⁻¹ · g_x .
```

(The mixed line-dyn case reduces the device-private algebraics the same way
with `[f; f_node; f_l]` as the differential block.)

## 2. The problem

The Jacobian blocks are evaluated **numerically** (a CasADi `Function` call
at the operating point) — but the elimination was done with

```python
As = fx - fy @ ca.inv(gy) @ gx
```

`ca.inv` on a numeric `DM` runs CasADi's own dense LU and **forms the
explicit (2nn+n_priv)² inverse**, then two dense products. That is slower
than LAPACK by a large constant, allocates the O(ny²) inverse for no reason,
and explicit inverses are also the numerically worse primitive (error bound
`κ(g_y)` enters twice: once forming `g_y⁻¹`, once multiplying).

## 3. The fix

Convert the (already numeric) Jacobian to numpy once and use a solve:

```python
As = fx - fy @ np.linalg.solve(gy, gx)      # one LU, n_x backsolves
```

Identical mathematics — `np.linalg.solve(gy, gx) = g_y⁻¹ g_x` computed
through the factorization instead of through the inverse.

**Singular `g_y`:** `ca.inv` produced inf/nan entries which the existing
"non-finite ⇒ skip the diagnostic" guard caught downstream; `np.linalg.solve`
raises instead. The `except LinAlgError: As = NaN` wrapper restores the exact
old degradation path (analysis skipped with a warning, never aborting the
simulation).

## 4. Cost

For `ny` algebraic variables the explicit-inverse route costs
`O(ny³)` (inverse) + `2·O(ny²·nx)` (two products) with CasADi's scalar
virtual-machine constant factors; the solve route is one `O(ny³)/3` LAPACK
LU + `O(ny²·nx)` backsolves + one GEMM, with vendor-BLAS constants. On large
systems this turns a minutes-scale pre-simulation diagnostic into seconds;
eigenvalue extraction itself (`np.linalg.eig`, also O(n³) but on the reduced
`nx`-sized matrix) is unchanged.
