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

# Build hermess system files for one operating case of the
# 14-generator South East Australian benchmark from the transcribed tables
# (sea_data.py / sea_dynamics.py).
#
# Usage:
#   python build_sea_system.py [case]            # default case 1
#
# Writes  SEA_case<N>/sim_param.txt and sim_dist.txt  next to this script.
#
# Conventions/choices (see the PDF for table references):
# - All machine parameters are converted to the system base (100 MVA):
#   x_sys = x_machine·Sb/S_agg, H_sys = H·S_agg/Sb with S_agg = n·MVA_unit.
#   Sn is set to Sb so all base factors in the device models are unity.
# - Parallel circuits are aggregated (r/n, x/n, b·n) — identical to the
#   published per-circuit data in the base cases (PDF V4 notes, Table 10).
# - Generator step-up transformers: x/n_online, tap from Table 13 (t at the
#   FROM/generator side, matching Fig. 19 and the Grid tap convention).
# - Switched shunts (Table 12) are merged into the constant-impedance loads:
#   q_eff = Q_load − Q_shunt·V₀², with V₀ refined by re-running the power
#   flow (--pf-check mode) until the BusInit values are self-consistent.
# - SVC buses are PV buses at the SVC setpoint voltage; SVC devices appear
#   BEFORE the loads so their finit can remove their current share from
#   dae.iinit (see devices/svc.py).
# - LPS_3 (bus 301) is the slack; its Table-8 output is a validation target.
# - --gfm "NAME,NAME" / --gfl "NAME,..." replace the named power stations by
#   grid-forming / grid-following converters of the same aggregate rating
#   and dispatch (quasi-static LCL filter for the static network); the
#   loadflow is unchanged. Output dir gets a _conv suffix.

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sea_data as D  # noqa: E402
import sea_dynamics as DYN  # noqa: E402

SB = 100.0
T_FLOOR = 1e-3  # floor for 0 s time constants: parasitic pole @1e3 rad/s,
#                 two decades above the rotor-mode band, keeps IDAS step sizes sane


def fmt(x: float) -> str:
    return f"{x:.10g}"


def all_buses() -> list:
    buses = []
    for f, t, *_ in D.LINES:
        for b in (f, t):
            if b not in buses:
                buses.append(b)
    for f, t, *_ in D.TRANSFORMERS:
        for b in (f, t):
            if b not in buses:
                buses.append(b)
    return buses


def gen_lines(case: int, v0: dict) -> list:
    out = []
    out.append("# Transmission lines (Table 10, parallel circuits aggregated)")
    for f, t, n, r, x, b in D.LINES:
        out.append(
            f'Line, bus_i = "{f}", bus_j = "{t}", r = {fmt(r / n)}, '
            f"x = {fmt(x / n)}, g = 0, b = {fmt(b * n)}, trafo = 1"
        )

    out.append("")
    out.append("# Transformers (Tables 11/13); 'ng' = online units of the generator")
    units_online = {D.GENERATORS[g][0]: D.GENERATORS[g][3][case][0] for g in D.GENERATORS}
    for f, t, num, rating, x in D.TRANSFORMERS:
        n = units_online[f] if num == "ng" else int(num)
        if n == 0:
            continue  # power plant fully offline in this case
        tap = D.TAPS[(f, t)][case - 1]
        out.append(
            f'Line, bus_i = "{f}", bus_j = "{t}", r = 0, x = {fmt(x / n)}, '
            f"g = 0, b = 0, trafo = {fmt(tap)}"
        )
    return out


def businit_lines(case: int, v0: dict) -> list:
    out = ["# Bus initialization (Tables 8/9/12/14)"]
    svc_buses = {D.SVCS[s][0]: D.SVCS[s][4][case][0] for s in D.SVCS}
    gen_buses = {D.GENERATORS[g][0]: g for g in D.GENERATORS}

    for bus in all_buses():
        load_p, load_q = (0.0, 0.0)
        if bus in D.LOADS:
            load_p, load_q = D.LOADS[bus][case - 1]
        q_sh = D.SHUNTS.get(bus, [0] * 6)[case - 1]
        v_est = v0.get(bus, 1.0)
        q_eff = load_q - q_sh * v_est**2

        if bus in gen_buses:
            g = gen_buses[bus]
            n, mw, _ = D.GENERATORS[g][3][case]
            if g == D.SLACK:
                out.append(f'BusInit, bus = "{bus}", p = 0, v = 1.0, type = "slack"')
            else:
                out.append(
                    f'BusInit, bus = "{bus}", p = {fmt(-n * mw)}, v = 1.0, type = "PV"'
                )
        elif bus in svc_buses:
            out.append(
                f'BusInit, bus = "{bus}", p = {fmt(load_p)}, '
                f'v = {fmt(svc_buses[bus])}, type = "PV"'
            )
        else:
            out.append(
                f'BusInit, bus = "{bus}", p = {fmt(load_p)}, q = {fmt(q_eff)}, '
                f'type = "PQ"'
            )
    return out


def svc_lines(case: int) -> list:
    out = ["# Static var compensators (Table 9 / Fig. 22); must precede the loads"]
    for name, (bus, mbase, qmax, qmin, percase) in D.SVCS.items():
        ka, _ks = DYN.SVC_CONTROL[name]
        _v, q = percase[case]
        out.append(
            f'SVC, idx = "{name}", bus = "{bus}", Sn = 100, fn = 50, '
            f"KA = {fmt(ka)}, Kd = {fmt(DYN.SVC_KD)}, Td = {fmt(DYN.SVC_TD)}, "
            f"B_min = {fmt(qmin / SB)}, B_max = {fmt(qmax / SB)}, q = {fmt(q)}"
        )
    return out


def load_lines(case: int) -> list:
    out = ["# Constant-impedance loads incl. merged switched shunts (Tables 12/14)"]
    # Shunt-only buses (414/415/416 reactors) get a ZIP too: its finit
    # calibrates to the bus init current, which there is exactly the shunt.
    buses = list(D.LOADS) + [
        b for b in D.SHUNTS
        if b not in D.LOADS and D.SHUNTS[b][case - 1] != 0
    ]
    for bus in buses:
        out.append(
            f'StaticZIP, bus = "{bus}", Sn = 100, fn = 50, '
            f"z_share = 1.0, i_share = 0.0, p_share = 0.0"
        )
    return out


def pss_params(gen: str, case: int) -> str:
    if "--no-pss" in sys.argv:
        return ""
    if gen not in DYN.PSS or gen in DYN.PSS_OFF.get(case, []):
        return ""
    kc, zeros, poles = DYN.PSS[gen]
    first_order = [z[1] for z in zeros if z[0] == "T"]
    quad = [z for z in zeros if z[0] == "ab"]
    poles = list(poles)

    if quad:
        a_q, b_q = quad[0][1], quad[0][2]
        tp5, tp6 = poles[-2], poles[-1]
        poles = poles[:-2]
    else:
        # Unused quadratic slot: exact unity for any pole pair (a=T5+T6,
        # b=T5·T6 cancels). Gentle poles avoid needless stiffness; tiny ones
        # push 1/(T5·T6) to 1e8 at 1e-4.
        tp5 = tp6 = 1e-2
        a_q, b_q = tp5 + tp6, tp5 * tp6

    # Pair first-order zeros with the remaining poles in order; leftover
    # poles become pure lags (Tz = 0); unused slots become exact unity
    # (Tz = Tp, gentle pole for the same stiffness reason).
    tz, tp = [], []
    for i in range(4):
        if i < len(poles):
            tp.append(poles[i])
            tz.append(first_order[i] if i < len(first_order) else 0.0)
        else:
            tp.append(1e-2)
            tz.append(1e-2)
    assert len(first_order) <= len(poles), f"{gen}: more PSS zeros than poles"

    sgn = -1.0 if gen in DYN.PSS_NEGATED.get(case, []) else 1.0
    parts = [f"K_stab = {fmt(DYN.PSS_DE * kc)}", f"Tw = {fmt(DYN.PSS_TW)}",
             f"sgn = {fmt(sgn)}"]
    for i in range(4):
        parts.append(f"Tz{i+1} = {fmt(tz[i])}")
        parts.append(f"Tp{i+1} = {fmt(tp[i])}")
    parts += [f"a_q = {fmt(a_q)}", f"b_q = {fmt(b_q)}",
              f"Tp5 = {fmt(tp5)}", f"Tp6 = {fmt(tp6)}"]
    return ", ".join(parts)


def _arg_list(flag: str) -> list:
    if flag in sys.argv:
        return [s.strip() for s in sys.argv[sys.argv.index(flag) + 1].split(",")]
    return []


def converter_line(gen: str, bus: str, s_agg: float, kind: str) -> str:
    """Grid-forming / grid-following converter replacing power station `gen`.

    Control parameters follow the IEEE39_bus_inverter fixture (droop GFM /
    PLL GFL with cascaded voltage/current control); the quasi-static LCL
    realization matches the static network model. Ratings and dispatch come
    from the loadflow (sequential init solves the setpoints)."""
    common = (
        f'idx = "{gen}c", bus = "{bus}", Sn = {fmt(s_agg)}, fn = 50, '
        "Kq = 0.1, Vref = 1.0, Rf = 0.003, Lf = 0.08, Cf = 0.074, "
        "Kpv = 0.866, Kiv = 433, Kffv = 0, Kpc = 0.143, Kic = 15.0, "
        "Kffc = 0, Rv = 0, Lv = 0.2, Lt = 0.2, Rt = 0.01"
    )
    if kind == "gfm":
        return f'GridForming, filter = "LCL_static", Kp = 0.01, {common}'
    return (
        f'GridFollowing, filter = "LCL_static", Kp = 0.02, '
        f"Kpll_p = 0.9, Kpll_i = 5, {common}"
    )


def machine_lines(case: int) -> list:
    out = ["# Synchronous machines (Tables 15/16/26/27, Appendix I.5)"]
    gfm = _arg_list("--gfm")
    gfl = _arg_list("--gfl")
    for gen, (bus, _maxu, mva, percase) in D.GENERATORS.items():
        n, _mw, _mvar = percase[case]
        if n == 0:
            continue
        if gen in gfm or gen in gfl:
            assert gen != D.SLACK, "cannot replace the slack machine"
            out.append(
                converter_line(gen, bus, n * mva, "gfm" if gen in gfm else "gfl")
            )
            continue
        s_agg = n * mva
        p = DYN.GEN_PARAMS[gen]
        to_sys = SB / s_agg  # reactance conversion machine->system base

        cls = "GENROU" if p["order"] == 6 else "GENSAL"
        xq1 = p["Xq1"] if p["Xq1"] is not None else p["Xq"]
        tq01 = p["Tq01"] if p["Tq01"] is not None else 1.0

        kv = {
            "Sn": 100, "fn": 50, "H": p["H"] * s_agg / SB, "D": 0, "f": 0,
            "R_s": 0,
            "x_a": p["Xa"] * to_sys, "x_d": p["Xd"] * to_sys,
            "x_q": p["Xq"] * to_sys, "x_dprim": p["Xd1"] * to_sys,
            "x_qprim": xq1 * to_sys, "x_dsec": p["Xd2"] * to_sys,
            "x_qsec": p["Xq2"] * to_sys,
            "T_d0prim": p["Td01"], "T_q0prim": tq01,
            "T_d0sec": p["Td02"], "T_q0sec": p["Tq02"],
        }

        if gen in DYN.AVR_ST1A:
            a = DYN.AVR_ST1A[gen]
            avr = "AVRST1A"
            kv.update(
                {
                    "KA": a["KA"], "TA": a["TA"],
                    "Tr": max(a["Tr"], T_FLOOR),
                    "TB": a["TB"], "TC": a["TC"],
                    "TB1": max(a["TB1"], T_FLOOR),
                    "TC1": a["TC1"] if a["TC1"] > 0 else max(a["TB1"], T_FLOOR),
                }
            )
        else:
            a = DYN.AVR_AC1A[gen]
            avr = "AVRAC1A"
            kv.update(
                {
                    "KA": a["KA"], "TA": a["TA"], "KE": a["KE"],
                    "TE": a["TE"], "KF": a["KF"], "TF": a["TF"],
                }
            )

        pss = pss_params(gen, case)
        strategies = f'avr = "{avr}", governor = "GOVCONST"'
        if pss:
            strategies += ', pss = "PSSSEA"'

        params = ", ".join(f"{k} = {fmt(v)}" for k, v in kv.items())
        out.append(
            f'{cls}, idx = "{gen}", bus = "{bus}", {strategies},\n\t{params}'
            + (f",\n\t{pss}" if pss else "")
        )
    return out


def write_case(case: int, v0: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = [
        f"# 14-generator South East Australian benchmark, Case {case}",
        "# Generated by build_sea_system.py from Gibbard & Vowles (2014).",
        "",
        *businit_lines(case, v0),
        "",
        *gen_lines(case, v0),
        "",
        *svc_lines(case),
        "",
        *load_lines(case),
        "",
        *machine_lines(case),
        "",
    ]
    (out_dir / "sim_param.txt").write_text("\n".join(parts))
    # The benchmark has no turbine/governor models (constant Pm), so a
    # sustained load step has no post-disturbance equilibrium — the system
    # frequency would drift indefinitely. Use a cleared bus fault like the
    # published transient studies (Appendix IV).
    (out_dir / "sim_dist.txt").write_text(
        "# Default disturbance: 100 ms shunt fault at bus 217, then cleared\n"
        'Disturbance, time = 1.0, type = "FAULT_BUS", bus = "217", y = 10\n'
        'Disturbance, time = 1.1, type = "CLEAR_FAULT_BUS", bus = "217"\n'
    )


def run_power_flow(case_dir: Path) -> dict:
    """Run the init power flow on the generated file; return bus -> |V|."""
    code = f"""
import json
import numpy as np
from hermess.config import config
from hermess import system
from hermess.utils import data_loader

with open(r"{case_dir / 'sim_param.txt'}") as fid:
    data_loader.read(fid, "sim")
system.grid_sim.add_lines(system.line_sim)
for item in system.device_list_sim:
    if item.properties["xy_index"]:
        item.xy_index(system.dae_sim, system.grid_sim)
new_config = config.updated(
    testsystemfile="x", fn=50, Sb=100, ts=1e-3, T_start=0.0, T_end=1.0,
    plot=False, plot_voltage=False, plot_diff=False, log_level="ERROR",
    incl_lim=False, line_dyn=False, skip_disturance=True,
    print_power_flow=False, small_signal_analysis=False)
system.dae_sim.t = 1e-3
system.dae_sim.grid = system.grid_sim
system.dae_sim.device_list = system.device_list_sim
system.dae_sim.bus_init = system.bus_init_sim
system.dae_sim.setup(**vars(new_config))
system.grid_sim.setup(dae=system.dae_sim, bus_init=system.bus_init_sim)
v = {{}}
for bus in system.grid_sim.buses:
    re, im = system.grid_sim.yinit[bus]
    v[bus] = float(np.hypot(re, im))
print("PFJSON" + json.dumps(v))
"""
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=HERE.parents[2],
    )
    for line in res.stdout.splitlines():
        if line.startswith("PFJSON"):
            return json.loads(line[len("PFJSON"):])
    raise RuntimeError(f"power flow failed:\n{res.stdout[-2000:]}\n{res.stderr[-2000:]}")


def main() -> None:
    case = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    suffix = "_nopss" if "--no-pss" in sys.argv else ""
    if "--gfm" in sys.argv or "--gfl" in sys.argv:
        suffix += "_conv"
    out_dir = HERE / f"SEA_case{case}{suffix}"

    # Iterate the shunt-voltage calibration: BusInit q at shunt buses depends
    # on the solved voltage (constant-impedance shunts), which depends on q.
    v0: dict = {}
    for _ in range(3):
        write_case(case, v0, out_dir)
        v_new = run_power_flow(out_dir)
        delta = max(
            (abs(v_new.get(b, 1.0) - v0.get(b, 1.0)) for b in D.SHUNTS), default=0.0
        )
        v0 = v_new
        if delta < 1e-6:
            break
    write_case(case, v0, out_dir)
    print(f"wrote {out_dir} (shunt-voltage calibration delta {delta:.2e})")


if __name__ == "__main__":
    main()
