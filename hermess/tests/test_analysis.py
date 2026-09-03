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

"""The hermess.analysis module: signal addressing, tables, plots and the
system-file helpers, exercised on one small quiet run."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

import hermess
from hermess import analysis as an

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def dae():
    return hermess.simulate(
        "3bus_loadstep", T_end=1.5, ts=0.005, quiet=True,
        small_signal_analysis=True,
    )


# ---------------------------------------------------------------- catalog


def test_catalog_covers_states_buses_and_branches(dae):
    names = an.signal_names(dae, None)
    assert "SG1:omega" in names
    assert "bus2:v" in names
    assert any(n.startswith("line") and n.endswith(":P") for n in names)
    table = an.signals(dae)
    assert set(table.columns) == {"signal", "owner", "quantity", "unit", "kind", "description"}
    assert set(an.signals(dae, kind="state")["kind"]) == {"state"}


def test_selector_grammar(dae):
    assert an.signal_names(dae, "SG1:omega") == ["SG1:omega"]
    assert an.signal_names(dae, "f") == ["SG1:f", "GFMI2:f"]
    assert an.signal_names(dae, "bus*:v") == ["bus1:v", "bus2:v", "bus3:v"]
    # case-insensitive, prefixless bus, dict, device object, (device, state)
    assert an.signal_names(dae, "sg1:OMEGA") == ["SG1:omega"]
    assert an.signal_names(dae, "3:v") == ["bus3:v"]
    assert an.signal_names(dae, {"GFMI2": ["Pc_tilde", "f"]}) == ["GFMI2:Pc_tilde", "GFMI2:f"]
    dev = an.get_device(dae, "SG1")
    assert "SG1:omega" in an.signal_names(dae, dev)
    assert an.signal_names(dae, (dev, "omega")) == ["SG1:omega"]
    # lists deduplicate and keep order
    assert an.signal_names(dae, ["SG1:omega", "SG1:omega", "bus1:v"]) == ["SG1:omega", "bus1:v"]


def test_unknown_selector_suggests(dae):
    with pytest.raises(KeyError, match="omega"):
        an.signal_names(dae, "SG1:omga")


# ---------------------------------------------------------------- data access


def test_get_dataframe_and_csv(dae, tmp_path):
    series = an.get(dae, "SG1:omega")["SG1:omega"]
    assert series.shape == dae.time_steps.shape
    df = an.to_dataframe(dae, "*:f", every=10)
    assert df.index.name == "t"
    assert list(df.columns) == ["SG1:f", "GFMI2:f"]
    out = an.to_csv(dae, tmp_path / "f.csv", "*:f", every=10)
    head = out.read_text().splitlines()[0]
    assert head.startswith("t,") and "SG1:f" in head


def test_metrics(dae):
    m = an.metrics(dae)
    assert {"pre-event", "extreme", "deviation", "final"} <= set(m.columns)
    assert "SG1:f" in m.index
    assert abs(m.loc["SG1:f", "pre-event"] - 50.0) < 1e-6


def test_frequency_and_raw_access(dae):
    sg = an.get_device(dae, "SG1")
    gfm = an.get_device(dae, "GFMI2")
    f_sg = an.frequency_hz(dae, sg)
    np.testing.assert_allclose(f_sg, np.asarray(sg.xf["omega"][0]) * 50.0)
    f_gfm = an.frequency_hz(dae, gfm)
    assert abs(f_gfm[0] - 50.0) < 1e-6
    assert an.bus_voltage(dae, "3").shape == dae.time_steps.shape
    assert an.state_index(sg, "omega") == int(sg.omega[0])
    assert "SG1" in an.device_label(sg)
    with pytest.raises(KeyError):
        an.get_device(dae, "nope")


def test_summary_and_events(dae):
    assert dae.events == [(1.0, "LOAD", "2")]
    text = an.summary(dae)
    assert "3 buses" in text and "load at 2" in text


# ---------------------------------------------------------------- plotting


def test_plot_functions_smoke(dae):
    an.plot(dae, ["*:f", "bus*:v"])
    an.plot(dae, "SG1:omega", title="one")
    an.plot_states(dae, "GFMI2")
    an.compare({"a": dae, "b": dae}, "GFMI2:f")
    an.plot_frequency(dae)
    an.plot_voltages(dae, buses=["1", "3"])
    an.plot_active_power(dae)
    an.plot_modes(dae, fmax=5)
    an.plot_system(dae)
    an.plot_system(dae, colors={"machine": "k"}, device_labels="type",
                   color_by="bus*:v", annotate_branches=True)
    plt.close("all")


def test_compare_uses_the_active_color_cycle(dae):
    axs = an.compare({"a": dae, "b": dae}, "GFMI2:f")
    lines = axs.ravel()[0].get_lines()
    cycle = matplotlib.rcParams["axes.prop_cycle"].by_key()["color"]
    assert lines[0].get_color() == cycle[0]
    assert lines[1].get_color() == cycle[1]
    plt.close("all")


# ---------------------------------------------------------------- tables


def test_small_signal_tables(dae):
    modes = an.small_signal(dae)
    assert modes and "zeta" in modes[0]
    table = an.modal_table(dae, n=5)
    assert len(table) == 5 and "dominant states" in table.columns
    A = an.state_matrix(dae)
    assert A.shape[0] == A.shape[1]
    frame = an.state_matrix(dae, as_frame=True)
    assert list(frame.index) == list(frame.columns)
    part = an.participation_table(dae, mode=1)
    assert len(part)
    assert an.power_flow_table(dae, "bus").shape[0] == 3
    assert an.power_flow_table(dae, "branch").shape[0] == 3
    with pytest.raises(KeyError):
        an.power_flow_table(dae, "nope")


# ---------------------------------------------------------------- system files


def test_copy_show_and_edit_system(tmp_path, capsys):
    root = an.copy_system("3bus_loadstep", dest=tmp_path / "systems")
    assert (root / "3bus_loadstep" / "sim_param.txt").exists()
    # editing the copy leaves the package untouched
    an.set_param(root, "3bus_loadstep", "GFMI2", Kp=0.05, note='"x"')
    text = (root / "3bus_loadstep" / "sim_param.txt").read_text()
    assert "Kp = 0.05" in text and 'note = "x"' in text
    assert "Kp = 0.05" not in (an.PACKAGE_SYSTEMS / "3bus_loadstep" / "sim_param.txt").read_text()
    with pytest.raises(KeyError):
        an.set_param(root, "3bus_loadstep", "NOPE", Kp=1)
    an.set_disturbances(root, "3bus_loadstep", [
        'Disturbance, time = 2.0, type = "SETPOINT", device = "GFMI2", param = "Pref", value = 0.7',
        'Disturbance, time = 1.0, type = "FAULT_LINE", bus_i = "1", bus_j = "2", y = 30',
    ])
    events = an.read_events(root, "3bus_loadstep")
    assert events == [(1.0, "FAULT_LINE", "1-2"), (2.0, "SETPOINT", "GFMI2:Pref = 0.7")]
    an.show_system(root, "3bus_loadstep")
    shown = capsys.readouterr().out
    assert "GFMI2" in shown and "©" not in shown and "Licensed under" not in shown


def _shipped_files(name: str) -> dict:
    folder = hermess.SYSTEMS_DIR / name
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_helpers_refuse_to_edit_the_shipped_systems():
    """Nothing in hermess.analysis can write into the installed package."""
    before = _shipped_files("3bus_loadstep")
    row = 'Disturbance, time = 1.0, type = "LOAD", bus = "2", p_delta = 99'

    with pytest.raises(PermissionError, match="copy_system"):
        an.set_param(hermess.SYSTEMS_DIR, "3bus_loadstep", "GFMI2", Kp=99.0)
    with pytest.raises(PermissionError):
        an.set_disturbances(hermess.SYSTEMS_DIR, "3bus_loadstep", [row])
    with pytest.raises(PermissionError):
        an.copy_system("3bus_loadstep", dest=hermess.SYSTEMS_DIR)
    with pytest.raises(PermissionError):
        an.copy_system("3bus_loadstep", dest=hermess.SYSTEMS_DIR, overwrite=True)
    # A path that only resolves into the package (relative parts, a string)
    # is caught the same way.
    with pytest.raises(PermissionError):
        an.set_param(str(hermess.SYSTEMS_DIR / "3bus" / ".."), "3bus_loadstep", "GFMI2", Kp=99.0)
    with pytest.raises(PermissionError):
        an.copy_system("3bus_loadstep", dest=hermess.SYSTEMS_DIR / "sea14gen", overwrite=True)

    assert (hermess.SYSTEMS_DIR / "3bus_loadstep").is_dir()
    assert _shipped_files("3bus_loadstep") == before


def test_quiet_run_is_silent(capfd):
    hermess.simulate("3bus_loadstep", T_end=0.1, ts=0.01, quiet=True)
    captured = capfd.readouterr()
    assert "Simulation" not in captured.err
