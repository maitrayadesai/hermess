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

from pathlib import Path

import numpy as np
from hermess.run import run
import os
from hermess.config import config
import pickle

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_run():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sim_loc = os.path.join(base_dir, "baselines/baseline_result_sim.pkl")

    with open(sim_loc, "rb") as file:
        sim_base = pickle.load(file)  # numpy array of the baseline x_full

    new_config = config.updated(
        testsystemfile="IEEE39_bus",
        system_root=FIXTURE_ROOT,
        fn=50,
        Sb=100,
        ts=0.005,
        T_start=0.0,
        T_end=15.0,
        int_scheme_sim="idas",
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        log_level="INFO",
        incl_lim=False,
        line_dyn=False,
    )

    sim = run(new_config)

    assert np.allclose(
        sim.x_full, sim_base, atol=1e-06
    ), "The simulated results did not match the baseline"
