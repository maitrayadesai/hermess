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

"""Tests verifying that delta_ref states are only created for omega_mode='dist'.

These simulation-only tests verify the conditional delta_ref implementation across
all omega_mode values and combinations of line_dyn and incl_lim.
"""

from pathlib import Path

import numpy as np
from hermess.run import run
from hermess.config import config

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_nom_no_delta_ref_line_dyn_false():
    """omega_mode='nom', line_dyn=False: no delta_ref states should exist."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus",
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
    assert not sim.has_delta_ref
    assert not hasattr(sim, "idx_delta_ref")
    assert not any("delta_ref" in s for s in sim.states)
    assert sim.x_full.shape[1] > 1


def test_nom_no_delta_ref_line_dyn_true():
    """omega_mode='nom', line_dyn=True: no delta_ref states should exist."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus_inverter",
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
        T_end=0.5,
        log_level="WARNING",
    )
    sim = run(new_config)
    assert not sim.has_delta_ref
    assert not hasattr(sim, "idx_delta_ref")
    assert sim.x_full.shape[1] > 1


def test_coi_no_delta_ref():
    """omega_mode='coi', line_dyn=True: no delta_ref states should exist."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus_inverter",
        system_root=FIXTURE_ROOT,
        omega_mode="coi",
        line_dyn=True,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_start=0.0,
        T_end=0.5,
        log_level="WARNING",
    )
    sim = run(new_config)
    assert not sim.has_delta_ref
    assert sim.x_full.shape[1] > 1


def test_single_no_delta_ref():
    """omega_mode='single': no delta_ref states should exist."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus_inverter",
        system_root=FIXTURE_ROOT,
        omega_mode="single",
        omega_single_idx=None,
        line_dyn=True,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_start=0.0,
        T_end=0.5,
        log_level="WARNING",
    )
    sim = run(new_config)
    assert not sim.has_delta_ref
    assert sim.x_full.shape[1] > 1


def test_dist_has_delta_ref_line_dyn_true():
    """omega_mode='dist', line_dyn=True: delta_ref states must exist."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus_inverter",
        system_root=FIXTURE_ROOT,
        omega_mode="dist",
        line_dyn=True,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_start=0.0,
        T_end=0.5,
        log_level="WARNING",
    )
    sim = run(new_config)
    assert sim.has_delta_ref
    assert hasattr(sim, "idx_delta_ref")
    nn = sim.grid.nn
    assert len(sim.idx_delta_ref) == nn
    assert any("delta_ref" in s for s in sim.states)
    assert sim.x_full.shape[1] > 1


def test_dist_has_delta_ref_line_dyn_false():
    """omega_mode='dist', line_dyn=False: delta_ref states must exist."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus_inverter",
        system_root=FIXTURE_ROOT,
        omega_mode="dist",
        line_dyn=False,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="idas",
        ts=0.0001,
        T_start=0.0,
        T_end=0.5,
        log_level="WARNING",
    )
    sim = run(new_config)
    assert sim.has_delta_ref
    assert hasattr(sim, "idx_delta_ref")
    assert sim.x_full.shape[1] > 1


def test_nom_with_limits_line_dyn_false():
    """omega_mode='nom', incl_lim=True, line_dyn=False: no delta_ref, limits work."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus",
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
    assert not sim.has_delta_ref
    assert sim.x_full.shape[1] > 1


def test_nom_with_limits_line_dyn_true():
    """omega_mode='nom', incl_lim=True, line_dyn=True: no delta_ref, limits work."""
    new_config = config.updated(
        testsystemfile="IEEE39_bus_inverter",
        system_root=FIXTURE_ROOT,
        omega_mode="nom",
        line_dyn=True,
        incl_lim=True,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_start=0.0,
        T_end=0.5,
        log_level="WARNING",
    )
    sim = run(new_config)
    assert not sim.has_delta_ref
    assert sim.x_full.shape[1] > 1


def test_state_count_reduction():
    """Verify nx is nn smaller when omega_mode != 'dist' vs 'dist'."""
    config_nom = config.updated(
        testsystemfile="IEEE39_bus_inverter",
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
        T_end=0.1,
        log_level="WARNING",
    )
    sim_nom = run(config_nom)

    config_dist = config.updated(
        testsystemfile="IEEE39_bus_inverter",
        system_root=FIXTURE_ROOT,
        omega_mode="dist",
        line_dyn=True,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_start=0.0,
        T_end=0.1,
        log_level="WARNING",
    )
    sim_dist = run(config_dist)

    nn = sim_nom.grid.nn
    assert sim_dist.nx == sim_nom.nx + nn
    assert sim_dist.x_full.shape[0] == sim_nom.x_full.shape[0] + nn
