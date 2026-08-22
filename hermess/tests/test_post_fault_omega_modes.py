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

"""Regression tests: simulation must stay finite and bounded after a fault
for every reference-frame mode (nom, coi, single, dist) and both line_dyn
settings.

Guards against DaeSim.exec_dist() rebuilding self.x without refreshing
self.omega_ref_*_expr, which left the post-fault integrator referencing stale
SX symbols and diverging for every omega_mode except 'nom' (numeric ω_ref).
"""

from pathlib import Path

import numpy as np
import pytest

from hermess.config import config
from hermess.run import run

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _base_config(omega_mode: str, line_dyn: bool, testsystemfile: str):
    return config.updated(
        testsystemfile=testsystemfile,
        system_root=FIXTURE_ROOT,
        omega_mode=omega_mode,
        omega_single_idx="GFMI2",
        line_dyn=line_dyn,
        incl_lim=True,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="cvodes" if line_dyn else "idas",
        ts=0.0005 if line_dyn else 0.005,
        T_start=0.0,
        T_end=2.0,
        log_level="WARNING",
    )


def _omega_state_indices(sim) -> list[int]:
    """Return indices of states whose name ends in '_omega' (synchronous-machine
    rotor speeds and similar). Used as a sanity-check probe."""
    return [i for i, s in enumerate(sim.states) if s.endswith("_omega")]


def _assert_post_fault_healthy(sim, fault_time: float) -> None:
    # Whole trajectory must be finite.
    assert np.all(np.isfinite(sim.x_full)), "non-finite state encountered"

    # Probe rotor-speed-like states post fault — these should stay near 1 p.u.
    # for a small disturbance over the test horizon. This catches the
    # "integrator silently produced garbage" failure mode.
    fault_step = int(round(fault_time / sim.t))
    omega_idx = _omega_state_indices(sim)
    if omega_idx:
        post = sim.x_full[np.ix_(omega_idx, range(fault_step, sim.x_full.shape[1]))]
        assert np.all(post > 0.90) and np.all(
            post < 1.10
        ), f"omega state left plausible band: min={post.min()}, max={post.max()}"

    # If dist mode, delta_ref states must stay bounded (no runaway).
    if sim.has_delta_ref:
        delta_post = sim.x_full[
            np.ix_(list(sim.idx_delta_ref), range(fault_step, sim.x_full.shape[1]))
        ]
        assert np.all(np.abs(delta_post) < 1e3), "delta_ref state runaway"


@pytest.mark.parametrize("omega_mode", ["nom", "coi", "single", "dist"])
@pytest.mark.parametrize("line_dyn", [True, False])
def test_open_line_post_fault(omega_mode: str, line_dyn: bool) -> None:
    """3_bus_lineopen: OPEN_LINE at t=1.0s. Sim must complete and stay sane."""
    cfg = _base_config(omega_mode, line_dyn, testsystemfile="3_bus_lineopen")
    sim = run(cfg)

    assert sim.x_full.shape[1] == sim.nts
    _assert_post_fault_healthy(sim, fault_time=1.0)


@pytest.mark.parametrize("omega_mode", ["nom", "coi", "single", "dist"])
@pytest.mark.parametrize("line_dyn", [True, False])
def test_bus_fault_post_clear(omega_mode: str, line_dyn: bool) -> None:
    """3_bus_busfault: FAULT_BUS at t=1.0s, CLEAR at t=1.04s. Sim must
    complete and recover to plausible state."""
    cfg = _base_config(omega_mode, line_dyn, testsystemfile="3_bus_busfault")
    sim = run(cfg)

    assert sim.x_full.shape[1] == sim.nts
    # Use the clear time as the start of the recovery window — that's when
    # the network returns to a near-nominal topology.
    _assert_post_fault_healthy(sim, fault_time=1.04)
