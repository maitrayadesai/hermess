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

"""The package-level entry points a user meets first.

Covers ``hermess.list_systems`` / ``hermess.simulate``, registration of
user-defined models (``hermess.register`` and the loader path that consults it),
the analysis outputs published on the finished object (the reduced state matrix,
the participation table, the power-flow tables, the device power expressions),
and the guarantee that importing the package leaves the caller's matplotlib
backend alone.
"""

from pathlib import Path

import casadi as ca
import numpy as np
import pytest

import hermess
from hermess.config import config
from hermess.devices.inverter_angle import DroopAngle
from hermess.devices.static import StaticZIP
from hermess.registry import DEVICE_REGISTRY, register, registered, unregister
from hermess.run import run

FIXTURE_ROOT = Path(__file__).parent / "fixtures"

_COMMON = dict(
    system_root=FIXTURE_ROOT,
    fn=50,
    Sb=100,
    ts=0.005,
    T_start=0.0,
    T_end=2.0,
    int_scheme_sim="idas",
    plot=False,
    plot_voltage=False,
    plot_diff=False,
    log_level="ERROR",
    incl_lim=False,
    line_dyn=False,
    print_power_flow=False,
)


def _run_3bus(**overrides):
    cfg = config.updated(testsystemfile="3_bus", **{**_COMMON, **overrides})
    return run(cfg)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def test_list_systems_finds_the_shipped_cases():
    names = hermess.list_systems()
    assert "3bus" in names and "ieee39" in names
    # nested folders are addressed by their relative path
    assert any(n.startswith("sea14gen/") for n in names)
    # every name is usable as testsystemfile
    for name in names:
        assert (hermess.SYSTEMS_DIR / name / "sim_param.txt").is_file()


def test_list_systems_accepts_another_root():
    assert "3_bus" in hermess.list_systems(FIXTURE_ROOT)


def test_simulate_one_liner_runs_and_defaults_to_quiet(capsys):
    dae = hermess.simulate("3_bus", system_root=FIXTURE_ROOT, T_end=1.0, ts=0.01,
                           line_dyn=False, incl_lim=False, log_level="ERROR")
    assert dae.nx > 0 and dae.x_full.shape[1] == dae.nts
    # plotting and the power-flow print are off unless asked for
    assert "Power flow for initialization" not in capsys.readouterr().out


def test_simulate_overrides_reach_the_config():
    dae = hermess.simulate("3_bus", system_root=FIXTURE_ROOT, T_end=1.5, ts=0.01,
                           line_dyn=True, incl_lim=False, log_level="ERROR")
    assert dae.T_end == 1.5 and dae.line_dyn is True


def test_import_does_not_hijack_the_matplotlib_backend():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import importlib

    import hermess.run as hermess_run

    importlib.reload(hermess_run)
    assert matplotlib.get_backend().lower() == "agg"


# ---------------------------------------------------------------------------
# Registration of user-defined models
# ---------------------------------------------------------------------------


class _AliasDroop(DroopAngle):
    """A user-written angle source (here: the shipped droop under another name)."""


def test_register_strategy_makes_it_selectable(tmp_path):
    register(_AliasDroop, "MyDroop")
    try:
        assert "MyDroop" in registered("angle")["angle"]

        # a system that selects the user strategy by name
        src = FIXTURE_ROOT / "IEEE39_bus_inverter"
        case = tmp_path / "case"
        case.mkdir()
        text = (src / "sim_param.txt").read_text()
        assert "GridForming" in text
        lines = []
        for line in text.splitlines():
            if line.startswith("GridForming"):
                line = line.rstrip().rstrip(",") + ', angle = "MyDroop"'
            lines.append(line)
        (case / "sim_param.txt").write_text("\n".join(lines) + "\n")
        (case / "sim_dist.txt").write_text((src / "sim_dist.txt").read_text())

        cfg = config.updated(testsystemfile="case",
                             **{**_COMMON, "system_root": tmp_path, "T_end": 0.5, "line_dyn": True})
        dae = run(cfg)
        gfm = next(d for d in dae.device_list if type(d).__name__ == "GridForming")
        assert isinstance(gfm._angle, _AliasDroop)
        assert "delta_c" in gfm.states
    finally:
        unregister("MyDroop", "angle")
        assert "MyDroop" not in registered("angle")["angle"]


def test_register_defaults_to_the_class_name_and_works_as_a_decorator():
    @register
    class _DecoratedDroop(DroopAngle):
        pass

    try:
        assert "_DecoratedDroop" in registered("angle")["angle"]
    finally:
        unregister("_DecoratedDroop", "angle")


def test_register_accepts_a_device_class():
    class _MyLoad(StaticZIP):
        pass

    register(_MyLoad)
    try:
        assert DEVICE_REGISTRY["_MyLoad"] is _MyLoad
        assert "_MyLoad" in registered()["device (user-registered)"]
    finally:
        unregister("_MyLoad", "device")
        assert "_MyLoad" not in DEVICE_REGISTRY


def test_registered_device_receives_the_strategy_keywords(tmp_path):
    """The loader's registry path must pass strategy selections to the
    constructor exactly like the package-scan path (regression: it used to
    instantiate registered devices with no kwargs, silently dropping them)."""
    from hermess.devices.inverter import GridForming

    class _MyGFM(GridForming):
        """A user-written converter (here: the shipped one under another name)."""

    register(_MyGFM)
    register(_AliasDroop, "MyDroop")
    try:
        src = FIXTURE_ROOT / "3_bus"
        case = tmp_path / "case"
        case.mkdir()
        lines = []
        for line in (src / "sim_param.txt").read_text().splitlines():
            if line.startswith("GridForming"):
                line = "_MyGFM" + line[len("GridForming"):]
                line = line.rstrip().rstrip(",") + ', angle = "MyDroop"'
            lines.append(line)
        (case / "sim_param.txt").write_text("\n".join(lines) + "\n")
        (case / "sim_dist.txt").write_text((src / "sim_dist.txt").read_text())

        cfg = config.updated(testsystemfile="case",
                             **{**_COMMON, "system_root": tmp_path, "T_end": 0.5})
        dae = run(cfg)
        gfm = next(d for d in dae.device_list if type(d).__name__ == "_MyGFM")
        assert isinstance(gfm._angle, _AliasDroop)
    finally:
        unregister("_MyGFM", "device")
        unregister("MyDroop", "angle")


def test_system_root_expands_the_user_home(tmp_path, monkeypatch):
    """The documented ``system_root="~/my_systems"`` form must work."""
    import shutil

    monkeypatch.setenv("HOME", str(tmp_path))
    shutil.copytree(FIXTURE_ROOT / "3_bus", tmp_path / "mysys" / "3_bus")

    assert hermess.list_systems("~/mysys") == ["3_bus"]
    dae = hermess.simulate("3_bus", system_root="~/mysys",
                           **{k: v for k, v in _COMMON.items() if k != "system_root"},
                           )
    assert dae.x_full.shape[1] > 0


def test_register_rejects_an_unrelated_class():
    with pytest.raises(TypeError):
        register(dict)


def test_registered_lists_the_shipped_strategies():
    reg = registered()
    assert {"avr", "governor", "pss", "shaft", "filter", "angle", "voltage", "inner", "pll"} <= set(reg)
    assert "Droop" in reg["angle"] and "PLL" in reg["angle"]
    assert "TGOV1" in reg["governor"] and "IEEEDC1A" in reg["avr"]
    with pytest.raises(KeyError):
        registered("not-a-kind")


# ---------------------------------------------------------------------------
# What a finished run publishes
# ---------------------------------------------------------------------------


def test_state_matrix_is_stored_with_matching_state_names():
    dae = _run_3bus(small_signal_analysis=True)
    assert dae.A is not None
    assert dae.A.shape[0] == dae.A.shape[1] == len(dae.state_names)
    # the stored matrix is the one the reported eigenvalues come from
    assert np.allclose(np.sort_complex(np.linalg.eigvals(dae.A)),
                       np.sort_complex(np.asarray(dae.eigenvalues)))


def test_participation_table():
    dae = _run_3bus(small_signal_analysis=True)
    df = dae.participation_table(mode=1, top=5)
    assert list(df.columns) == ["state", "participation"]
    assert len(df) == 5
    assert set(df["state"]) <= set(dae.state_names)
    assert df["participation"].is_monotonic_decreasing
    # the full column is normalized
    full = dae.participation_table(mode=1, top=None)
    assert full["participation"].sum() == pytest.approx(1.0, abs=1e-3)
    assert df.attrs["mode"] == 1
    with pytest.raises(KeyError):
        dae.participation_table(mode=10**6)


def test_power_flow_tables():
    dae = _run_3bus()
    bus, branch = dae.grid.power_flow_tables(dae)
    assert len(bus) == dae.grid.nn and len(branch) == dae.grid.nb
    assert {"Bus", "V Magnitude (pu)", "P Gen (MW)"} <= set(bus.columns)
    assert {"From Bus", "To Bus", "P Loss (MW)"} <= set(branch.columns)
    # the initialized voltages agree with the operating point of the run
    v0 = np.hypot(np.asarray(dae.yinit)[0:2 * dae.grid.nn:2],
                  np.asarray(dae.yinit)[1:2 * dae.grid.nn:2])
    assert np.allclose(bus["V Magnitude (pu)"].to_numpy(), v0)


def test_print_init_power_flow_still_prints(capsys):
    dae = _run_3bus()
    dae.grid.print_init_power_flow(dae)
    out = capsys.readouterr().out
    assert "Power Flow: Bus Results" in out and "Power Flow: Branch Results" in out


def test_devices_publish_their_electrical_power():
    """Machines expose the air-gap power and converters their terminal powers, as
    symbolic expressions that can be evaluated along a trajectory afterwards."""
    dae = _run_3bus()
    sg = next(d for d in dae.device_list if "Synchronous" in type(d).__name__)
    assert isinstance(sg.Pe, ca.SX) and sg.Pe.shape == (sg.n, 1)

    # evaluated at the operating point, the air-gap power matches the machine's
    # scheduled output (up to the stator loss), i.e. it is the physical quantity.
    f = ca.Function("Pe", [dae.x, dae.y], [sg.Pe])
    pe0 = np.asarray(f(dae.xinit, dae.yinit)).ravel()[0] * float(sg.Sn[0])
    p_bus = float(dae.grid.sf[str(sg.bus[0])][0, 0]) * dae.Sb
    assert pe0 == pytest.approx(p_bus, rel=0.02)


def test_inverters_publish_their_terminal_power():
    cfg = config.updated(testsystemfile="IEEE39_bus_inverter",
                         **{**_COMMON, "T_end": 0.5, "line_dyn": True})
    dae = run(cfg)
    inv = next(d for d in dae.device_list if type(d).__name__ in ("GridForming", "GridSupporting"))
    assert isinstance(inv.Pc, ca.SX) and inv.Pc.shape == (inv.n, 1)
    assert isinstance(inv.Qc, ca.SX) and inv.Qc.shape == (inv.n, 1)

    # Pc_tilde is Pc through the measurement filter, so they agree in steady state
    f = ca.Function("Pc", [dae.x, dae.y], [inv.Pc])
    pc0 = np.asarray(f(dae.xinit, dae.yinit)).ravel()
    assert np.allclose(pc0, np.asarray(dae.xinit)[inv.Pc_tilde[:]], atol=1e-6)


def test_progress_callback_numpy_false_cancels():
    from hermess.errors import SimulationCancelled

    with pytest.raises(SimulationCancelled):
        hermess.simulate(
            "3_bus", system_root=FIXTURE_ROOT, T_end=1.0, ts=0.01,
            progress_callback=lambda fraction: np.bool_(fraction < 0.5),
        )


def test_init_callback_numpy_false_cancels():
    from hermess.errors import SimulationCancelled

    with pytest.raises(SimulationCancelled):
        hermess.simulate(
            "3_bus", system_root=FIXTURE_ROOT, T_end=0.5, ts=0.01,
            init_callback=lambda dae: np.bool_(False),
        )


def test_simulate_prints_no_casadi_numpy_notice(recwarn):
    hermess.simulate("3_bus", system_root=FIXTURE_ROOT, T_end=0.1, ts=0.01)
    notices = [w for w in recwarn
               if "casadi" in str(w.message).lower() and "numpy" in str(w.message).lower()]
    assert not notices
