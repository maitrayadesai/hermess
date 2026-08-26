# © 2024-2026 ETH Zurich
# Original author: Milos Katanic
# Simulation-only fork & maintainer: Maitraya Avadhut Desai
#
# Licensed under the GNU General Public License v3.0 or later;
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     https://www.gnu.org/licenses/gpl-3.0.en.html
#
# This software is distributed "AS IS", WITHOUT WARRANTY OF ANY KIND,
# express or implied. See the License for specific language governing
# permissions and limitations under the License.
#
# Simulation-only fork of PowerDynamicEstimator
# (https://doi.org/10.5905/ethz-1007-842); dynamic state estimation removed.
# For inquiries, contact: mdesai@ethz.ch

"""Quantify how far the CURRENT inverter trajectories drift from the committed
byte-identical baselines -- the diagnostic companion to
``test_recur_sim_inverter.py`` (which only gives boolean pass/fail).

Run from the repo root:

    .venv/bin/python -m hermess.tests.baselines.report_inverter_drift
    .venv/bin/python -m hermess.tests.baselines.report_inverter_drift sim_ld

Use this for non-byte-identical changes (e.g. floating-point reassociation), where
the gates can only say "diverged": this tool says by how much and in which states,
so you can confirm the drift is reassociation-scale rather than a transcription bug
and watch the margin against the gate tolerances.

It does NOT modify the baselines -- it loads them read-only and compares. Capture
a fresh reference only via ``create_baseline_inverter.py``, and only when an
intentional, validated numerics change makes the new trajectories the reference.

For each case it reports the array shape, the np.allclose gate verdict (same
semantics as the test: atol gate + numpy's default rtol=1e-5), the global
max-abs / max-rel / RMS difference with the location of the worst element, and a
per-state table of the largest-drifting rows -- named when the row->name
reconstruction matches the array (else bare indices, never a wrong label)."""

from __future__ import annotations

import pickle
import sys
from typing import List, Optional

import numpy as np

from hermess import system
from hermess.tests.baselines.inverter_baseline import (
    BASELINES,
    make_inverter_baseline_config,
    run_inverter_case,
)

#: Gate tolerance per case, mirroring test_recur_sim_inverter.py exactly.
GATE_ATOL = {"sim_ld": 1e-6, "sim_alg": 1e-6}

#: Floor added to the denominator of the relative error so near-zero baseline
#: entries (e.g. a current at rest) don't blow it up.
_REL_FLOOR = 1e-9

#: Device-name -> short tag, copied from system.py's participation-factor labeller
#: so the reconstructed names read the same as everywhere else in the codebase.
_DEVICE_ABBREV = {
    "Synchronous_machine_transient_model": "SM",
    "Synchronous_machine_subtransient_model": "SM",
    "Synchronous_machine_subtransient_model_Sauer_Pai": "SM_SP",
    "Synchronous_machine_subtransient_model_Sauer_Pai_6th_order": "SM_SP6",
    "GridForming_inverter_model": "GFM",
    "GridSupporting_inverter_model": "GFL",
    "Static_load_power": "SLP",
    "Static_load_impedance": "SLZ",
    "Static_load_ZIP": "ZIP",
    "Infinite_bus": "INF",
}


def _reconstruct_state_names(case: str, n_rows: int) -> List[str]:
    """Rebuild the per-row state names of ``x_full`` from the module globals that
    ``run_inverter_case`` just populated, mirroring the exact device -> entry ->
    state -> (dynamic-line tail) ordering system.py uses to build the state vector.

    The reconstruction is *length-guarded*: if anything is off (attribute missing,
    or the rebuilt list does not match ``n_rows``) it returns plain ``x{i}``
    indices rather than risk pinning a drift number on the wrong state."""
    fallback = [f"x{i}" for i in range(n_rows)]
    try:
        device_list, grid, line = (
            system.device_list_sim,
            system.grid_sim,
            system.line_sim,
        )

        names: List[str] = []
        for item in device_list:
            short = _DEVICE_ABBREV.get(item._name, item._name[:6])
            for i in range(item.n):
                for state in item.states:
                    names.append(f"{short}@{item.bus[i]}:{state}")

        if make_inverter_baseline_config(case).line_dyn:
            for i in range(grid.nb):
                for state in line.states:
                    names.append(f"DL_{line.bus_i[i]}-{line.bus_j[i]}:{state}")
            for i in range(grid.nn):
                for state in ["vre", "vim"]:
                    names.append(f"DL_{grid.buses[i]}:{state}")

        return names if len(names) == n_rows else fallback
    except Exception:
        return fallback


def report_case(case: str) -> Optional[dict]:
    """Run one baseline ``case`` on the current code, diff it against the committed
    reference, print the report, and return the metrics dict (None if the baseline
    is missing or the shapes differ)."""
    path = BASELINES[case]
    print(f"\n=== {case} ===")
    if not path.exists():
        print(f"  baseline missing: {path.name} -- run create_baseline_inverter.py")
        return None

    with open(path, "rb") as file:
        base = np.asarray(pickle.load(file))
    arr = run_inverter_case(case)  # populates the system module globals as a side effect

    if arr.shape != base.shape:
        # A shape change means the state count/ordering moved: a structural
        # regression, not reassociation drift.
        print(
            f"  SHAPE MISMATCH current {arr.shape} vs baseline {base.shape} "
            f"-- state count/ordering changed (structural regression, not drift)"
        )
        return None

    atol = GATE_ATOL[case]
    passes = bool(np.allclose(arr, base, atol=atol))  # default rtol=1e-5, as in the gate

    diff = np.abs(arr - base)
    rel = diff / (np.abs(base) + _REL_FLOOR)
    max_abs = float(diff.max())
    max_rel = float(rel.max())
    rms = float(np.sqrt(np.mean(diff**2)))
    r_abs, c_abs = np.unravel_index(int(diff.argmax()), diff.shape)

    names = _reconstruct_state_names(case, arr.shape[0])
    named = names[0] != "x0" or arr.shape[0] == 1  # whether reconstruction succeeded

    print(f"  shape            {arr.shape}  (rows=states, cols=time)")
    print(f"  gate np.allclose atol={atol:.0e}, rtol=1e-5 -> {'PASS' if passes else 'FAIL'}")
    print(f"  max |abs diff|   {max_abs:.3e}   at {names[r_abs]} (row {r_abs}, col {c_abs})")
    print(f"  max |rel diff|   {max_rel:.3e}   (floor {_REL_FLOOR:.0e})")
    print(f"  RMS abs diff     {rms:.3e}")
    if not named:
        print("  (state names unavailable -- showing row indices)")

    per_state = diff.max(axis=1)  # worst drift per state over all time
    order = np.argsort(per_state)[::-1]
    top = min(15, arr.shape[0])
    print(f"  top {top} drifting states (max |abs diff| over time):")
    for r in order[:top]:
        if per_state[r] == 0.0:
            break
        print(f"      {per_state[r]:.3e}  {names[r]}")

    return {
        "case": case,
        "shape": arr.shape,
        "pass": passes,
        "max_abs": max_abs,
        "max_rel": max_rel,
        "rms": rms,
        "argmax_row": int(r_abs),
        "argmax_col": int(c_abs),
        "argmax_name": names[r_abs],
    }


def main(argv: List[str]) -> int:
    cases = argv[1:] or list(BASELINES)
    unknown = [c for c in cases if c not in BASELINES]
    if unknown:
        print(f"unknown case(s) {unknown}; valid: {list(BASELINES)}")
        return 2

    results = [report_case(c) for c in cases]
    results = [r for r in results if r is not None]

    print("\n--- summary ---")
    for r in results:
        print(
            f"  {r['case']:8s} {'PASS' if r['pass'] else 'FAIL'}  "
            f"max|abs|={r['max_abs']:.2e}  max|rel|={r['max_rel']:.2e}  "
            f"rms={r['rms']:.2e}"
        )
    # Nonzero exit if any case failed its gate, so this is usable in a pipeline.
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
