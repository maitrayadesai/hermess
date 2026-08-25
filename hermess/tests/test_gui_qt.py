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

"""Offscreen smoke tests of the Qt widgets. Skipped when the optional GUI
dependencies (``hermess[gui]``) are not installed."""

import os

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hermess.results import (  # noqa: E402
    DeviceTrajectories,
    SimulationResults,
    SmallSignalResults,
)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    # Keep the tests' QSettings out of the user's real preferences.
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        str(tmp_path_factory.mktemp("qsettings")),
    )
    application = QApplication.instance() or QApplication([])
    application.setOrganizationName("ETH Zurich")
    application.setApplicationName("HERMESS-test")
    yield application


@pytest.fixture()
def results():
    t = np.linspace(0.0, 1.0, 101)
    eigs = np.array([-1.0 + 5.0j, -1.0 - 5.0j, -3.0 + 0.0j])
    modes = [
        {
            "id": 1,
            "members": [0, 1],
            "rep_idx": 0,
            "eig": complex(eigs[0]),
            "sigma": -1.0,
            "omega": 5.0,
            "freq_hz": 5.0 / (2 * np.pi),
            "zeta": 0.196,
            "is_complex": True,
            "participation": np.array([0.7, 0.3]),
            "dominant": [("SM@1:omega", 0.7), ("SM@1:delta", 0.3)],
        },
        {
            "id": 2,
            "members": [2],
            "rep_idx": 2,
            "eig": complex(eigs[2]),
            "sigma": -3.0,
            "omega": 0.0,
            "freq_hz": 0.0,
            "zeta": 1.0,
            "is_complex": False,
            "participation": np.array([0.2, 0.8]),
            "dominant": [("SM@1:delta", 0.8)],
        },
    ]
    return SimulationResults(
        system="demo",
        t=t,
        voltage={"1": np.exp(1j * 0.01 * t), "2": 0.98 * np.exp(1j * 0.02 * t)},
        power={"1": (1.0 + 0.1j) * np.ones_like(t)},
        devices=[
            DeviceTrajectories(
                model="Synchronous_machine_subtransient_model_Sauer_Pai",
                unit="SG1",
                bus="1",
                states={"delta": 0.5 * t, "omega": 1.0 + 0.01 * np.sin(t)},
            )
        ],
        small_signal=SmallSignalResults(
            eigenvalues=eigs,
            state_names=["SM@1:omega", "SM@1:delta"],
            participation=np.column_stack(
                [m["participation"] for m in modes for _ in m["members"]]
            ),
            modes=modes,
        ),
    )


def test_timedomain_tab(app, results):
    from PySide6.QtCore import Qt

    from hermess.gui.timedomain_tab import TimeDomainTab

    tab = TimeDomainTab()
    tab.set_results(results)
    # Check the first voltage signal programmatically and expect one curve.
    tree = tab._tree
    voltage_item = tree.topLevelItem(0).child(0)
    voltage_item.setCheckState(0, Qt.Checked)
    assert tab.selected_signals() == [("V", "1")]
    label, trajectory = tab.signal_array(("V", "1"))
    assert label == "|V| 1"
    assert trajectory.shape == results.t.shape
    assert len(tab._plot.getPlotItem().listDataItems()) == 1


def test_smallsignal_tab(app, results):
    from hermess.gui.smallsignal_tab import SmallSignalTab

    tab = SmallSignalTab()
    tab.set_results(results)
    assert tab._table.rowCount() == 2
    assert tab._table.item(0, 0).text() == "1"
    # Selecting the complex mode highlights both conjugate points.
    tab._table.selectRow(0)
    assert len(tab._highlight.points()) == 2
    # A run without small-signal data falls back to the placeholder.
    tab.set_results(SimulationResults(system="x", t=results.t, voltage={}, power={}))
    assert tab._placeholder.isVisible() or not tab._splitter.isVisible()


def test_options_dialog_roundtrip(app):
    from hermess.gui.options_dialog import OptionsDialog

    dialog = OptionsDialog({"T_end": 2.0, "line_dyn": False})
    dialog._accept()
    overrides = dialog.overrides()
    assert overrides["T_end"] == 2.0
    assert overrides["line_dyn"] is False
    # Untouched defaults must not appear as overrides.
    assert "ts" not in overrides
    assert "small_signal_analysis" not in overrides


def test_topology_tab(app, results):
    import pandas as pd

    import hermess
    from hermess.gui import sysparse
    from hermess.gui.topology_tab import TopologyTab

    tab = TopologyTab()
    desc = sysparse.parse_system(hermess.SYSTEMS_DIR / "3_bus")
    tab.set_system(desc)
    assert tab._pos.shape == (3, 2)
    assert len(tab._bus_labels) == 3
    assert len(tab._device_items) == 3  # SG1, GFMI2, StaticZIP

    # Annotation only applies when the run matches the shown system.
    results.system = "3_bus"
    results.power_flow_bus = pd.DataFrame(
        {
            "Bus": ["1", "2", "3"],
            "V Magnitude (pu)": [1.0, 0.98, 1.05],
            "V Phase (deg)": [0.0, -2.1, 1.3],
        }
    )
    tab.set_results(results)
    assert tab._annotations["2"] == (0.98, -2.1)
    results.system = "other_system"
    tab.set_results(results)
    assert tab._annotations == {}

    # Dragging a node updates the stored positions.
    tab._node_moved(0, np.array([0.4, 0.6]))
    assert np.allclose(tab._pos[0], [0.4, 0.6])


def test_powerflow_tab(app, results):
    import pandas as pd

    from hermess.gui.powerflow_tab import PowerFlowTab

    tab = PowerFlowTab()
    tab.set_results(None)
    assert not tab._tabs.isVisibleTo(tab)
    results.power_flow_bus = pd.DataFrame(
        {"Bus": ["1", "2"], "V Magnitude (pu)": [1.0, 0.98]}
    )
    tab.set_results(results)
    assert tab._tabs.isVisibleTo(tab)
    assert tab._bus_table.rowCount() == 2
    assert tab._bus_table.columnCount() == 2


def test_smallsignal_participation_pane(app, results):
    from hermess.gui.smallsignal_tab import SmallSignalTab

    tab = SmallSignalTab()
    tab.set_results(results)
    tab._table.selectRow(0)
    assert tab._part_bars is not None
    ticks = tab._part_plot.getAxis("left")._tickLevels
    assert ticks and ticks[0][0][1] == "SM@1:omega"  # largest participation first


def test_main_window_builds(app):
    from hermess.gui.main_window import MainWindow

    window = MainWindow()
    assert window._systems._tree.topLevelItemCount() >= 1
    shipped = window._systems._tree.topLevelItem(0)
    assert shipped.childCount() > 0
    # Selecting a shipped system fills the inspector.
    window._systems._tree.setCurrentItem(shipped.child(0))
    assert window._systems.current_system is not None
    assert window._systems._devices_tree.topLevelItemCount() > 0
    window._runner.shutdown()


def test_settings_roundtrip(app, tmp_path):
    import hermess
    from hermess.gui.main_window import MainWindow

    # A user folder holding one system, opened in the first session.
    system_dir = tmp_path / "my_system"
    system_dir.mkdir()
    source = hermess.SYSTEMS_DIR / "3_bus"
    for name in ("sim_param.txt", "sim_dist.txt"):
        (system_dir / name).write_text((source / name).read_text())

    first = MainWindow()
    assert first._systems.add_folder(system_dir)
    first._overrides = {"T_end": 3.0, "line_dyn": False}
    first.close()

    second = MainWindow()
    assert second._overrides == {"T_end": 3.0, "line_dyn": False}
    assert str(system_dir) in second._systems.user_folders()
    # The selection (the opened system) is restored too.
    assert second._systems.current_system == ("my_system", str(tmp_path))
    second.close()

    # An overrides set that no longer validates is dropped, not restored.
    QSettings().setValue("simulation/overrides", '{"no_such_field": 1}')
    third = MainWindow()
    assert third._overrides == {}
    third.close()
