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
    assert tab._placeholder.isVisibleTo(tab)  # empty state before any run
    tab.set_results(results)
    assert not tab._placeholder.isVisibleTo(tab)
    assert tab._splitter.isVisibleTo(tab)
    # Check the first voltage signal programmatically and expect one curve.
    tree = tab._tree
    voltage_item = tree.topLevelItem(0).child(0)
    voltage_item.setCheckState(0, Qt.Checked)
    assert tab.selected_signals() == [("V", "1")]
    label, trajectory = tab.signal_array(("V", "1"))
    assert label == "|V| 1"
    assert trajectory.shape == results.t.shape
    assert len(tab._plot.getPlotItem().listDataItems()) == 1
    # The checked signal carries a color chip; unchecked ones do not.
    assert not voltage_item.icon(0).isNull()
    voltage_item.setCheckState(0, Qt.Unchecked)
    assert voltage_item.icon(0).isNull()

    # Long records render with the fast pen (no antialiasing), short ones
    # keep the antialiased stroke.
    assert results.t.shape[0] <= 20_000
    voltage_item.setCheckState(0, Qt.Checked)
    curve = tab._plot.getPlotItem().listDataItems()[0]
    assert curve.opts["antialias"] is True
    long_t = np.linspace(0.0, 10.0, 100_001)
    tab.set_results(
        SimulationResults(
            system="long",
            t=long_t,
            voltage={"1": np.exp(1j * 0.01 * long_t)},
            power={},
        )
    )
    tab._tree.topLevelItem(0).child(0).setCheckState(0, Qt.Checked)
    curve = tab._plot.getPlotItem().listDataItems()[0]
    assert curve.opts["antialias"] is False


def test_algebraic_signals_in_tree(app, results):
    from PySide6.QtCore import Qt

    from hermess.gui.timedomain_tab import TimeDomainTab

    results.devices[0].algebraics = {"omega_c": 1.0 + 0.001 * results.t}
    tab = TimeDomainTab()
    tab.set_results(results)
    root = tab._tree.invisibleRootItem()
    device_group = next(
        root.child(i)
        for i in range(root.childCount())
        if root.child(i).text(0).startswith("SG1")
    )
    algebraic_item = next(
        device_group.child(i)
        for i in range(device_group.childCount())
        if "omega_c" in device_group.child(i).text(0)
    )
    assert "(algebraic)" in algebraic_item.text(0)
    algebraic_item.setCheckState(0, Qt.Checked)
    label, values = tab.signal_array(algebraic_item.data(0, 0x0100))
    assert label == "SG1:omega_c"
    assert values.shape == results.t.shape


def test_eigenvalue_click_with_empty_selection(app, results):
    import numpy as np

    from hermess.gui.smallsignal_tab import SmallSignalTab

    tab = SmallSignalTab()
    tab.set_results(results)
    # pyqtgraph hands the clicked spots over as a numpy array; an empty one
    # must not raise (plain truthiness on arrays does).
    tab._select_from_plot(tab._scatter, np.array([]))


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
    desc = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus")
    tab.set_system(desc)
    assert tab._pos.shape == (3, 2)
    assert len(tab._bus_labels) == 3
    assert len(tab._device_items) == 3  # SG1, GFMI2, StaticZIP

    # Annotation only applies when the run matches the shown system.
    results.system = "3bus"
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


def test_info_dialog_and_topology_double_click(app):
    import hermess
    from hermess.gui import device_info, sysparse
    from hermess.gui.info_dialog import InfoDialog
    from hermess.gui.topology_tab import TopologyTab

    root = device_info.schematics_dir()
    dialog = InfoDialog(
        "GFMI2 — GridForming",
        "A grid-forming converter.",
        params={"Sn": "100", "Kp": "0.01"},
        diagrams=[("Control structure", root / "conv_structure.svg")],
    )
    assert dialog.windowTitle().startswith("GFMI2")
    dialog.close()

    tab = TopologyTab()
    tab.set_system(sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus"))
    # Double-click handlers build their dialogs without raising.
    tab._show_device_info(tab._desc.devices[1])  # the grid-forming converter
    tab._show_bus_info(0)


def test_preflight_blocks_on_errors(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from hermess.gui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    window = MainWindow()
    shipped = window._systems._tree.topLevelItem(0)
    for i in range(shipped.childCount()):
        if shipped.child(i).text(0) == "3bus":
            window._systems._tree.setCurrentItem(shipped.child(i))
            break
    assert window._preflight() is True
    window._overrides = {"int_scheme_sim": "cvodes", "line_dyn": False}
    assert window._preflight() is False
    window._runner.shutdown()
    window.close()


def test_device_form_dialog(app):
    from hermess.gui.param_form import DeviceFormDialog

    dialog = DeviceFormDialog("GENROU", bus="1")
    # A pristine form is all model defaults: nothing explicit is emitted
    # (the document generates the idx when the device is added).
    assert dialog.values() == {}
    dialog._grid._edits["H"].setText("6.5")
    combo = dialog._strategy_combos["pss"]
    combo.setCurrentIndex(combo.findData("PSSKundur"))
    values = dialog.values()
    assert values["H"] == "6.5"  # explicit value survives the strategy change
    assert values["pss"] == "PSSKundur"
    assert "Sn" not in values  # untouched fields stay on model defaults


def test_simple_form_dialog_businit(app):
    from hermess.gui import param_meta
    from hermess.gui.param_form import SimpleFormDialog

    dialog = SimpleFormDialog(
        "Bus 1",
        param_meta.businit_meta(),
        params={"type": "PV", "p": "-50"},
        combos={"type": ["slack", "PV", "PQ"]},
    )
    values = dialog.values()
    assert values["type"] == "PV"
    assert values["p"] == "-50"


def test_disturbance_form_dialog(app):
    from hermess.gui.disturbance_editor import DisturbanceFormDialog, summarize
    from hermess.gui.sysparse import Entry

    dialog = DisturbanceFormDialog(
        ["1", "2"], params={"type": "LOAD", "time": "1.0", "bus": "2"}
    )
    assert set(dialog._fields) == {"time", "bus", "p_delta", "q_delta"}
    assert dialog._required == ["time", "bus"]
    dialog._type.setCurrentText("OPEN_LINE")
    assert set(dialog._fields) == {"time", "bus_i", "bus_j"}
    assert "OPEN_LINE" in dialog._example.text()  # the core's file-form example
    assert "t = 1.0" in summarize(Entry("Disturbance", {"time": "1.0", "type": "LOAD"}))


def test_preflight_respects_system_defaults(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from hermess.gui.main_window import MainWindow

    # A network whose lines carry no charging fails pre-flight with the
    # package default line_dyn=True, unless its sim_settings.txt turns
    # dynamic lines off, as hermess.simulate would.
    system = tmp_path / "bare"
    system.mkdir()
    (system / "sim_param.txt").write_text(
        'Line, bus_i = "1", bus_j = "2", r = 0.01, x = 0.1\n'
        'BusInit, bus = "1", p = 0, v = 1.0, type = "slack"\n'
        'BusInit, bus = "2", p = 10, q = 0, type = "PQ"\n'
    )
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    window = MainWindow()
    window._overrides = {}  # ignore overrides restored from earlier tests
    window._systems.add_folder(system)
    assert window._preflight() is False  # zero shunt susceptance blocks
    (system / "sim_settings.txt").write_text("line_dyn = false\n")
    assert window._preflight() is True  # the shipped default lifts it
    window._runner.shutdown()
    window.close()


def test_options_dialog_uses_system_defaults(app):
    from hermess.gui.options_dialog import OptionsDialog

    dialog = OptionsDialog({}, system_defaults={"line_dyn": False})
    # Untouched dialog: the system default is the baseline, not an override.
    dialog._accept()
    assert dialog.overrides() == {}
    # Explicitly turning dynamic lines back on becomes an override, even
    # though it equals the package default.
    dialog._widgets["line_dyn"].setChecked(True)
    dialog._accept()
    assert dialog.overrides() == {"line_dyn": True}


def test_topology_edit_mode(app):
    import numpy as np

    from hermess.gui.sysdoc import SystemDocument
    from hermess.gui.topology_tab import TopologyTab

    tab = TopologyTab()
    tab.begin_edit(SystemDocument.blank())
    assert tab.editing
    doc = tab.document

    name = doc.add_bus()
    tab._changed({name: (0.2, 0.3)})
    assert len(tab._bus_labels) == 1
    assert np.allclose(tab._pos_by_name["1"], [0.2, 0.3])

    second = doc.add_bus()
    tab._changed({second: (0.8, 0.3)})
    doc.add_line("1", "2")
    doc.add_device("StaticZIP", "2")
    tab._changed()
    assert len(tab._device_items) == 1
    # The click position survives re-renders.
    assert np.allclose(tab._pos_by_name["1"], [0.2, 0.3])

    # Hit testing: the delete tool finds and removes the device, then the bus.
    tab._view.getPlotItem().vb.setRange(xRange=(0, 1), yRange=(0, 1))
    glyph_entry = tab._nearest_device(
        tab._pos[1] + 0.11 * np.array([1.0, 0.0])
    ) or tab._device_items[0][5]
    tab._doc.remove_entry(glyph_entry)
    tab._changed()
    assert tab._desc.devices == []
    tab._delete_at(np.array([0.2, 0.3]))
    assert tab._desc.buses() == ["2"]

    # Leaving edit mode with a clean document needs no confirmation.
    tab.document.dirty = False
    tab._edit_toggle.setChecked(False)
    assert not tab.editing
    assert tab._desc.buses() == ["2"]


def test_form_labels_show_actual_defaults(app):
    from hermess.gui.param_form import DeviceFormDialog

    dialog = DeviceFormDialog("GENROU", bus="1", suggested_idx="SG3")
    assert dialog._idx_edit.placeholderText() == "SG3"
    avr = dialog._strategy_combos["avr"]
    assert avr.itemText(0) == "(model default: IEEEDC1A)"
    pss = dialog._strategy_combos["pss"]
    assert pss.itemText(0) == "(model default: none)"


def test_tool_resets_to_move_after_actions(app, monkeypatch):
    import numpy as np

    from hermess.gui.param_form import DeviceFormDialog
    from hermess.gui.sysdoc import SystemDocument
    from hermess.gui.topology_tab import TopologyTab

    tab = TopologyTab()
    tab.begin_edit(SystemDocument.blank())
    doc = tab.document
    tab._changed({doc.add_bus(): (0.0, 0.0)})
    tab._changed({doc.add_bus(): (1.0, 0.0)})
    tab._view.getPlotItem().vb.setRange(xRange=(0, 1), yRange=(-0.5, 0.5))

    # Completing a line drops back to the Move tool.
    tab._tool_buttons["line"].setChecked(True)
    tab._line_tool_click(np.array([0.0, 0.0]))
    tab._line_tool_click(np.array([1.0, 0.0]))
    assert tab._active_tool() == "move"
    assert len(tab._desc.lines) == 1

    # So does attaching a device, even when the dialog is cancelled.
    monkeypatch.setattr(DeviceFormDialog, "exec", lambda self: False)
    tab._tool_buttons["device"].setChecked(True)
    tab._pending_device_kind = "StaticZIP"
    tab._add_device_at("StaticZIP", "2")
    assert tab._active_tool() == "move"

    # And deleting something.
    tab._tool_buttons["delete"].setChecked(True)
    tab._delete_at(np.array([1.0, 0.0]))  # removes bus 2
    assert tab._active_tool() == "move"
    assert tab._desc.buses() == ["1"]


def test_toggle_off_with_dirty_document_confirms(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from hermess.gui.sysdoc import SystemDocument
    from hermess.gui.topology_tab import TopologyTab

    tab = TopologyTab()
    tab.begin_edit(SystemDocument.blank())
    tab.document.add_bus()
    tab._changed()

    # "Keep editing" leaves edit mode active.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(
        QMessageBox,
        "clickedButton",
        lambda self: next(
            b
            for b in self.buttons()
            if self.buttonRole(b) == QMessageBox.RejectRole
        ),
    )
    tab._edit_toggle.setChecked(False)
    assert tab.editing
    assert tab._edit_toggle.isChecked()

    # "Discard" leaves edit mode.
    monkeypatch.setattr(
        QMessageBox,
        "clickedButton",
        lambda self: next(
            b
            for b in self.buttons()
            if self.buttonRole(b) == QMessageBox.DestructiveRole
        ),
    )
    tab._edit_toggle.setChecked(False)
    assert not tab.editing


def test_line_double_click_edits(app, monkeypatch):
    import numpy as np

    from hermess.gui.param_form import SimpleFormDialog
    from hermess.gui.sysdoc import SystemDocument
    from hermess.gui.topology_tab import TopologyTab

    tab = TopologyTab()
    tab.begin_edit(SystemDocument.blank())
    doc = tab.document
    tab._changed({doc.add_bus(): (0.0, 0.0)})
    tab._changed({doc.add_bus(): (1.0, 0.0)})
    line = doc.add_line("1", "2")
    tab._changed()
    tab._view.getPlotItem().vb.setRange(xRange=(0, 1), yRange=(-0.5, 0.5))

    # The midpoint of the segment hits the line, not a bus or glyph.
    assert tab._nearest_line(np.array([0.5, 0.0])) is line
    monkeypatch.setattr(SimpleFormDialog, "exec", lambda self: True)
    monkeypatch.setattr(SimpleFormDialog, "values", lambda self: {"r": "0.05"})
    tab._line_double_clicked(line)
    assert line.params["r"] == "0.05"
    assert line.get("bus_i") == "1" and line.get("bus_j") == "2"  # endpoints kept


def test_clear_canvas_confirms(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from hermess.gui.sysdoc import SystemDocument
    from hermess.gui.topology_tab import TopologyTab

    tab = TopologyTab()
    tab.begin_edit(SystemDocument.blank())
    tab.document.add_bus()
    tab._changed()
    # Auto-click the destructive (Clear) button of the confirmation.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(
        QMessageBox,
        "clickedButton",
        lambda self: next(
            b
            for b in self.buttons()
            if self.buttonRole(b) == QMessageBox.DestructiveRole
        ),
    )
    tab._clear_canvas()
    assert tab._desc.buses() == []
    assert "canvas is empty" in tab._status.text().lower()
    assert tab._undo_button.isEnabled()  # the clear is undoable


def test_run_saves_silently_once_folder_known(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from hermess.gui.main_window import MainWindow
    from hermess.gui.sysdoc import SystemDocument

    # Any dialog would mean the silent path was not taken.
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: (_ for _ in ()).throw(AssertionError)
    )
    window = MainWindow()
    window._topology.begin_edit(SystemDocument.blank())
    doc = window._topology.document
    doc.add_bus()
    doc.save(tmp_path / "mysys")
    doc.add_bus()  # dirty again, but the target folder is known
    assert doc.dirty
    assert window._resolve_edited_system() is True
    assert 'bus = "2"' in (tmp_path / "mysys" / "sim_param.txt").read_text()
    assert window._systems.current_system == ("mysys", str(tmp_path))
    window._runner.shutdown()
    window.close()


def test_save_as_forks_instead_of_overwriting(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from hermess.gui.main_window import MainWindow
    from hermess.gui.sysdoc import SystemDocument

    window = MainWindow()
    window._topology.begin_edit(SystemDocument.blank())
    doc = window._topology.document
    doc.add_bus()
    doc.save(tmp_path / "original")
    original_text = (tmp_path / "original" / "sim_param.txt").read_text()

    doc.add_bus()  # the change that is worth keeping as a variant
    suggestions = []

    def fake_dialog(parent, caption, start, *args, **kwargs):
        suggestions.append(start)
        return str(tmp_path / "variant"), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_dialog))
    window._topology._request_save(save_as=True)
    # The variant holds the new state; the original is untouched.
    assert 'bus = "2"' in (tmp_path / "variant" / "sim_param.txt").read_text()
    assert (tmp_path / "original" / "sim_param.txt").read_text() == original_text
    assert suggestions[0].endswith("original_variant")  # suggested sibling name
    window._runner.shutdown()
    window.close()


def test_save_as_refuses_to_clobber_another_system(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from hermess.gui.main_window import MainWindow
    from hermess.gui.sysdoc import SystemDocument

    victim = tmp_path / "existing"
    victim.mkdir()
    (victim / "sim_param.txt").write_text("# another user's system\n")

    window = MainWindow()
    window._topology.begin_edit(SystemDocument.blank())
    window._topology.document.add_bus()
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(victim), ""))
    )
    # Cancelling the replace question leaves the existing system untouched.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(
        QMessageBox,
        "clickedButton",
        lambda self: next(
            b
            for b in self.buttons()
            if self.buttonRole(b) == QMessageBox.RejectRole
        ),
    )
    assert window._save_system() is False
    assert "another user's system" in (victim / "sim_param.txt").read_text()

    # Confirming replaces it.
    monkeypatch.setattr(
        QMessageBox,
        "clickedButton",
        lambda self: next(
            b
            for b in self.buttons()
            if self.buttonRole(b) == QMessageBox.DestructiveRole
        ),
    )
    assert window._save_system() is True
    assert 'bus = "1"' in (victim / "sim_param.txt").read_text()
    window._runner.shutdown()
    window.close()


def test_window_title_tracks_state(app):
    from hermess.gui.main_window import MainWindow
    from hermess.gui.sysdoc import SystemDocument

    window = MainWindow()
    shipped = window._systems._tree.topLevelItem(0)
    window._systems._tree.setCurrentItem(shipped.child(0))
    selected = window._systems.current_system[0]
    assert window.windowTitle() == f"HERMESS — {selected}"
    window._topology.begin_edit(SystemDocument.blank("untitled"))
    window._topology.document.add_bus()
    window._topology._changed()
    assert window.windowTitle() == "HERMESS — untitled*"
    window._topology.document.dirty = False
    window._runner.shutdown()
    window.close()


def test_settings_roundtrip(app, tmp_path):
    import hermess
    from hermess.gui.main_window import MainWindow

    # A user folder holding one system, opened in the first session.
    system_dir = tmp_path / "my_system"
    system_dir.mkdir()
    source = hermess.SYSTEMS_DIR / "3bus"
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
