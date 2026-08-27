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

"""A lazy eigenvalue_analysis() must describe its own system.

run() reloads hermess.system in place, so the module-level grid_sim /
line_sim / device_list_sim always describe the most recently built system.
Calling eigenvalue_analysis() on an earlier DaeSim used to read the state
names from those globals: with a structurally different system built in
between, the names belonged to the wrong system, and with a different state
count the modal report crashed with an IndexError.
"""

import numpy as np

from hermess.config import config
from hermess.run import run


def quick_config(system, **overrides):
    settings = dict(
        testsystemfile=system,
        omega_mode="nom",
        fn=50,
        Sb=100,
        ts=0.01,
        T_start=0.0,
        T_end=0.1,
        int_scheme_sim="idas",
        int_scheme_sim_options={"reltol": 1e-8, "max_num_steps": 10000},
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        log_level="ERROR",
        incl_lim=False,
        line_dyn=False,
        skip_disturance=True,
        debug_check_init=False,
        print_power_flow=False,
        small_signal_analysis=False,
    )
    settings.update(overrides)
    return config.updated(**settings)


def test_analysis_after_building_a_different_system():
    sim_a = run(quick_config("3bus"))
    # A structurally different system (other machine model, other state count)
    # becomes the content of the module globals.
    run(quick_config("3bus_genrou"))

    sim_a.eigenvalue_analysis()

    n = len(sim_a.eigenvalues)
    assert sim_a.A.shape == (n, n)
    assert len(sim_a.state_names) == n
    assert sim_a.modes  # the modal report can be built

    # The names are those of sim_a's own devices, byte for byte.
    sim_ref = run(quick_config("3bus"))
    sim_ref.eigenvalue_analysis()
    assert sim_a.state_names == sim_ref.state_names
    assert np.allclose(
        np.sort_complex(np.array(sim_a.eigenvalues)),
        np.sort_complex(np.array(sim_ref.eigenvalues)),
    )
