# 06 — `simulate()`: linear-time result accumulation

**File:** `hermess/system.py` — `DaeSim.simulate`
(the no-limiter, disturbance-interval branch).

## The problem

The no-limiter simulation path integrates from disturbance event to
disturbance event and appended each interval's trajectory block with

```python
self.x_full = np.hstack((self.x_full, xf))
self.y_full = np.hstack((self.y_full, yf))
```

`np.hstack` allocates a fresh array and copies **both** operands. With
interval lengths `c₁, c₂, …, c_K` (Σc_i = nts columns), interval *i* copies
all `c₁+…+c_i` accumulated columns again, so the total data movement is

```
Σ_i (c₁ + … + c_i) · (nx + ny)  =  O(K · nts · (nx+ny))
```

— quadratic in the number of events for a fixed horizon, and it doubles the
peak memory (old + new array coexist during each copy). Harmless for 5
events; not for event-rich studies (e.g. switching sequences or scripted
load ramps) on systems with 10⁴ states.

## The fix

Standard segment-list accumulation: collect the per-interval blocks in a
Python list and concatenate **once** at the end —

```python
x_segments.append(xf); n_cols += xf.shape[1]
...
self.x_full = np.hstack(x_segments)        # single O(nts·(nx+ny)) copy
```

Total data movement is one copy of the final array; peak memory is the final
array plus the (already-owned) segments.

One bookkeeping change: `_fault_intervals` recorded the post-event column
index as `self.x_full.shape[1]`, which no longer grows during the loop; a
running counter `n_cols` records the identical value (it is consumed later
by `compute_i_full` to evaluate branch currents per topology interval).

Output arrays are bit-identical to before — the same blocks end up at the
same column offsets.
