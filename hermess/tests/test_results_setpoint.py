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

"""Derived outputs across a SETPOINT disturbance.

A SETPOINT event rebuilds the equations with the new setpoint baked in as a
numeric constant. The post-run extraction must evaluate each stored segment
with the expressions of its own build; evaluating the whole run with the
final expressions shifts the pre-event part of ``omega_c`` by
``Kp * (Pref_new - Pref_old)`` (the bug this file pins down).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

import hermess
from hermess.results import extract_results

TEMPLATE = Path(__file__).parent / "fixtures" / "3_bus_loadstep"


def _case(tmp_path, dist_line: str) -> str:
    shutil.copytree(TEMPLATE, tmp_path / "case")
    (tmp_path / "case" / "sim_dist.txt").write_text(dist_line + "\n")
    return str(tmp_path)


def _run(tmp_path, dist_line: str, t_end: float):
    root = _case(tmp_path, dist_line)
    dae = hermess.simulate(
        "case", system_root=root, T_end=t_end, small_signal_analysis=False
    )
    results = extract_results(dae)
    gfm = next(d for d in results.devices if d.unit == "GFMI2")
    return dae, results, gfm


def test_setpoint_keeps_pre_event_segment_exact(tmp_path):
    dae, results, gfm = _run(
        tmp_path,
        'Disturbance, time = 1.0, type = "SETPOINT", '
        'device = "GFMI2", param = "Pref", value = 0.7',
        t_end=5.0,
    )
    omega_c = gfm.algebraics["omega_c"]
    t = results.t

    # Before the event nothing moves: the reconstructed converter frequency
    # is exactly the nominal 1.0 p.u., not shifted by the later setpoint.
    pre = omega_c[t < 1.0 - 1e-9]
    assert pre.size > 100
    np.testing.assert_allclose(pre, 1.0, atol=1e-9)

    # After the event the converter picks up power, and by the end of the run
    # its frequency has settled onto the system frequency carried by the
    # machine's rotor speed.
    sg1 = next(d for d in results.devices if d.unit == "SG1")
    assert omega_c[-1] > 1.0005
    np.testing.assert_allclose(omega_c[-1], sg1.states["omega"][-1], atol=5e-4)

    # One expression snapshot per equation build: the initial one and the
    # SETPOINT rebuild.
    assert len(dae._expr_intervals) == 2


def test_load_step_run_stays_single_segment(tmp_path):
    dae, results, gfm = _run(
        tmp_path,
        'Disturbance, time = 1.0, type = "LOAD", bus = "2", '
        "p_delta = 10, q_delta = 0",
        t_end=2.0,
    )
    omega_c = gfm.algebraics["omega_c"]
    t = results.t

    # A LOAD event changes network data but never the device expressions:
    # the initial snapshot covers the whole run.
    assert len(dae._expr_intervals) == 1
    assert omega_c.shape == t.shape
    assert np.all(np.isfinite(omega_c))
    np.testing.assert_allclose(omega_c[t < 1.0 - 1e-9], 1.0, atol=1e-9)
