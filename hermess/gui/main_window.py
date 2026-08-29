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

"""The HERMESS main window: browser dock, viewer tabs, log dock, run control."""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QTabWidget,
)

import hermess
from hermess.gui import export, sysparse, validation
from hermess.gui.sysdoc import SystemDocument
from hermess.gui.logpanel import LogPanel
from hermess.gui.options_dialog import OptionsDialog
from hermess.gui.powerflow_tab import PowerFlowTab
from hermess.gui.runner import SimulationRunner
from hermess.gui.smallsignal_tab import SmallSignalTab
from hermess.gui.systems_panel import SystemsPanel
from hermess.gui.timedomain_tab import TimeDomainTab
from hermess.gui.topology_tab import TopologyTab
from hermess.gui.worker import RunRequest

_DOCS_URL = "https://maitrayadesai.github.io/hermess/"
_MAX_RUNS = 10  # kept in memory; oldest dropped beyond this


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HERMESS")
        self.resize(1280, 800)

        self._overrides: dict = {}
        self._runs: list = []  # (label, SimulationResults)
        self._last_selection = None  # (name, root) for reverting a selection
        self._reverting = False
        self._runner = SimulationRunner(self)

        # Central viewer tabs
        self._topology = TopologyTab()
        self._timedomain = TimeDomainTab()
        self._smallsignal = SmallSignalTab()
        self._powerflow = PowerFlowTab()
        tabs = QTabWidget()
        tabs.addTab(self._topology, "Topology")
        tabs.addTab(self._timedomain, "Time domain")
        tabs.addTab(self._smallsignal, "Small signal")
        tabs.addTab(self._powerflow, "Power flow")
        tabs.setCurrentIndex(1)  # time domain is the working view
        self.setCentralWidget(tabs)

        # Docks (object names are required for saveState/restoreState)
        self._systems = SystemsPanel()
        systems_dock = QDockWidget("Systems", self)
        systems_dock.setObjectName("systemsDock")
        systems_dock.setWidget(self._systems)
        self.addDockWidget(Qt.LeftDockWidgetArea, systems_dock)

        self._log = LogPanel()
        log_dock = QDockWidget("Log", self)
        log_dock.setObjectName("logDock")
        log_dock.setWidget(self._log)
        self.addDockWidget(Qt.BottomDockWidgetArea, log_dock)

        # Actions
        self._run_action = QAction("Run", self)
        self._run_action.setShortcut(QKeySequence("F5"))
        self._run_action.triggered.connect(self._start_run)
        self._stop_action = QAction("Stop", self)
        self._stop_action.setEnabled(False)
        self._stop_action.triggered.connect(self._runner.stop)
        options_action = QAction("Options…", self)
        options_action.triggered.connect(self._edit_options)
        export_action = QAction("Export CSV…", self)
        export_action.triggered.connect(self._export_csv)
        figure_action = QAction("Export figure…", self)
        figure_action.triggered.connect(self._export_figure)
        open_action = QAction("Open system folder…", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._systems.open_folder)
        new_action = QAction("New system", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_system)
        self._save_action = QAction("Save system", self)
        self._save_action.setShortcut(QKeySequence.Save)
        self._save_action.setEnabled(False)
        self._save_action.triggered.connect(self._save_system)
        self._save_as_action = QAction("Save system as…", self)
        self._save_as_action.setEnabled(False)
        self._save_as_action.triggered.connect(lambda: self._save_system(save_as=True))
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        docs_action = QAction("Documentation", self)
        docs_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(_DOCS_URL))
        )
        about_action = QAction("About HERMESS", self)
        about_action.triggered.connect(self._about)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(self._save_action)
        file_menu.addAction(self._save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(export_action)
        file_menu.addAction(figure_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        sim_menu = self.menuBar().addMenu("Simulation")
        sim_menu.addAction(self._run_action)
        sim_menu.addAction(self._stop_action)
        sim_menu.addSeparator()
        sim_menu.addAction(options_action)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(docs_action)
        help_menu.addAction(about_action)

        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.addAction(self._run_action)
        toolbar.addAction(self._stop_action)
        toolbar.addAction(options_action)
        toolbar.addAction(export_action)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Run: "))
        self._runs_combo = QComboBox()
        self._runs_combo.setMinimumWidth(240)
        self._runs_combo.currentIndexChanged.connect(self._show_run)
        toolbar.addWidget(self._runs_combo)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setFixedWidth(220)
        self._progress.setVisible(False)
        self.statusBar().addPermanentWidget(self._progress)
        self.statusBar().showMessage("Select a system and press Run (F5).")

        # Wiring
        self._topology.set_validator(
            lambda desc: validation.validate(desc, self._overrides)
        )
        self._topology.documentChanged.connect(self._on_document_changed)
        self._topology.editModeChanged.connect(self._on_edit_mode_changed)
        self._systems.systemSelected.connect(self._on_system_selected)
        self._runner.stateChanged.connect(self._on_state_changed)
        self._runner.progressed.connect(self._on_progress)
        self._runner.logged.connect(self._log.append_record)
        self._runner.stability.connect(self._on_stability)
        self._runner.finished.connect(self._on_finished)
        self._runner.failed.connect(self._on_failed)
        self._runner.cancelled.connect(self._on_cancelled)

        self._restore_settings()

    # ---- run control ---------------------------------------------------------

    def _start_run(self) -> None:
        if self._runner.running:
            return
        if self._topology.editing and not self._resolve_edited_system():
            return
        selected = self._systems.current_system
        if selected is None:
            QMessageBox.information(
                self, "No system selected", "Select a system in the Systems panel first."
            )
            return
        name, root = selected
        if not self._preflight():
            return
        self._log.append_notice(f"Running {name} …")
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self.statusBar().showMessage(f"Building and initializing {name} …")
        self._runner.start(
            RunRequest(system=name, system_root=root, overrides=dict(self._overrides))
        )

    def _preflight(self) -> bool:
        """Validate the (system, options) pair; True when the run may start.

        Errors block; warnings ask for confirmation. Every issue also lands
        in the log so it survives the dialog.
        """
        folder = self._systems.system_folder()
        if folder is None:
            return True
        issues = validation.validate(
            sysparse.parse_system(folder), self._overrides
        )
        if not issues:
            return True
        errors = [i for i in issues if i.severity == "error"]
        for issue in issues:
            self._log.append_record(
                logging.ERROR if issue.severity == "error" else logging.WARNING,
                issue.message,
            )
        listing = "\n\n".join(
            ("✖  " if i.severity == "error" else "⚠  ") + i.message
            for i in issues
        )
        if errors:
            box = QMessageBox(
                QMessageBox.Critical,
                "Cannot start the simulation",
                "The system or the simulation options have problems that "
                "would make the run fail:",
                parent=self,
            )
            box.setInformativeText(listing)
            box.exec()
            return False
        box = QMessageBox(
            QMessageBox.Warning,
            "Check the configuration",
            "The run can start, but the following looks questionable:",
            parent=self,
        )
        box.setInformativeText(listing)
        run_button = box.addButton("Run anyway", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is run_button

    def _on_stability(self, payload: dict) -> None:
        """The worker's operating-point report; unstable holds the run until
        the user decides."""
        n_modes = payload.get("n_modes", 0)
        unstable = payload.get("unstable", [])
        if not unstable:
            self._log.append_notice(
                f"Operating point is stable ({n_modes} modes)."
            )
            return
        lines = []
        for mode in unstable:
            eig = mode["eig"]
            dominant = ", ".join(
                f"{name} ({pf:.0%})" for name, pf in mode["dominant"]
            )
            lines.append(
                f"mode {mode['id']}:  λ = {eig.real:+.4f} ± {abs(eig.imag):.3f}j,  "
                f"f = {mode['freq_hz']:.3f} Hz,  ζ = {mode['zeta'] * 100:+.1f}%\n"
                f"    dominant states: {dominant}"
            )
        self._log.append_record(
            logging.WARNING,
            f"Operating point unstable ({len(unstable)} of {n_modes} modes):\n"
            + "\n".join(lines),
        )
        box = QMessageBox(
            QMessageBox.Warning,
            "Unstable operating point",
            f"The small-signal analysis found {len(unstable)} unstable "
            f"mode(s) at the operating point. The simulation will likely "
            "diverge or fail.",
            parent=self,
        )
        box.setInformativeText("\n\n".join(lines))
        cont = box.addButton("Continue anyway", QMessageBox.AcceptRole)
        box.addButton("Stop the run", QMessageBox.RejectRole)
        box.exec()
        proceed = box.clickedButton() is cont
        self._runner.answer_stability(proceed)
        self._log.append_notice(
            "Continuing despite the unstable operating point."
            if proceed
            else "Run stopped at the unstable operating point."
        )

    def _on_system_selected(self, name: str, root) -> None:
        if self._reverting:
            return
        if self._topology.editing and self._topology.document.dirty:
            if not self._confirm_discard():
                self._reverting = True
                if self._last_selection is not None:
                    self._systems.select_system(*self._last_selection)
                self._reverting = False
                return
        self._last_selection = (name, root)
        folder = self._systems.system_folder()
        self._topology.set_system(
            sysparse.parse_system(folder) if folder is not None else None
        )
        self._topology.set_results(self._current_results())
        self.statusBar().showMessage(f"System: {name}. Press Run (F5).")

    # ---- system building -----------------------------------------------------

    def _new_system(self) -> None:
        if self._topology.editing and self._topology.document.dirty:
            if not self._confirm_discard():
                return
        self.centralWidget().setCurrentWidget(self._topology)
        self._topology.begin_edit(SystemDocument.blank())
        self.statusBar().showMessage(
            "Building a new system: place buses, connect lines, attach devices; "
            "Save writes an ordinary system folder."
        )

    def _on_edit_mode_changed(self, active: bool) -> None:
        self._save_action.setEnabled(active)
        self._save_as_action.setEnabled(active)
        if active:
            self.statusBar().showMessage(
                "Edit mode: use the palette above the diagram; double-click "
                "elements to edit their parameters."
            )

    def _on_document_changed(self) -> None:
        self._save_action.setEnabled(True)

    def _inside_shipped(self, folder: Path) -> bool:
        try:
            return Path(folder).resolve().is_relative_to(
                hermess.SYSTEMS_DIR.resolve()
            )
        except (OSError, ValueError):
            return False

    def _save_system(self, save_as: bool = False) -> bool:
        """Save the edited system; returns True when it was written."""
        if not self._topology.editing:
            return False
        doc = self._topology.document
        folder = doc.desc.folder
        needs_dialog = (
            save_as
            or folder is None
            or not Path(folder).is_absolute()
            or self._inside_shipped(folder)
        )
        if needs_dialog:
            path, _filter = QFileDialog.getSaveFileName(
                self,
                "Save system as (a folder of this name is created)",
                str(Path.home() / doc.desc.name),
            )
            if not path:
                return False
            folder = Path(path)
            if self._inside_shipped(folder):
                QMessageBox.warning(
                    self,
                    "Read-only location",
                    "The systems shipped with the package cannot be "
                    "overwritten; choose a folder of your own.",
                )
                return False
        doc.save(folder)
        self._log.append_notice(f"Saved system to {folder}.")
        # Registering the folder selects it, which shows the saved system
        # read-only; Edit re-opens it.
        self._systems.add_folder(folder, select=True)
        return True

    def _resolve_edited_system(self) -> bool:
        """Before running while editing: make sure the document is saved and
        selected; returns False when the run must not start.

        Once the document has its own folder, Run saves silently (the IDE
        convention: running implies saving); only the very first save asks,
        because a target folder must be chosen."""
        doc = self._topology.document
        folder = doc.desc.folder
        has_target = (
            folder is not None
            and Path(folder).is_absolute()
            and not self._inside_shipped(folder)
        )
        if doc.dirty and not has_target:
            box = QMessageBox(
                QMessageBox.Question,
                "Save before running",
                "The system runs from its files, so it must be saved once "
                "to a folder of your choice; afterwards Run saves "
                "automatically.",
                parent=self,
            )
            save_button = box.addButton("Save…", QMessageBox.AcceptRole)
            box.addButton("Cancel", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not save_button:
                return False
            return self._save_system()
        if doc.dirty or not (Path(folder) / "sim_param.txt").exists():
            return self._save_system()  # silent: the target is already known
        self._systems.add_folder(folder, select=True)
        return True

    def _confirm_discard(self) -> bool:
        """Unsaved edits stand in the way; returns True when it is safe to
        proceed (saved or deliberately discarded)."""
        box = QMessageBox(
            QMessageBox.Warning,
            "Unsaved system",
            "The edited system has unsaved changes.",
            parent=self,
        )
        save_button = box.addButton("Save…", QMessageBox.AcceptRole)
        discard_button = box.addButton("Discard", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is save_button:
            return self._save_system()
        return box.clickedButton() is discard_button

    def _on_state_changed(self, running: bool) -> None:
        self._run_action.setEnabled(not running)
        self._stop_action.setEnabled(running)
        if not running:
            self._progress.setVisible(False)

    def _on_progress(self, fraction: float) -> None:
        self._progress.setValue(round(fraction * 1000))
        self.statusBar().showMessage(f"Simulating … {fraction:.0%}")

    def _on_finished(self, results) -> None:
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        label = f"{stamp}  {results.system}"
        self._runs.append((label, results))
        del self._runs[:-_MAX_RUNS]
        self._rebuild_runs_combo(select_last=True)
        self._log.append_notice(f"Finished {results.system}.")
        self.statusBar().showMessage(f"Finished {results.system}.")

    def _on_failed(self, message: str) -> None:
        self._log.append_record(logging.ERROR, message)
        self.statusBar().showMessage("Simulation failed.")
        short = message.splitlines()[0] if message else "Unknown error"
        box = QMessageBox(QMessageBox.Critical, "Simulation failed", short, parent=self)
        box.setDetailedText(message)
        box.exec()

    def _on_cancelled(self) -> None:
        self._log.append_notice("Simulation cancelled.")
        self.statusBar().showMessage("Simulation cancelled.")

    # ---- runs and views ------------------------------------------------------

    def _rebuild_runs_combo(self, select_last: bool = False) -> None:
        self._runs_combo.blockSignals(True)
        self._runs_combo.clear()
        for label, _results in self._runs:
            self._runs_combo.addItem(label)
        if select_last and self._runs:
            self._runs_combo.setCurrentIndex(len(self._runs) - 1)
        self._runs_combo.blockSignals(False)
        self._show_run(self._runs_combo.currentIndex())

    def _show_run(self, index: int) -> None:
        if not (0 <= index < len(self._runs)):
            return
        _label, results = self._runs[index]
        self._timedomain.set_results(results)
        self._smallsignal.set_results(results)
        self._powerflow.set_results(results)
        self._topology.set_results(results)

    def _current_results(self):
        index = self._runs_combo.currentIndex()
        if 0 <= index < len(self._runs):
            return self._runs[index][1]
        return None

    # ---- dialogs -------------------------------------------------------------

    def _edit_options(self) -> None:
        dialog = OptionsDialog(self._overrides, self)
        if dialog.exec():
            self._overrides = dialog.overrides()
            summary = ", ".join(f"{k}={v}" for k, v in self._overrides.items())
            self.statusBar().showMessage(
                f"Options: {summary}" if summary else "Options: defaults."
            )

    def _export_csv(self) -> None:
        results = self._current_results()
        if results is None:
            QMessageBox.information(self, "Nothing to export", "Run a simulation first.")
            return
        signal_ids = self._timedomain.selected_signals()
        if not signal_ids:
            QMessageBox.information(
                self,
                "Nothing selected",
                "Check the signals to export in the Time domain tab first.",
            )
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export selected signals", f"{results.system}.csv", "CSV (*.csv)"
        )
        if not path:
            return
        signals = [self._timedomain.signal_array(sid) for sid in signal_ids]
        sidecar = export.export_csv(path, results, signals)
        self._log.append_notice(f"Exported {len(signals)} signals to {path} (+ {sidecar.name}).")

    def _export_figure(self) -> None:
        """Save the current viewer tab as a PNG (a rough preview; final paper
        figures come from the CSV export and pgfplots)."""
        widget = self.centralWidget().currentWidget()
        name = self.centralWidget().tabText(self.centralWidget().currentIndex())
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Export figure",
            f"{name.lower().replace(' ', '_')}.png",
            "PNG image (*.png)",
        )
        if not path:
            return
        pixmap = widget.grab()
        pixmap.setDevicePixelRatio(1.0)  # save at full rendered resolution
        pixmap.save(path)
        self._log.append_notice(f"Saved figure to {path}.")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About HERMESS",
            f"<b>HERMESS</b> {hermess.__version__}<br>"
            "Hybrid EMT/RMS Modern Electric power System Simulator<br><br>"
            "© 2024-2026 ETH Zurich, GPL-3.0-or-later<br>"
            f'<a href="{_DOCS_URL}">Documentation</a>',
        )

    # ---- lifecycle -----------------------------------------------------------

    def _restore_settings(self) -> None:
        """Restore window layout, opened folders, selection and options from
        the previous session. Every part is optional: corrupted or outdated
        values are dropped rather than breaking startup."""
        settings = QSettings()
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = settings.value("window/state")
        if state is not None:
            self.restoreState(state)

        try:
            folders = json.loads(str(settings.value("systems/userFolders", "[]")))
        except json.JSONDecodeError:
            folders = []
        for folder in folders:
            if Path(folder).is_dir():
                self._systems.add_folder(folder, select=False)

        try:
            last = json.loads(str(settings.value("systems/last", "null")))
        except json.JSONDecodeError:
            last = None
        if last:
            self._systems.select_system(last[0], last[1])

        try:
            overrides = json.loads(str(settings.value("simulation/overrides", "{}")))
            # Validate against the current Config schema; a field renamed or
            # retyped since the last session invalidates the whole set.
            from hermess.gui.options_dialog import validate_overrides

            validate_overrides(overrides)
            self._overrides = overrides
        except Exception:
            self._overrides = {}

    def closeEvent(self, event) -> None:
        if self._topology.editing and self._topology.document.dirty:
            if not self._confirm_discard():
                event.ignore()
                return
        settings = QSettings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())
        settings.setValue(
            "systems/userFolders", json.dumps(self._systems.user_folders())
        )
        current = self._systems.current_system
        settings.setValue(
            "systems/last", json.dumps(list(current) if current else None)
        )
        settings.setValue("simulation/overrides", json.dumps(self._overrides))
        self._runner.shutdown()
        super().closeEvent(event)
