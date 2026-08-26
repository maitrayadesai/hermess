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

"""Shared configuration + runner for the inverter byte-identical baselines.

Single source of truth for the ``IEEE39_bus_inverter`` baseline runs, imported by
both ``create_baseline_inverter.py`` (which pickles the references) and the
``test_recur_sim_inverter.py`` gates (which compare against them). Keeping the
config here prevents drift between baseline-creation and the tests. Two cases:

- ``sim_ld``  -- SIM, ``line_dyn=True`` (ODE; cvodes): 2 GridForming + 3
  GridSupporting + 5 SGs through the t=4.0 bus fault. Run at the production output
  step ``ts=1e-4`` but stored decimated (every ``SIM_LD_STRIDE``-th sample) so the
  pickle stays ~1 MB; a byte-identical refactor matches at every sample.
- ``sim_alg`` -- SIM, ``line_dyn=False`` (algebraic network / DAE; idas).

Baselines store only the ``x_full`` numpy arrays, not the whole DaeSim objects:
under pytest's ``pythonpath="hermess"`` + ``--import-mode=importlib``,
``system.DaeSim`` is reachable under two module paths, so whole-object pickling
raises "it's not the same object". The arrays are all the gates compare.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from hermess.config import config
from hermess.run import run

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"
_BASE = Path(__file__).resolve().parent

#: Decimation stride for the line_dyn=True sim (run at ts=1e-4, stored every 50th
#: sample -> 5e-3 effective spacing) to keep the pickle ~1 MB.
SIM_LD_STRIDE = 50

#: End time; the bus fault fires at t=4.0, leaving ~1 s of post-fault transient.
T_END = 5.0

BASELINES = {
    "sim_ld": _BASE / "baseline_inverter_sim_linedyn.pkl",
    "sim_alg": _BASE / "baseline_inverter_sim_alg.pkl",
}

_COMMON = dict(
    testsystemfile="IEEE39_bus_inverter",
    system_root=FIXTURE_ROOT,
    omega_mode="nom",
    fn=50,
    Sb=100,
    incl_lim=False,
    T_start=0.0,
    T_end=T_END,
    plot=False,
    plot_voltage=False,
    plot_diff=False,
    print_power_flow=False,
    log_level="WARNING",
)

# A fixed, JIT-free integrator setup for cross-run determinism (the config default
# uses jit=True + reltol=1e-14, which add a compiler dependency we don't want in a
# byte-identity gate).
_INT_OPTS = {"reltol": 1e-10, "max_num_steps": 500000}


def make_inverter_baseline_config(case: str):
    """Return the config for one baseline ``case`` (``sim_ld`` / ``sim_alg``)."""
    if case == "sim_ld":
        return config.updated(
            **_COMMON,
            line_dyn=True,
            int_scheme_sim="cvodes",
            int_scheme_sim_options=_INT_OPTS,
            ts=0.0001,
        )
    if case == "sim_alg":
        return config.updated(
            **_COMMON,
            line_dyn=False,
            int_scheme_sim="idas",
            int_scheme_sim_options=_INT_OPTS,
            ts=0.005,
        )
    raise ValueError(f"unknown baseline case {case!r}")


def run_inverter_case(case: str) -> np.ndarray:
    """Run one baseline ``case`` and return the simulated trajectory
    (decimated for ``sim_ld``)."""
    sim = run(make_inverter_baseline_config(case))
    arr = np.asarray(sim.x_full)
    if case == "sim_ld":
        arr = arr[:, ::SIM_LD_STRIDE]
    return arr
