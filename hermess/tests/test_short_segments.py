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

"""Simulation intervals shorter than one output step.

The run is integrated in segments separated by the disturbances. A segment whose
output grid is empty -- ``T_end`` at or just after the last disturbance, or two
disturbances closer together than one time step -- used to reach
``casadi.integrator`` with an empty grid, which segfaults the interpreter instead
of raising. These cases must complete (the trajectory simply ends where there is
nothing left to integrate), and a genuinely empty grid must raise.
"""

from pathlib import Path

import numpy as np
import pytest

from hermess.config import config
from hermess.run import run

FIXTURE_ROOT = Path(__file__).parent / "fixtures"

_COMMON = dict(
    system_root=FIXTURE_ROOT,
    fn=50,
    Sb=100,
    ts=0.001,
    T_start=0.0,
    int_scheme_sim="idas",
    plot=False,
    plot_voltage=False,
    plot_diff=False,
    log_level="ERROR",
    incl_lim=False,
    print_power_flow=False,
)

# the shipped 3-bus load-step fixture steps the load at t = 1.0 s
_T_DIST = 1.0


@pytest.mark.parametrize("line_dyn", [False, True])
@pytest.mark.parametrize("T_end", [_T_DIST, _T_DIST + 0.001])
def test_t_end_at_the_last_disturbance_completes(T_end, line_dyn, caplog):
    """T_end at (or within one step of) the last disturbance leaves nothing to
    integrate afterwards: the run completes and says so, rather than crashing."""
    cfg = config.updated(testsystemfile="3_bus_loadstep", T_end=T_end, line_dyn=line_dyn,
                         skip_disturance=False, **_COMMON)
    dae = run(cfg)

    assert dae.x_full.shape[1] == dae.nts == len(dae.time_steps)
    assert dae.time_steps[-1] == pytest.approx(T_end)
    assert np.isfinite(dae.x_full).all()
    # the run ends at the disturbance instant, so the trajectory is still the
    # pre-disturbance steady state: there was no time left for a response
    assert np.allclose(dae.x_full[:, -1], dae.xinit, atol=1e-6)
    assert any("less than one time step" in r.getMessage() for r in caplog.records)


def test_a_longer_run_is_unaffected():
    """The guard must not disturb the normal case: the same system run past the
    disturbance keeps every output step."""
    cfg = config.updated(testsystemfile="3_bus_loadstep", T_end=2.0, line_dyn=False,
                         skip_disturance=False, **_COMMON)
    dae = run(cfg)
    assert dae.x_full.shape[1] == pytest.approx(2000, abs=2)
    assert dae.time_steps[-1] == pytest.approx(2.0)


def test_empty_output_grid_raises_instead_of_crashing():
    """Any other path that would hand the integrator an empty grid gets a clear
    error (this is the call that used to segfault)."""
    cfg = config.updated(testsystemfile="3_bus_loadstep", T_end=2.0, line_dyn=False,
                         skip_disturance=True, **_COMMON)
    dae = run(cfg)
    dae.tf = np.array([])
    with pytest.raises(ValueError, match="Empty integrator output grid"):
        dae.fgcall()


def test_simultaneous_disturbances_are_both_applied(tmp_path):
    """Two load steps scheduled at the same instant must have the same effect as
    one step of their combined size (neither skipped nor double-applied)."""
    src = FIXTURE_ROOT / "3_bus_loadstep"

    def _run_case(dist_text, name):
        case = tmp_path / name
        case.mkdir()
        (case / "sim_param.txt").write_text((src / "sim_param.txt").read_text())
        (case / "sim_dist.txt").write_text(dist_text)
        cfg = config.updated(**{**_COMMON, "testsystemfile": case.name,
                                "system_root": tmp_path, "T_end": 1.5})
        return run(cfg)

    step10 = 'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 10, q_delta = 0\n'
    step20 = 'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 20, q_delta = 0\n'
    two = _run_case(step10 + step10, "two")
    one = _run_case(step20, "one")
    assert two.time_steps[-1] == pytest.approx(1.5, abs=_COMMON["ts"])
    # atol floors the comparison for states that are physically zero and only
    # carry floating-point dust (observed at ~1e-25), where rtol is meaningless.
    np.testing.assert_allclose(two.y_full[:, -1], one.y_full[:, -1], rtol=1e-8, atol=1e-12)
    np.testing.assert_allclose(two.x_full[:, -1], one.x_full[:, -1], rtol=1e-8, atol=1e-12)
