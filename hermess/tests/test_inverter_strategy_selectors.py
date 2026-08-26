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

"""The data-file strategy selectors (filter=/angle=/voltage=/inner=/pll=) are
threaded correctly through the data loader.

Copies the inverter fixture and appends *explicit, default-matching* strategy
selectors to every GridForming/GridSupporting row, then checks the simulated
trajectory is byte-identical to the no-selector sim_ld baseline. This proves the
threading both (a) routes each selector to the right strategy and (b) reproduces
the hardcoded defaults exactly -- a regression guard for the registry plumbing.
"""

import pickle
import shutil

import numpy as np

from hermess.run import run
from hermess.tests.baselines.inverter_baseline import (
    BASELINES,
    FIXTURE_ROOT,
    SIM_LD_STRIDE,
    make_inverter_baseline_config,
)


def _add_default_selectors(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("GridForming,"):
        return (
            line.rstrip()
            + ', filter = "LCL", angle = "Droop", voltage = "QVDroop",'
            + ' inner = "Cascaded"'
        )
    if stripped.startswith("GridSupporting,"):
        return (
            line.rstrip()
            + ', filter = "LCL", angle = "PLL", voltage = "QVDroop",'
            + ' inner = "Cascaded", pll = "SRF_PLL"'
        )
    return line


def test_explicit_default_selectors_match_baseline(tmp_path):
    # Copy the fixture and inject explicit (default-matching) selectors.
    dst = tmp_path / "IEEE39_bus_inverter"
    shutil.copytree(FIXTURE_ROOT / "IEEE39_bus_inverter", dst)
    sim_param = dst / "sim_param.txt"
    patched = "\n".join(
        _add_default_selectors(line) for line in sim_param.read_text().splitlines()
    )
    sim_param.write_text(patched)

    # Same run config as the sim_ld baseline, pointed at the patched fixture.
    cfg = make_inverter_baseline_config("sim_ld").updated(system_root=tmp_path)
    sim = run(cfg)
    sim_x = np.asarray(sim.x_full)[:, ::SIM_LD_STRIDE]

    with open(BASELINES["sim_ld"], "rb") as file:
        base = pickle.load(file)

    assert np.allclose(sim_x, base, atol=1e-6), (
        "Explicit default-matching strategy selectors did not reproduce the "
        "no-selector baseline -- data-loader threading is wrong"
    )
