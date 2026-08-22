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

# Wall-clock benchmark for the time-domain simulation. Inlines the
# simulation steps so setup and simulate can be timed separately.
#
# The --system argument is resolved against hermess/tests/fixtures,
# then hermess/systems (e.g. the South East Australian benchmark).
#
# Usage:
#   python benchmarks/benchmark_simulation.py [--system NAME] [--t-end T]
#       [--ts DT] [--line-dyn] [--incl-lim] [--linsol NAME] [--scheme NAME]
#       [--block-max N]
#
# Examples:
#   python benchmarks/benchmark_simulation.py --system IEEE39_bus_ideal
#   # the worst case: dynamic lines, small step, limiter loop
#   python benchmarks/benchmark_simulation.py --system IEEE39_bus_inverter \
#       --ts 1e-4 --t-end 0.2 --line-dyn --incl-lim

import argparse
import time
from pathlib import Path

from hermess.config import config
from hermess import system
from hermess.utils import data_loader

HERE = Path(__file__).resolve().parent
SEARCH_ROOTS = [
    HERE.parent / "hermess" / "tests" / "fixtures",
    HERE.parent / "hermess" / "systems",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="IEEE39_bus_ideal")
    ap.add_argument("--t-end", type=float, default=2.0)
    ap.add_argument("--ts", type=float, default=0.001)
    ap.add_argument("--line-dyn", action="store_true")
    ap.add_argument("--incl-lim", action="store_true")
    ap.add_argument("--linsol", default=None)
    ap.add_argument("--scheme", default="idas")
    ap.add_argument(
        "--block-max",
        type=int,
        default=None,
        help="override DaeSim.sim_block_max (1 = historical per-step loop)",
    )
    args = ap.parse_args()

    root = next((r for r in SEARCH_ROOTS if (r / args.system).exists()), None)
    if root is None:
        raise SystemExit(f"System '{args.system}' not found under {SEARCH_ROOTS}")

    sim_options = {
        "reltol": 1e-14,
        "max_num_steps": 10000,
        "max_step_size": 0.01,
        "jit": True,
    }
    if args.linsol:
        sim_options["linear_solver"] = args.linsol

    new_config = config.updated(
        testsystemfile=args.system,
        system_root=root,
        fn=50,
        Sb=100,
        ts=args.ts,
        T_start=0.0,
        T_end=args.t_end,
        int_scheme_sim=args.scheme,
        int_scheme_sim_options=sim_options,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        log_level="ERROR",
        incl_lim=args.incl_lim,
        line_dyn=args.line_dyn,
        skip_disturance=True,
        print_power_flow=False,
        small_signal_analysis=False,
    )

    t0 = time.perf_counter()
    simfile = root / args.system / "sim_param.txt"
    with open(simfile, "rt") as fid:
        data_loader.read(fid, "sim")

    system.grid_sim.add_lines(system.line_sim)
    for item in system.device_list_sim:
        if item.properties["xy_index"]:
            item.xy_index(system.dae_sim, system.grid_sim)
    system.dae_sim.t = new_config.ts
    system.dae_sim.grid = system.grid_sim
    system.dae_sim.device_list = system.device_list_sim
    system.dae_sim.bus_init = system.bus_init_sim
    system.dae_sim.setup(**vars(new_config))
    system.grid_sim.setup(dae=system.dae_sim, bus_init=system.bus_init_sim)
    t_powerflow = time.perf_counter()

    for item in system.device_list_sim:
        if item.properties["finit"]:
            item.finit(system.dae_sim)
    t_finit = time.perf_counter()

    for item in system.device_list_sim:
        if item.properties["fgcall"]:
            item.fgcall(system.dae_sim)
    system.grid_sim.gcall(system.dae_sim, line=system.line_sim)
    system.disturbance_sim.sort_chrono()
    system.dae_sim.check_initialization()
    t_symbolic = time.perf_counter()

    if args.block_max is not None:
        system.dae_sim.sim_block_max = args.block_max
    system.dae_sim.simulate(system.disturbance_sim)
    t_sim = time.perf_counter()

    dae_sim = system.dae_sim
    n_steps = dae_sim.nts
    sim_s = t_sim - t_symbolic
    print(
        f"\nsystem={args.system}  T_end={args.t_end}s ts={args.ts} "
        f"scheme={args.scheme} line_dyn={args.line_dyn} incl_lim={args.incl_lim} "
        f"linear_solver={args.linsol or 'default'}"
    )
    print(
        f"sizes: nx={dae_sim.nx} ny={dae_sim.ny} nl={dae_sim.nl} "
        f"nb={system.grid_sim.nb} steps={n_steps}"
    )
    print(f"load + power flow:        {t_powerflow - t0:8.2f} s")
    print(f"device finit:             {t_finit - t_powerflow:8.2f} s")
    print(f"symbolic build (fgcall):  {t_symbolic - t_finit:8.2f} s")
    print(f"simulate (incl. FG build):{sim_s:8.2f} s  ({1e3 * sim_s / max(n_steps - 1, 1):.3f} ms/step)")
    print(f"total:                    {t_sim - t0:8.2f} s")


if __name__ == "__main__":
    main()
