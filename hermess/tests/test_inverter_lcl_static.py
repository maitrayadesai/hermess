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

"""Validate the quasi-static LCL_static filter (filter quantities as device-private
algebraics) against the dynamic LCL filter.

LCL_static is a singular-perturbation reduction that removes the fast LCL
dynamics, so it is not byte-identical to dynamic LCL. The validation is:

1. **Self-consistency / machinery:** LCL_static runs as a DAE (line_dyn=False),
   initializes, and is exactly reproducible, proving the algebraic-port plumbing
   (var_sym + DAE integration + routing the algebraic filter values into
   dae.yinit) is correct. It supports both init methods (sequential default and
   joint), which reach the same operating point.

2. **Quasi-static reduction (physics):** slow quantities of LCL_static and dynamic
   LCL (same static network) are machine-identical before a disturbance and
   re-converge after the fast transient settles; they differ only during the fast
   transient. Validated for both a bus fault and a small load step.
"""

import shutil

import numpy as np
import pytest

from hermess.config import config
from hermess.run import run
from hermess.tests.baselines.inverter_baseline import FIXTURE_ROOT

TS = 0.005
T_END = 5.0
# A few slow / quasi-static states of a grid-forming and a grid-following unit.
SLOW = [
    ("GFMI4", "Pc_tilde"),
    ("GFMI4", "delta_c"),
    ("GFMI4", "Qc_tilde"),
    ("GFLI7", "Pc_tilde"),
    ("GFLI7", "delta_c"),
]


def _build_fixture(root, filter_name, disturbance):
    """Copy the inverter fixture into ``root``, select ``filter_name`` on every
    converter, and set the disturbance (``"fault"`` keeps the bus fault at t=4.0;
    ``"load"`` replaces it with a small load step at t=2.0 on a load bus)."""
    dst = root / "IEEE39_bus_inverter"
    shutil.copytree(FIXTURE_ROOT / "IEEE39_bus_inverter", dst)
    sp = dst / "sim_param.txt"
    sp.write_text(
        "\n".join(
            (line.rstrip() + f', filter = "{filter_name}"')
            if line.strip().startswith(("GridForming,", "GridFollowing,"))
            else line
            for line in sp.read_text().splitlines()
        )
    )
    if disturbance == "load":
        sd = dst / "sim_dist.txt"
        kept = [
            l for l in sd.read_text().splitlines()
            if not l.strip().startswith("Disturbance,")
        ]
        kept.append('Disturbance, time = 2.0, type = "LOAD", bus = "4", p_delta = 3, q_delta = 0')
        sd.write_text("\n".join(kept))


def _run(root, filter_name, disturbance):
    _build_fixture(root, filter_name, disturbance)
    cfg = config.updated(
        testsystemfile="IEEE39_bus_inverter",
        system_root=root,
        omega_mode="nom",
        line_dyn=False,
        incl_lim=False,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        print_power_flow=False,
        int_scheme_sim="idas",
        int_scheme_sim_options={"reltol": 1e-10, "max_num_steps": 500000},
        ts=TS,
        T_start=0.0,
        T_end=T_END,
        log_level="ERROR",
    )
    sim = run(cfg)
    return sim


def _dev_state(sim, idx, state):
    """Trajectory of a named state for the device with the given idx."""
    for dev in sim.device_list:
        intmap = getattr(dev, "int", {})
        if idx in intmap:
            return np.asarray(dev.xf[state])[intmap[idx]]
    raise KeyError((idx, state))


def test_lcl_static_self_consistent(tmp_path):
    """LCL_static runs as a DAE, initializes (sequential by default), and is
    exactly reproducible (the algebraic-port machinery is correct)."""
    s1 = _run(tmp_path / "a", "LCL_static", "fault")
    s2 = _run(tmp_path / "b", "LCL_static", "fault")
    assert np.array_equal(s1.x_full, s2.x_full), "LCL_static is not reproducible"
    assert (s1.x_full.max(1) - s1.x_full.min(1)).max() > 0.1, "trajectory is trivial"


def test_lcl_static_both_init_methods_agree(tmp_path, monkeypatch):
    """LCL_static initializes correctly under BOTH the sequential init (routing the
    algebraic filter values into dae.yinit) and the joint init (solving them as
    private-algebraic unknowns); both reach the same operating point."""
    from hermess.devices.inverter import Inverter

    x0 = {}
    for method in ("sequential", "joint"):
        monkeypatch.setattr(Inverter, "_init_method", method)
        sim = _run(tmp_path / method, "LCL_static", "fault")
        x0[method] = np.asarray(sim.x_full)[:, 0]
    assert np.abs(x0["sequential"] - x0["joint"]).max() < 1e-9, (
        "sequential and joint init disagree on the LCL_static operating point"
    )


@pytest.mark.parametrize(
    "disturbance, t_dist, after_atol",
    [
        ("fault", 4.0, 5e-3),  # large disturbance: ~1e-3 after settling
        ("load", 2.0, 1e-3),   # gentle disturbance: ~5e-5 (reduction ~exact)
    ],
)
def test_lcl_static_quasi_static_reduction(tmp_path, disturbance, t_dist, after_atol):
    """The slow quantities of LCL_static and dynamic LCL (same static network)
    are machine-identical before the disturbance and re-converge after the fast
    transient settles -- they differ only during the fast transient."""
    dyn = _run(tmp_path / "dyn", "LCL", disturbance)
    sta = _run(tmp_path / "sta", "LCL_static", disturbance)

    n_pre = int((t_dist - 0.5) / TS)   # well before the disturbance
    n_post = int((t_dist + 0.5) / TS)  # after the fast transient has settled

    for idx, state in SLOW:
        a = _dev_state(dyn, idx, state)
        b = _dev_state(sta, idx, state)
        assert np.abs(a[:n_pre] - b[:n_pre]).max() < 1e-9, (
            f"{idx}.{state}: differs before the disturbance (should be the same "
            "quasi-static operating point)"
        )
        assert np.abs(a[n_post:] - b[n_post:]).max() < after_atol, (
            f"{idx}.{state}: slow envelope did not re-converge after settling"
        )
