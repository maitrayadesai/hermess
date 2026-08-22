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

"""Numerical validation of compute_i_full post-processing against CasADi branch_current_fun.

Compares the vectorized NumPy i_full computation against the per-step CasADi
build_branch_current_fun reference across multiple scenarios.

All tests use frozen fixtures under tests/fixtures/ rather than the shared
hermess/systems/ workspace, so interactive edits to the demo systems cannot
silently change test behavior. See tests/fixtures/README.md.
"""

from pathlib import Path

import numpy as np
import pytest
from hermess.run import run
from hermess.config import config

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _recompute_i_full_casadi(sim):
    """Recompute i_full using the CasADi branch_current_fun reference."""
    sim.grid.build_branch_current_fun(sim)
    i_full_ref = np.zeros_like(sim.i_full)
    for k in range(sim.nts):
        Ik = sim.grid.branch_current_fun(sim.x_full[:, k], sim.y_full[:, k])
        i_full_ref[:, k] = np.array(Ik).squeeze()
    return i_full_ref


def test_no_faults_incl_lim_true():
    """nom mode, LOAD step at t=1s, incl_lim=True: should match to machine precision."""
    new_config = config.updated(
        testsystemfile="3_bus_loadstep",
        system_root=FIXTURE_ROOT,
        omega_mode="nom",
        line_dyn=False,
        incl_lim=True,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="idas",
        ts=0.005,
        T_start=0.0,
        T_end=2.0,
        log_level="WARNING",
    )
    sim = run(new_config)
    i_full_ref = _recompute_i_full_casadi(sim)
    assert np.allclose(sim.i_full, i_full_ref, atol=1e-12)


def test_no_faults_incl_lim_false():
    """nom mode, LOAD step at t=1s, incl_lim=False: should match to machine precision."""
    new_config = config.updated(
        testsystemfile="3_bus_loadstep",
        system_root=FIXTURE_ROOT,
        omega_mode="nom",
        line_dyn=False,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="idas",
        ts=0.005,
        T_start=0.0,
        T_end=2.0,
        log_level="WARNING",
    )
    sim = run(new_config)
    i_full_ref = _recompute_i_full_casadi(sim)
    assert np.allclose(sim.i_full, i_full_ref, atol=1e-12)


def test_bus_fault_incl_lim_true():
    """nom mode, FAULT_BUS + CLEAR_FAULT_BUS, incl_lim=True."""
    new_config = config.updated(
        testsystemfile="3_bus_busfault",
        system_root=FIXTURE_ROOT,
        omega_mode="nom",
        line_dyn=False,
        incl_lim=True,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="idas",
        ts=0.005,
        T_start=0.0,
        T_end=3.0,
        log_level="WARNING",
    )
    sim = run(new_config)
    i_full_ref = _recompute_i_full_casadi(sim)

    assert len(sim._fault_intervals) > 1, "Expected fault boundaries to be tracked"
    assert np.allclose(sim.i_full, i_full_ref, atol=1e-12)


def test_dist_mode_incl_lim_true():
    """dist mode (has_delta_ref=True) under LOAD step at t=1s, incl_lim=True."""
    new_config = config.updated(
        testsystemfile="3_bus_loadstep",
        system_root=FIXTURE_ROOT,
        omega_mode="dist",
        line_dyn=False,
        incl_lim=True,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="idas",
        ts=0.005,
        T_start=0.0,
        T_end=2.0,
        log_level="WARNING",
    )
    sim = run(new_config)
    assert sim.has_delta_ref

    i_full_ref = _recompute_i_full_casadi(sim)
    # The omega=1.0 approximation in build_y() (used by compute_i_full)
    # diverges from the frequency-aware branch_current_fun whenever
    # omega_ref deviates from 1 (dist / coi modes). Accept up to 1%
    # relative error; nom mode is tested separately with machine-precision
    # tolerance.
    scale = np.max(np.abs(i_full_ref))
    max_diff = np.max(np.abs(sim.i_full - i_full_ref))
    assert max_diff / scale < 0.01, (
        f"Relative error {max_diff/scale:.4e} exceeds 1% threshold"
    )


def test_coi_mode_incl_lim_true():
    """coi mode, incl_lim=True.

    COI frequency deviates from 1.0 pu during transients, so the omega=1.0
    approximation in build_y() causes a small error vs the frequency-aware
    CasADi function. Same root cause as the dist mode discrepancy.

    Uses the LOAD-step fixture so the disturbance is pinned.
    """
    new_config = config.updated(
        testsystemfile="3_bus_loadstep",
        system_root=FIXTURE_ROOT,
        omega_mode="coi",
        line_dyn=False,
        incl_lim=True,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="idas",
        ts=0.005,
        T_start=0.0,
        T_end=2.0,
        log_level="WARNING",
    )
    sim = run(new_config)
    i_full_ref = _recompute_i_full_casadi(sim)

    # Same modeling discrepancy as dist mode — accept up to 1% relative.
    scale = np.max(np.abs(i_full_ref))
    max_diff = np.max(np.abs(sim.i_full - i_full_ref))
    assert max_diff / scale < 0.01, (
        f"Relative error {max_diff/scale:.4e} exceeds 1% threshold"
    )


def test_line_dyn_true():
    """nom mode, line_dyn=True, incl_lim=False."""
    new_config = config.updated(
        testsystemfile="3_bus",
        system_root=FIXTURE_ROOT,
        omega_mode="nom",
        line_dyn=True,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_start=0.0,
        T_end=2.0,
        log_level="WARNING",
    )
    sim = run(new_config)
    i_full_ref = _recompute_i_full_casadi(sim)
    assert np.allclose(sim.i_full, i_full_ref, atol=1e-12)
