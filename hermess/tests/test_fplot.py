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

"""The built-in result plots (the path `hermess run <system>` takes by
default). The suite otherwise always runs with plotting off, which is how a
removed matplotlib API in fplot once went unnoticed."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

import hermess


def test_default_plot_path_draws_without_error(monkeypatch):
    monkeypatch.setattr(plt, "show", lambda *a, **k: None)
    hermess.simulate(
        "3bus_loadstep", T_end=0.2, ts=0.01, quiet=True,
        plot=True, plot_voltage=True, plot_diff=True,
    )
    assert plt.get_fignums(), "the plot path produced no figures"
    plt.close("all")


def test_ida_failure_is_translated():
    dae = hermess.simulate("3bus_loadstep", T_end=0.05, ts=0.01, quiet=True)

    def failing_fg(**kwargs):
        raise RuntimeError('IDACalcIC returned "IDA_CONV_FAIL". Consult IDAS documentation.')

    import numpy as np

    with pytest.raises(RuntimeError, match="did not converge"):
        dae._line_dyn_integrate(
            dae.xinit, dae.yinit, np.zeros(dae.nl), dae.sinit, dae.slinit,
            FG=failing_fg,
        )


def test_disturbance_rows_are_validated():
    from hermess.devices.device import Disturbance

    d = Disturbance()
    with pytest.raises(ValueError, match="supported types"):
        d.add(type="FAULT", time=1.0, bus="2")
    with pytest.raises(ValueError, match=r"unknown field.*p_delta[\s\S]*fault admittance"):
        d.add(type="FAULT_BUS", time=1.0, bus="2", p_delta=10)
    with pytest.raises(ValueError, match=r"missing field.*bus_j[\s\S]*Example"):
        d.add(type="FAULT_LINE", time=1.0, bus_i="1")
    d.add(type="FAULT_BUS", time=1.0, bus="2", y=20)
    d.add(type="SETPOINT", time=2.0, device="GFMI2", param="Pref", value=0.7)
    assert d.n == 2
