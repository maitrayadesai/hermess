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

"""Shared machinery for the ANDES reference generators.

Each ``<case>/generate.py`` defines its machines (and, when applicable,
governors) and calls :func:`run_and_write`, which builds the ANDES twin of the
three-bus hermess system in ``<case>/system/``, runs power flow, eigenvalue
analysis and the time-domain simulation, and writes ``reference.csv`` and
``reference_meta.json`` next to the script.

This module is imported only by the generate scripts, never by the test suite:
the tests compare against the committed CSV/JSON and must not require ANDES.
Regeneration is a deliberate act::

    uv run --group validation python hermess/tests/references/andes/genrou/generate.py

The three-bus network is shared by every case and mirrors the hermess
``sim_param.txt`` files line for line: a triangle of pi-lines between buses
1-2-3, machines at buses 1 (slack) and 3 (PV, 60 MW), and a 150 MW / 40 Mvar
load at bus 2 that both tools convert to constant impedance at the power-flow
voltage. The disturbance is the loss of line 3-1 at t = 1 s. All devices are
on the system base (Sn = Sb = 100 MVA, 50 Hz), so no per-unit conversion
happens on either side.

The ANDES time grid does not stay on the output step after the switching event
(it restarts from t_event + 1e-4), so the trajectory is generated with a 1 ms
fixed step and interpolated once, here, onto the 5 ms comparison grid; the
committed CSV is exactly the grid the test compares on.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import numpy as np

# The comparison grid: matches the hermess run (ts = 5 ms, T = [0, 10) s).
T_END = 10.0
TS_OUT = 0.005
T_EVENT = 1.0
TSTEP_ANDES = 0.001

# The three-bus network, one entry per line of the hermess sim_param.txt.
BUSES = (1, 2, 3)
LINES = (
    dict(idx="L12", bus1=1, bus2=2, r=0.01, x=0.08, b=0.03, g=0.0),
    dict(idx="L23", bus1=2, bus2=3, r=0.002, x=0.1, b=0.05, g=0.0),
    dict(idx="L31", bus1=3, bus2=1, r=0.006, x=0.03, b=0.075, g=0.0),
)
TRIPPED_LINE = "L31"
LOAD = dict(idx="PQ2", bus=2, p0=1.5, q0=0.4)
SLACK = dict(idx="GS1", bus=1, v0=1.03, a0=0.0)
PV = dict(idx="GP3", bus=3, p0=0.6, v0=1.02)
VN = 110  # one voltage level everywhere: no impedance-base conversion


def build_system(
    machines: list[dict],
    governors: list[dict] | None = None,
    exciter_model: str | None = None,
    exciters: list[dict] | None = None,
    pss_model: str | None = None,
    psss: list[dict] | None = None,
):
    """Build the ANDES twin. ``machines`` are GENROU parameter dicts (idx, bus,
    gen and the electrical parameters); ``governors`` are TGOV1 dicts or None;
    ``exciters`` are parameter dicts of ``exciter_model`` or None; ``psss``
    are parameter dicts of ``pss_model`` (attached to the exciters) or None."""
    import andes

    andes.config_logger(stream_level=30)
    ss = andes.System()
    ss.files.no_output = True
    ss.config.mva = 100
    ss.config.freq = 50

    for b in BUSES:
        ss.add("Bus", dict(idx=b, name=f"bus{b}", Vn=VN))
    for line in LINES:
        ss.add("Line", dict(**line, Vn1=VN))
    ss.add("PQ", dict(**LOAD, Vn=VN))
    ss.add("Slack", dict(**SLACK, Vn=VN))
    ss.add("PV", dict(**PV, Vn=VN))
    for mach in machines:
        ss.add("GENROU", dict(**mach, Vn=VN))
    for gov in governors or []:
        ss.add("TGOV1", gov)
    for exc in exciters or []:
        ss.add(exciter_model, exc)
    for pss in psss or []:
        ss.add(pss_model, pss)
    ss.add("Toggle", dict(model="Line", dev=TRIPPED_LINE, t=T_EVENT))
    ss.setup()

    # Both branches of the load become constant impedance in the time domain,
    # matching StaticZIP with z_share = 1 (the conversion happens at the
    # power-flow voltage in both tools). These are the ANDES defaults; pinned
    # here so a future ANDES default change cannot silently alter the case.
    ss.PQ.config.p2p = 0
    ss.PQ.config.p2i = 0
    ss.PQ.config.p2z = 1
    ss.PQ.config.q2q = 0
    ss.PQ.config.q2i = 0
    ss.PQ.config.q2z = 1
    return ss


def run_and_write(
    case_dir: Path,
    description: str,
    machines: list[dict],
    governors: list[dict] | None = None,
    exciter_model: str | None = None,
    exciters: list[dict] | None = None,
    exciter_init_vars: tuple = (),
    pss_model: str | None = None,
    psss: list[dict] | None = None,
    pss_init_vars: tuple = (),
    notes: list[str] | None = None,
) -> None:
    """Run power flow + EIG + TDS on the twin and write the reference files."""
    import andes

    ss = build_system(machines, governors, exciter_model, exciters,
                      pss_model, psss)
    if not ss.PFlow.run():
        raise RuntimeError("ANDES power flow did not converge")

    ss.TDS.config.tf = T_END
    ss.TDS.config.tstep = TSTEP_ANDES
    ss.TDS.config.fixt = 1
    ss.TDS.config.shrinkt = 0
    ss.TDS.init()

    gen_ids = [m["idx"] for m in machines]
    n_gen = len(gen_ids)

    def per_gen(var) -> list[float]:
        return [float(v) for v in np.asarray(var.v)]

    initial: dict = {
        "bus_v": per_gen(ss.Bus.v),
        "bus_a_rad": per_gen(ss.Bus.a),
        "GENROU": {
            name: per_gen(getattr(ss.GENROU, name))
            for name in (
                "delta", "omega", "e1q", "e1d", "e2d", "e2q",
                "psi2d", "psi2q", "vf", "tm", "te", "Pe", "Qe",
            )
        },
    }
    if governors:
        initial["TGOV1"] = {
            name: per_gen(getattr(ss.TGOV1, name))
            for name in ("LAG_y", "LL_x", "pout")
        }
    if exciters:
        exc_dev = getattr(ss, exciter_model)
        initial[exciter_model] = {
            name: per_gen(getattr(exc_dev, name)) for name in exciter_init_vars
        }
    if psss:
        pss_dev = getattr(ss, pss_model)
        initial[pss_model] = {
            name: per_gen(getattr(pss_dev, name)) for name in pss_init_vars
        }

    # Row 0 of the trajectory: the initial point (the ANDES store starts at the
    # first integration step, not at t = 0).
    x0 = np.asarray(ss.dae.x).copy()
    y0 = np.asarray(ss.dae.y).copy()

    ss.EIG.run()
    eigenvalues = np.asarray(ss.EIG.mu)

    if not ss.TDS.run():
        raise RuntimeError("ANDES time-domain simulation failed")

    ts = ss.dae.ts
    t = np.concatenate([[0.0], np.asarray(ts.t)])
    x = np.vstack([x0[None, :], np.asarray(ts.x)])
    y = np.vstack([y0[None, :], np.asarray(ts.y)])

    # Interpolate once onto the 5 ms comparison grid. All columns are
    # continuous except the algebraic ones at the switching instant, which the
    # test excludes from the comparison anyway.
    t_ref = np.arange(0.0, T_END, TS_OUT)

    def interp(addresses, source) -> np.ndarray:
        cols = [np.interp(t_ref, t, source[:, a]) for a in addresses]
        return np.column_stack(cols)

    columns: dict[str, np.ndarray] = {"t": t_ref}
    for name, arr in zip(gen_ids, interp(ss.GENROU.omega.a, x).T):
        columns[f"omega_{name}"] = arr
    for name, arr in zip(gen_ids, interp(ss.GENROU.delta.a, x).T):
        columns[f"delta_{name}"] = arr
    for bus, arr in zip(BUSES, interp(ss.Bus.v.a, y).T):
        columns[f"v_{bus}"] = arr
    for name, arr in zip(gen_ids, interp(ss.GENROU.Pe.a, y).T):
        columns[f"p_{name}"] = arr
    for name, arr in zip(gen_ids, interp(ss.GENROU.Qe.a, y).T):
        columns[f"q_{name}"] = arr
    if governors:
        for name, arr in zip(gen_ids, interp(ss.TGOV1.LAG_y.a, x).T):
            columns[f"psv_{name}"] = arr
        for name, arr in zip(gen_ids, interp(ss.TGOV1.LL_x.a, x).T):
            columns[f"pm_{name}"] = arr
    if exciters:
        # The machine's field voltage, driven by the exciter (hermess: Efd).
        for name, arr in zip(gen_ids, interp(ss.GENROU.vf.a, y).T):
            columns[f"efd_{name}"] = arr
    if psss:
        # The stabilizing signal into the exciter (hermess: Vs).
        pss_dev = getattr(ss, pss_model)
        for name, arr in zip(gen_ids, interp(pss_dev.vsout.a, y).T):
            columns[f"vs_{name}"] = arr

    header = ",".join(columns)
    data = np.column_stack(list(columns.values()))
    np.savetxt(case_dir / "reference.csv", data, fmt="%.10e", delimiter=",",
               header=header, comments="")

    meta = {
        "description": description,
        "tool": "ANDES",
        "versions": {
            "andes": andes.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "system": {
            "Sb_MVA": 100,
            "fn_Hz": 50,
            "buses": list(BUSES),
            "lines": [dict(line) for line in LINES],
            "load": dict(LOAD),
            "slack": dict(SLACK),
            "pv": dict(PV),
            "machines": [dict(m) for m in machines],
            "governors": [dict(g) for g in governors] if governors else [],
            "exciter_model": exciter_model,
            "exciters": [dict(e) for e in exciters] if exciters else [],
            "pss_model": pss_model,
            "psss": [dict(p) for p in psss] if psss else [],
        },
        "event": {"type": "line trip", "line": TRIPPED_LINE, "t": T_EVENT},
        "integration": {
            "method": "trapezoidal, fixed step",
            "tstep": TSTEP_ANDES,
            "output_grid": f"interpolated onto arange(0, {T_END}, {TS_OUT})",
        },
        "n_gen": n_gen,
        "initial": initial,
        "eigenvalues": [[float(m.real), float(m.imag)] for m in eigenvalues],
        "notes": notes or [],
    }
    (case_dir / "reference_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {case_dir / 'reference.csv'} ({data.shape[0]} rows, "
          f"{data.shape[1]} columns) and reference_meta.json (andes {andes.__version__})")
