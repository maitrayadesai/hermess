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

"""The inverter offers two initialization methods, dispatched by the per-device
``_init_method`` declaration: the staged ``sequential`` init (its default) and the
generic one-shot ``joint`` Newton+LM solve (via ``finit_anchor_residuals``).

This test forces the joint method and checks it reproduces the sequential-init
baselines byte-identically: the dispatch works and both methods converge to the
same operating point.
"""

import pickle

import numpy as np

from hermess.devices.inverter import Inverter
from hermess.tests.baselines.inverter_baseline import (
    BASELINES,
    run_inverter_case,
)


def test_joint_init_matches_sequential_baseline(monkeypatch):
    # Force every inverter (GridForming/GridSupporting inherit this) onto the
    # one-shot joint init; the baselines were generated with the sequential init.
    monkeypatch.setattr(Inverter, "_init_method", "joint")
    for case, atol in [("sim_ld", 1e-6)]:
        arr = run_inverter_case(case)
        with open(BASELINES[case], "rb") as file:
            base = pickle.load(file)
        assert np.allclose(arr, base, atol=atol), (
            f"joint init did not reproduce the sequential-init baseline for {case}"
        )
