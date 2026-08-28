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

"""Setup guard for dynamic lines on shunt-free system files.

With ``line_dyn=True`` the line charging ``b`` acts as the bus capacitance
of the dynamic network (the voltage derivative is scaled by ``1/Bsum``), so
a bus whose branches all carry ``b = 0`` makes the network ODE singular.
The setup must reject such a run with the offending bus names instead of
letting the integrator fail with an Inf at the first step.
"""

import pytest

import hermess


def test_rms_only_system_rejected_with_dynamic_lines():
    # The Kundur machine buses connect only through their step-up
    # transformer branches, which carry no charging (b = 0).
    with pytest.raises(ValueError, match="shunt susceptance at every bus"):
        hermess.simulate("kundur", T_end=0.1, ts=1e-4, line_dyn=True)


def test_error_names_the_dead_buses():
    with pytest.raises(ValueError, match="B1"):
        hermess.simulate("kundur", T_end=0.1, ts=1e-4, line_dyn=True)


def test_hybrid_ready_system_still_accepted():
    dae = hermess.simulate("3bus", T_end=0.05, ts=1e-4, line_dyn=True)
    assert len(dae.time_steps) > 0
