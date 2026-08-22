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

import os
import pickle
from pathlib import Path

import numpy as np

from hermess.config import config
from hermess.run import run

# Use the same system files the test reads, so the baseline matches exactly.
FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"

# Config matches the one used by test_recur_sim.py.
baseline_config = config.updated(
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
    small_signal_analysis=False,
)

baseline_result_sim = run(baseline_config)

out_dir = os.path.dirname(os.path.abspath(__file__))

# Store only the x_full array (not the whole DaeSim): pickling the object ties
# the baseline to a module path, which breaks across renames and pytest's
# importlib mode. The array is all the gate compares.
with open(os.path.join(out_dir, "baseline_result_sim.pkl"), "wb") as file:
    pickle.dump(np.asarray(baseline_result_sim.x_full), file)


print("Baseline results saved successfully.")
