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

"""Byte-identical SIM baseline gates for the inverter models.

Exercise GridForming + GridFollowing (+ SGs) through the t=4.0 bus fault and
compare the full state trajectory against the pickled references at atol=1e-6,
for both network realizations:

- ``test_sim_line_dyn``: ``line_dyn=True`` (ODE, cvodes).
- ``test_sim_alg``:      ``line_dyn=False`` (algebraic network / DAE, idas).

Any change to inverter state count, ordering, or numerics fails these instantly.
"""

import pickle

import numpy as np

from hermess.tests.baselines.inverter_baseline import (
    BASELINES,
    run_inverter_case,
)


def _assert_matches(case: str, atol: float) -> None:
    with open(BASELINES[case], "rb") as file:
        base = pickle.load(file)
    arr = run_inverter_case(case)
    assert np.allclose(
        arr, base, atol=atol
    ), f"The inverter '{case}' trajectory did not match the byte-identical baseline"


def test_sim_line_dyn():
    _assert_matches("sim_ld", atol=1e-6)


def test_sim_alg():
    _assert_matches("sim_alg", atol=1e-6)
