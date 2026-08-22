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

"""ZIP-aware LOAD disturbance handler — comprehensive tests.

Exercises `Dae.dist_load` across every load-model variant, the two
line_dyn branches, sign conventions, and error handling.

Strategy: each test programmatically builds a one-scenario testcase
under `tmp_path` by copying the frozen `3_bus_loadstep/` fixture and
rewriting the `StaticZIP` line (or substituting `StaticLoadImpedance`
/ `StaticLoadPower`) plus the disturbance line. This avoids a
fixture-folder explosion while keeping the test inputs reproducible —
the test body is the source of truth.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil

import numpy as np
import pytest

from hermess.config import config
from hermess.run import run

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
TEMPLATE = FIXTURE_ROOT / "3_bus_loadstep"

BUS2_IDX = 1  # 0-based bus index in the 3-bus grid (bus 2 is the loaded one)


# -------------------------------------------------------------------- helpers


def _stage(
    tmp_path: Path,
    *,
    load_line: str | None = None,
    bus_init_line: str | None = None,
    sim_dist: str | None = None,
) -> Path:
    """Stage a scenario folder under tmp_path.

    Copies the 3_bus_loadstep template; optionally rewrites the load
    line for bus 2, the BusInit line for bus 2, and the entire
    sim_dist.txt content.

    The default 3-bus fixture has a 100 MW + 10 MVAr load at bus 2.
    For pure-P or pure-I share variants, this baseline is past the
    static voltage-stability limit (a known property of constant-power
    loads near the grid's PV nose); use *bus_init_line* to dial the
    baseline back into the stable region for those tests.
    """
    scen = tmp_path / "scenario"
    scen.mkdir(parents=True, exist_ok=False)
    for name in ("sim_param.txt", "sim_dist.txt", "est_param.txt", "est_dist.txt"):
        src = TEMPLATE / name
        if src.exists():
            (scen / name).write_text(src.read_text())

    sp = scen / "sim_param.txt"
    text = sp.read_text()

    if load_line is not None:
        text = re.sub(
            r"^StaticZIP,\s*bus\s*=\s*\"2\".*$",
            load_line,
            text,
            count=1,
            flags=re.MULTILINE,
        )

    if bus_init_line is not None:
        text = re.sub(
            r"^BusInit,\s*bus\s*=\s*\"2\".*$",
            bus_init_line,
            text,
            count=1,
            flags=re.MULTILINE,
        )

    sp.write_text(text)

    if sim_dist is not None:
        (scen / "sim_dist.txt").write_text(sim_dist.rstrip() + "\n")

    return tmp_path


# Stable baseline load magnitudes for the non-Z variants. The default
# 100 MW + 10 MVAr at bus 2 lives near the static voltage-stability
# limit when expressed as pure-P / pure-I; scale back so each variant
# has a comfortable operating point.
_LIGHT_BASELINE = 'BusInit, bus = "2",\tp = 20,\tq = 5,\ttype = "PQ"'


def _base_cfg(tmp_path: Path, **overrides):
    """Return a config that runs the staged scenario on the sim side."""
    kwargs = dict(
        testsystemfile="scenario",
        system_root=tmp_path,
        omega_mode="nom",
        line_dyn=False,
        incl_lim=True,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        int_scheme_sim="idas",
        ts=0.005,
        T_start=0.0,
        T_end=2.0,
        log_level="WARNING",
        print_power_flow=False,
    )
    kwargs.update(overrides)
    return config.updated(**kwargs)


def _bus_voltage_magnitude(sim, bus_idx: int, k: int) -> float:
    return float(np.hypot(sim.y_full[2 * bus_idx, k], sim.y_full[2 * bus_idx + 1, k]))


def _pre_post_voltages(sim, bus_idx: int = BUS2_IDX) -> tuple[float, float]:
    """Return (|V| at t ≈ 0.5s, |V| at t = T_end)."""
    pre_idx = int(0.5 / sim.t)  # well before t=1.0 disturbance
    post_idx = -1
    return (
        _bus_voltage_magnitude(sim, bus_idx, pre_idx),
        _bus_voltage_magnitude(sim, bus_idx, post_idx),
    )


# -------------------------------------------------------------------- tests


# ---------- per-share-type, line_dyn=False --------------------------------


def test_pure_z_load_step_converges(tmp_path):
    """Pure-Z load + 30 MW step. Linear KCL — no PV nose, IDA converges.
    The 3-bus grid is tightly coupled, so the steady-state voltage drop
    is modest (~0.01 pu); the key invariants are (a) the sim runs to
    completion without IDA_CONV_FAIL and (b) voltage sags (not rises).
    """
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0',
    )
    sim = run(_base_cfg(tmp_path))
    assert np.all(np.isfinite(sim.x_full))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post < v_pre - 1e-3, (
        f"Voltage should sag after Z load step: pre={v_pre:.6f}, post={v_post:.6f}"
    )
    assert v_post > 0.5  # not collapsed


def test_pure_p_load_large_step_dae_raises(tmp_path):
    """Pure-P with the heavy default 100 MW baseline + 30 MW step under
    the DAE formulation (line_dyn=False / idas). IDA must fail. This
    confirms (a) the user's "P" choice is honoured by the handler
    (not silently swallowed) and (b) the well-known DAE-side numerical
    fragility of constant-P loads on a small grid is surfaced as an
    error rather than masked.
    """
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 0.0, i_share = 0.0, p_share = 1.0',
    )
    with pytest.raises(RuntimeError, match="IDA"):
        run(_base_cfg(tmp_path))


def test_pure_p_small_step_dae_converges(tmp_path):
    """Pure-P with a small (1 MW) baseline and step under DAE
    (line_dyn=False / idas) — exercises the P-share branch of
    dist_load where IDA's algebraic-IC computation can still bridge
    the disturbance cleanly.
    """
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 0.0, i_share = 0.0, p_share = 1.0',
        bus_init_line='BusInit, bus = "2",\tp = 1,\tq = 0,\ttype = "PQ"',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 1, q_delta = 0',
    )
    sim = run(_base_cfg(tmp_path))
    assert np.all(np.isfinite(sim.x_full))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post < v_pre - 1e-5


def test_pure_i_small_step_dae_converges(tmp_path):
    """Pure-I with a 2 MW step under DAE (line_dyn=False / idas).
    Larger pure-I steps trigger IDA Newton failure at the disturbance
    boundary (the atan2/cos/sin nonlinearity in gcall_i makes
    consistent-IC computation across a step harder than for a Z
    increment), so we test the small-step regime here.
    """
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 0.0, i_share = 1.0, p_share = 0.0',
        bus_init_line=_LIGHT_BASELINE,
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 2, q_delta = 0',
    )
    sim = run(_base_cfg(tmp_path))
    assert np.all(np.isfinite(sim.x_full))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post < v_pre - 1e-5


def test_pure_i_large_step_line_dyn_true_converges(tmp_path):
    """Pure-I with a 30 MW step under dynamic lines (line_dyn=True /
    cvodes). The ODE formulation has no algebraic-IC computation, so
    even large pure-I steps integrate cleanly. Establishes that the
    handler's I-share math is correct — the DAE-side failures
    elsewhere in this file are an IDA convergence property, not a
    dist_load math error.
    """
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 0.0, i_share = 1.0, p_share = 0.0',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 30, q_delta = 0',
    )
    cfg = _base_cfg(
        tmp_path,
        line_dyn=True,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_end=1.2,
        incl_lim=False,
    )
    sim = run(cfg)
    assert np.all(np.isfinite(sim.x_full))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post < v_pre - 1e-4


def test_mixed_z_dominant_zip_load_step_converges(tmp_path):
    """Mixed Z/I/P shares with Z-dominant (0.8/0.1/0.1). The Z anchor
    keeps the baseline stable while still exercising the I and P
    branches of dist_load. Verifies that the share-apportioned
    increment correctly sags the bus voltage."""
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 0.8, i_share = 0.1, p_share = 0.1',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 20, q_delta = 0',
    )
    sim = run(_base_cfg(tmp_path))
    assert np.all(np.isfinite(sim.x_full))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post < v_pre - 1e-3


# ---------- legacy load classes ------------------------------------------


def test_legacy_static_load_impedance_treated_as_z_share_1(tmp_path):
    """`StaticLoadImpedance` should be treated as z=1 (and produce results
    indistinguishable from `StaticZIP, z_share=1`)."""
    # ZIP-z=1 reference
    _stage(
        tmp_path / "zip",
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0',
    )
    sim_zip = run(_base_cfg(tmp_path / "zip"))

    # Legacy StaticLoadImpedance scenario
    _stage(
        tmp_path / "leg",
        load_line='StaticLoadImpedance, bus = "2"',
    )
    sim_leg = run(_base_cfg(tmp_path / "leg"))

    # Voltages should agree to numerical noise
    v_zip = np.hypot(sim_zip.y_full[2 * BUS2_IDX], sim_zip.y_full[2 * BUS2_IDX + 1])
    v_leg = np.hypot(sim_leg.y_full[2 * BUS2_IDX], sim_leg.y_full[2 * BUS2_IDX + 1])
    assert np.allclose(v_zip, v_leg, atol=1e-8)


def test_legacy_static_load_power_treated_as_p_share_1(tmp_path):
    """`StaticLoadPower` must be inferred as p=1 and produce numerics
    indistinguishable from an explicit `StaticZIP(p_share=1)` of the
    same rated power. Run both on a small-step regime where the
    P-share branch converges cleanly, then compare voltage
    trajectories.
    """
    common_dist = 'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 1, q_delta = 0'
    light = 'BusInit, bus = "2",\tp = 1,\tq = 0,\ttype = "PQ"'

    _stage(
        tmp_path / "zip",
        load_line='StaticZIP, bus = "2", z_share = 0.0, i_share = 0.0, p_share = 1.0',
        bus_init_line=light,
        sim_dist=common_dist,
    )
    sim_zip = run(_base_cfg(tmp_path / "zip"))

    _stage(
        tmp_path / "leg",
        load_line='StaticLoadPower, bus = "2"',
        bus_init_line=light,
        sim_dist=common_dist,
    )
    sim_leg = run(_base_cfg(tmp_path / "leg"))

    v_zip = np.hypot(sim_zip.y_full[2 * BUS2_IDX], sim_zip.y_full[2 * BUS2_IDX + 1])
    v_leg = np.hypot(sim_leg.y_full[2 * BUS2_IDX], sim_leg.y_full[2 * BUS2_IDX + 1])
    assert np.allclose(v_zip, v_leg, atol=1e-9)


# ---------- error handling ------------------------------------------------


def test_no_load_at_bus_raises(tmp_path):
    """LOAD disturbance at a bus without any load device (here: bus 1,
    the slack generator) must raise a clear ValueError."""
    _stage(
        tmp_path,
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "1", p_delta = 5, q_delta = 0',
    )
    with pytest.raises(ValueError, match="no load device"):
        run(_base_cfg(tmp_path))


# ---------- semantics: stacking, sign conventions, negative steps --------


def test_stacking_two_load_events(tmp_path):
    """Two LOAD events at the same bus should stack (post-second total
    demand = P₀ + 2·Δp)."""
    # Two events: +10 MW at t=1.0, +10 MW at t=1.5
    two_events = (
        'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 10, q_delta = 0\n'
        'Disturbance, time = 1.5, type = "LOAD", bus = "2", p_delta = 10, q_delta = 0\n'
    )
    _stage(
        tmp_path / "two",
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0',
        sim_dist=two_events,
    )
    sim_two = run(_base_cfg(tmp_path / "two"))

    # One event of 20 MW for comparison
    _stage(
        tmp_path / "one",
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 20, q_delta = 0',
    )
    sim_one = run(_base_cfg(tmp_path / "one"))

    # After t=1.5 both runs should converge to the same steady state
    # (within transient damping). Test the final voltage.
    v_two_final = _bus_voltage_magnitude(sim_two, BUS2_IDX, -1)
    v_one_final = _bus_voltage_magnitude(sim_one, BUS2_IDX, -1)
    assert abs(v_two_final - v_one_final) < 0.02, (
        f"Two-step stacked outcome diverges from single 20MW step: "
        f"two={v_two_final}, one={v_one_final}"
    )


def test_negative_p_delta_raises_voltage(tmp_path):
    """A negative p_delta = load reduction should RAISE the bus voltage."""
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = -20, q_delta = 0',
    )
    sim = run(_base_cfg(tmp_path))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post > v_pre + 1e-4, (
        f"Voltage should rise after load reduction: pre={v_pre:.6f}, post={v_post:.6f}"
    )


def test_q_delta_sign_convention_inductive(tmp_path):
    """Positive q_delta = inductive consumption, should drop voltage
    magnitude (consistent with gcall_z's b convention)."""
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 0, q_delta = 20',
    )
    sim = run(_base_cfg(tmp_path))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post < v_pre - 1e-4, (
        f"Positive q_delta should drop voltage: pre={v_pre:.6f}, post={v_post:.6f}"
    )


# ---------- line_dyn=True path -------------------------------------------


def test_line_dyn_true_z_share(tmp_path):
    """The line_dyn=True branch of dist_load must also be ZIP-aware
    (it modifies dae.fnode via the ω_b / B_sum capacitor coupling
    instead of dae.g). Use Z-only + modest step + short horizon."""
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 10, q_delta = 0',
    )
    cfg = _base_cfg(
        tmp_path,
        line_dyn=True,
        int_scheme_sim="cvodes",
        ts=0.0001,
        T_end=1.05,
    )
    sim = run(cfg)
    assert np.all(np.isfinite(sim.x_full))


# =========================================================================
# Independent Q-side shares
# =========================================================================
#
# These tests cover the optional `p_share_q` / `i_share_q` / `z_share_q`
# fields on StaticZIP (the IEEE-polynomial-ZIP-style extension).
#
# Two layers of testing:
#   (a) Unit tests of the q_share() resolver on a freshly-instantiated
#       StaticZIP — pure logic, no simulation.
#   (b) End-to-end tests that stage a sim_param.txt with explicit Q-side
#       shares and verify the full pipeline (finit_sub decomposition →
#       dist_load Q-axis weighting → KCL response).


def test_q_share_resolver_falls_back_to_p_side():
    """q_share(branch, k) returns the P-side share when Q-side is NaN
    (the default / 'not declared' case)."""
    from hermess.devices.static import StaticZIP
    dev = StaticZIP()
    dev.z_share = np.array([0.7, 0.3])
    dev.i_share = np.array([0.2, 0.4])
    dev.p_share = np.array([0.1, 0.3])
    dev.z_share_q = np.array([np.nan, np.nan])
    dev.i_share_q = np.array([np.nan, np.nan])
    dev.p_share_q = np.array([np.nan, np.nan])
    for k in (0, 1):
        assert dev.q_share("z", k) == dev.z_share[k]
        assert dev.q_share("i", k) == dev.i_share[k]
        assert dev.q_share("p", k) == dev.p_share[k]


def test_q_share_resolver_uses_explicit_q_side():
    """q_share(branch, k) returns the Q-side value when it's set (not NaN)."""
    from hermess.devices.static import StaticZIP
    dev = StaticZIP()
    dev.z_share   = np.array([0.5])
    dev.i_share   = np.array([0.0])
    dev.p_share   = np.array([0.5])
    dev.z_share_q = np.array([1.0])
    dev.i_share_q = np.array([0.0])
    dev.p_share_q = np.array([0.0])
    assert dev.q_share("z", 0) == 1.0
    assert dev.q_share("i", 0) == 0.0
    assert dev.q_share("p", 0) == 0.0


def test_q_share_resolver_mixed_per_entry():
    """Different entries can independently opt in or out of Q-side shares."""
    from hermess.devices.static import StaticZIP
    dev = StaticZIP()
    dev.z_share   = np.array([0.6, 1.0])
    dev.i_share   = np.array([0.0, 0.0])
    dev.p_share   = np.array([0.4, 0.0])
    dev.z_share_q = np.array([np.nan, 0.0])
    dev.i_share_q = np.array([np.nan, 0.0])
    dev.p_share_q = np.array([np.nan, 1.0])
    assert dev.q_share("z", 0) == 0.6     # fallback
    assert dev.q_share("p", 0) == 0.4     # fallback
    assert dev.q_share("z", 1) == 0.0     # explicit
    assert dev.q_share("p", 1) == 1.0     # explicit


def test_q_share_falls_back_in_dist_load(tmp_path):
    """A bus declared with only P-side shares (no _share_q fields) must
    produce numerically identical dist_load behaviour to an explicit
    redeclaration where the Q-side equals the P-side. This is the
    backward-compatibility property — the fallback path can't drift
    from the historical single-share calibration."""
    common_dist = 'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 5, q_delta = 1'

    _stage(
        tmp_path / "implicit",
        load_line='StaticZIP, bus = "2", z_share = 1.0',
        sim_dist=common_dist,
    )
    sim_a = run(_base_cfg(tmp_path / "implicit"))

    _stage(
        tmp_path / "explicit",
        load_line='StaticZIP, bus = "2", z_share = 1.0, i_share = 0.0, p_share = 0.0, '
                  'z_share_q = 1.0, i_share_q = 0.0, p_share_q = 0.0',
        sim_dist=common_dist,
    )
    sim_b = run(_base_cfg(tmp_path / "explicit"))

    assert np.allclose(sim_a.x_full, sim_b.x_full, atol=1e-10)
    assert np.allclose(sim_a.y_full, sim_b.y_full, atol=1e-10)


def test_q_only_step_routes_through_q_share(tmp_path):
    """A pure Q-only LOAD step (p_delta=0, q_delta>0) on a bus with
    z_share_q = 1.0 (vs the implicit z_share_q = 0.5) should produce a
    different voltage response. Confirms the Q-side share is actually
    wired into dist_load's Q-axis contributions.

    Uses a modest step (q_delta=3) at the default 100 MW + 10 MVAr baseline:
    a larger step here sits at the static voltage-stability nose, where the
    integration is on a knife-edge. The routing signal at this step is small
    (~3e-6) but ~10 orders above the pre-disturbance match (~1e-15), so it is an
    unambiguous, robust check that Q routing changes the response."""
    common_dist = 'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 0, q_delta = 3'

    _stage(
        tmp_path / "old",
        load_line='StaticZIP, bus = "2", z_share = 0.5, p_share = 0.5',
        sim_dist=common_dist,
    )
    sim_old = run(_base_cfg(tmp_path / "old"))

    _stage(
        tmp_path / "qz1",
        load_line='StaticZIP, bus = "2", z_share = 0.5, p_share = 0.5, '
                  'z_share_q = 1.0, p_share_q = 0.0',
        sim_dist=common_dist,
    )
    sim_qz = run(_base_cfg(tmp_path / "qz1"))

    v_old = np.hypot(sim_old.y_full[2 * BUS2_IDX], sim_old.y_full[2 * BUS2_IDX + 1])
    v_qz  = np.hypot(sim_qz.y_full[2 * BUS2_IDX],  sim_qz.y_full[2 * BUS2_IDX + 1])

    # Pre-disturbance values must match (init is independent of dist_load).
    assert np.isclose(v_old[100], v_qz[100], atol=1e-6)
    # Post-disturbance steady state must differ because Q routing differs.
    # Signal is ~3e-6 at this step/operating point; threshold sits well above
    # the ~1e-15 pre-disturbance match yet below the routing signal.
    assert abs(v_old[-1] - v_qz[-1]) > 1e-6, (
        f"Voltages should differ when Q is routed differently: "
        f"old={v_old[-1]:.6f}, qz={v_qz[-1]:.6f}"
    )


def test_heating_load_z_for_p_p_for_q(tmp_path):
    """The 'heating with controls' scenario:
    z_share=1 / p_share=0 (active power purely resistive) plus
    z_share_q=0 / p_share_q=1 (reactive power purely constant-power).
    End-to-end sanity: init succeeds, small LOAD step simulates
    cleanly, voltage moves the right direction."""
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 1.0, p_share = 0.0, '
                  'z_share_q = 0.0, p_share_q = 1.0',
        bus_init_line='BusInit, bus = "2",\tp = 5,\tq = 1,\ttype = "PQ"',
        sim_dist='Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 2, q_delta = 0.5',
    )
    sim = run(_base_cfg(tmp_path))
    assert np.all(np.isfinite(sim.x_full))
    v_pre, v_post = _pre_post_voltages(sim)
    assert v_post < v_pre - 1e-5


def test_q_side_sum_to_1_warning(tmp_path, caplog):
    """If Q-side shares don't sum to 1.0, StaticZIP.finit logs a warning.
    We only need init to fire — no disturbance involved — so empty out
    sim_dist and use a light pure-Z baseline that's robust to the
    deliberate Q-side misconfiguration."""
    import logging
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 1.0, p_share = 0.0, '
                  'z_share_q = 0.3, p_share_q = 0.4',   # Q sum = 0.7 (and i_share_q falls back to i_share=0)
        bus_init_line='BusInit, bus = "2",\tp = 5,\tq = 1,\ttype = "PQ"',
        sim_dist="# no disturbance — only init exercises the warning",
    )
    with caplog.at_level(logging.WARNING):
        run(_base_cfg(tmp_path))
    qside_warnings = [
        rec for rec in caplog.records
        if "Q-side shares" in rec.message and "≠ 1.0" in rec.message
    ]
    assert qside_warnings, (
        f"Expected a Q-side sum-to-1 warning; got log records:\n"
        + "\n".join(rec.message for rec in caplog.records[:20])
    )


def test_p_side_sum_to_1_warning_unchanged_behaviour(tmp_path, caplog):
    """The sum-to-1 warning fires for the P-side too, mirroring the Q check."""
    import logging
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 0.3, p_share = 0.4',  # P sum = 0.7
        bus_init_line='BusInit, bus = "2",\tp = 5,\tq = 1,\ttype = "PQ"',
        sim_dist="# no disturbance — only init exercises the warning",
    )
    with caplog.at_level(logging.WARNING):
        run(_base_cfg(tmp_path))
    pside_warnings = [
        rec for rec in caplog.records
        if "P-side shares" in rec.message and "≠ 1.0" in rec.message
    ]
    assert pside_warnings


def test_mixed_grammar_old_and_new_in_one_file(tmp_path):
    """Verify the parser handles a sim_param.txt mixing old-style and
    new-style StaticZIP lines side by side — entries with no
    `*_share_q` fields fall back via NaN, entries with them use them.
    Use Z-dominant shares + a light baseline so the P-share portion
    doesn't tip bus 2 into the constant-P-instability region."""
    _stage(
        tmp_path,
        load_line='StaticZIP, bus = "2", z_share = 0.9, p_share = 0.1, '
                  'z_share_q = 1.0, p_share_q = 0.0',
        bus_init_line='BusInit, bus = "2",\tp = 10,\tq = 1,\ttype = "PQ"',
        sim_dist="# no disturbance — exercising only parser + finit_sub",
    )
    sim = run(_base_cfg(tmp_path))
    assert np.all(np.isfinite(sim.x_full))


def test_legacy_class_unaffected_by_q_share_extension(tmp_path):
    """`StaticLoadImpedance` has no q_share() method — the dist_load
    handler must fall back to identical P/Q shares (z=1 across both
    sides) and produce results equivalent to a `StaticZIP(z=1)` with
    no _share_q fields. Confirms the hasattr() guard works."""
    common_dist = 'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 5, q_delta = 1'

    _stage(
        tmp_path / "legacy",
        load_line='StaticLoadImpedance, bus = "2"',
        sim_dist=common_dist,
    )
    sim_l = run(_base_cfg(tmp_path / "legacy"))

    _stage(
        tmp_path / "zip",
        load_line='StaticZIP, bus = "2", z_share = 1.0',
        sim_dist=common_dist,
    )
    sim_z = run(_base_cfg(tmp_path / "zip"))

    v_l = np.hypot(sim_l.y_full[2 * BUS2_IDX], sim_l.y_full[2 * BUS2_IDX + 1])
    v_z = np.hypot(sim_z.y_full[2 * BUS2_IDX], sim_z.y_full[2 * BUS2_IDX + 1])
    assert np.allclose(v_l, v_z, atol=1e-8)
