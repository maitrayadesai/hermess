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

# Validate a built SEA case against the published results:
#   stage 1: load flow — generator Q (Table 8), SVC Q (Table 9), slack P
#   stage 2: small signal — rotor modes vs Tables 2-7 (PSS in service)
#
# Usage:
#   python validate_sea.py [case]
#
# Run build_sea_system.py first for the same case.

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sea_data as D  # noqa: E402
import sea_dynamics as DYN  # noqa: E402

from hermess.config import config  # noqa: E402
from hermess import system  # noqa: E402
from hermess.utils import data_loader  # noqa: E402

SB = 100.0


def main() -> None:
    case = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    no_pss = "--no-pss" in sys.argv
    case_dir = HERE / f"SEA_case{case}{'_nopss' if no_pss else ''}"

    with open(case_dir / "sim_param.txt") as fid:
        data_loader.read(fid, "sim")
    system.grid_sim.add_lines(system.line_sim)
    for item in system.device_list_sim:
        if item.properties["xy_index"]:
            item.xy_index(system.dae_sim, system.grid_sim)

    new_config = config.updated(
        testsystemfile=f"SEA_case{case}", system_root=HERE, fn=50, Sb=100,
        omega_mode="nom",
        ts=1e-3, T_start=0.0, T_end=0.01,
        int_scheme_sim="idas",
        int_scheme_sim_options={"reltol": 1e-12, "max_num_steps": 10000,
                                "max_step_size": 0.01, "jit": True},
        plot=False, plot_voltage=False, plot_diff=False, log_level="WARNING",
        incl_lim=False, line_dyn=False, skip_disturance=True,
        print_power_flow=False, small_signal_analysis=False)
    dae = system.dae_sim
    grid = system.grid_sim
    dae.t = new_config.ts
    dae.grid = grid
    dae.device_list = system.device_list_sim
    dae.bus_init = system.bus_init_sim
    dae.setup(**vars(new_config))
    grid.setup(dae=dae, bus_init=system.bus_init_sim)

    # ---- stage 1: load flow ------------------------------------------------
    yinit = np.asarray(dae.yinit, dtype=float)
    iinit = np.asarray(dae.iinit, dtype=float)

    def bus_pq(bus: str):
        i = grid.idx_bus[bus]
        vre, vim = yinit[2 * i], yinit[2 * i + 1]
        ire, iim = iinit[2 * i], iinit[2 * i + 1]
        # net injection INTO the network at the bus (iinit = Y·v), system base
        p = (vre * ire + vim * iim) * SB
        q = (vim * ire - vre * iim) * SB
        return p, q

    print(f"\n=== Case {case}: load flow validation ===")
    print(f"{'unit':8s} {'P [MW]':>10s} {'P ref':>10s} {'Q [Mvar]':>10s} "
          f"{'Q ref':>10s}")
    worst_q = 0.0
    for gen, (bus, _mx, _mva, percase) in D.GENERATORS.items():
        n, mw, mvar = percase[case]
        if n == 0:
            continue
        p, q = bus_pq(bus)
        p_ref, q_ref = n * mw, n * mvar
        flag = ""
        if gen == D.SLACK:
            flag = " (slack)"
        worst_q = max(worst_q, abs(q - q_ref))
        print(f"{gen:8s} {p:10.1f} {p_ref:10.1f} {q:10.1f} {q_ref:10.1f}{flag}")

    print(f"\n{'SVC':8s} {'Q [Mvar]':>10s} {'Q ref':>10s}")
    worst_svc = 0.0
    for name, (bus, _mb, _qx, _qn, percase) in D.SVCS.items():
        v_set, q_ref = percase[case]
        p_net, q_net = bus_pq(bus)
        # net = SVC - load(+shunt); recover the SVC share from the load tables
        load_p, load_q = D.LOADS.get(bus, [(0, 0)] * 6)[case - 1]
        i = grid.idx_bus[bus]
        v2 = yinit[2 * i] ** 2 + yinit[2 * i + 1] ** 2
        q_sh = D.SHUNTS.get(bus, [0] * 6)[case - 1]
        q_svc = q_net + load_q - q_sh * v2
        worst_svc = max(worst_svc, abs(q_svc - q_ref))
        print(f"{name:8s} {q_svc:10.1f} {q_ref:10.1f}")

    print(f"\nworst |dQ| generators: {worst_q:.1f} Mvar, SVCs: {worst_svc:.1f} Mvar")

    # ---- stage 2: initialization + small signal ----------------------------
    for item in system.device_list_sim:
        if item.properties["finit"]:
            item.finit(dae)
    for item in system.device_list_sim:
        if item.properties["fgcall"]:
            item.fgcall(dae)
    grid.gcall(dae, line=system.line_sim)
    system.disturbance_sim.sort_chrono()
    dae.check_initialization()
    if "--debug-init" in sys.argv:
        import casadi as ca

        w_sym = ca.vertcat(dae.omega_ref, dae.omega_ref_buses, dae.omega_ref_lines)
        w_one = ca.SX.ones(1 + grid.nn + grid.nb, 1)
        f_init = ca.substitute(dae.f, w_sym, w_one)
        g_init = ca.substitute(dae.g, w_sym, w_one)
        fn = ca.Function("fg", [dae.x, dae.y, dae.s], [f_init, g_init])
        fv, gv = fn(dae.xinit, dae.yinit, dae.sinit)
        fv = np.array(fv).flatten()
        gv = np.array(gv).flatten()
        for name, vec, labels in (
            ("f", fv, dae.states),
            ("g", gv, [f"y[{i}]" for i in range(len(gv))]),
        ):
            bad = np.argsort(-np.abs(vec))[:8]
            for i in bad:
                if abs(vec[i]) > 1e-6:
                    print(f"{name}[{i}] = {vec[i]:+.4e}   {labels[i]}")
        return

    dae.update_omega()
    dae.eigenvalue_analysis()
    eigs = np.asarray(dae.eigenvalues)

    # rotor modes: oscillatory, in the published frequency band
    cand = eigs[(eigs.imag > 1.0) & (eigs.imag < 13.0)]
    col = "no_pss" if no_pss else "pss"
    ref = np.array([complex(r, i) for r, i in DYN.ROTOR_MODES[case][col]])

    print(f"\nall oscillatory modes 1 < Im < 13 rad/s ({cand.size}):")
    for c in sorted(cand, key=lambda z: -z.imag):
        print(f"   {c.real:+8.3f} {c.imag:+8.3f}j   zeta={-c.real/abs(c):+.3f}")

    print(f"\n=== Case {case}: rotor modes ({col}) vs Table {case + 1} ===")
    print(f"{'published':>22s} {'computed':>22s} {'|d_freq|':>9s} {'d_damp':>8s}")
    err_f, err_z = [], []
    for r in ref:
        k = np.argmin(np.abs(cand - r)) if cand.size else None
        c = cand[k] if k is not None else complex(np.nan, np.nan)
        zr = -r.real / abs(r)
        zc = -c.real / abs(c)
        err_f.append(abs(c.imag - r.imag))
        err_z.append(abs(zc - zr))
        print(f"{r.real:10.3f}{r.imag:+10.3f}j {c.real:10.3f}{c.imag:+10.3f}j "
              f"{err_f[-1]:9.3f} {err_z[-1]:8.3f}")
    print(f"\nmax |d_freq| {max(err_f):.3f} rad/s, "
          f"max |d_zeta| {max(err_z):.3f}")


if __name__ == "__main__":
    main()
