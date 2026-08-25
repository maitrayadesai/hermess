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

"""Systems browser and inspector.

The browser lists the shipped systems plus any user folders opened with
"Open folder...". The inspector shows the selected system's devices, network
and disturbances (parsed read-only) and the raw text files. The intended
editing loop is external: change the files in any editor, then Reload and
Run here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import hermess
from hermess.gui import sysparse

_ROLE_SYSTEM = Qt.UserRole  # (name, root_str_or_None) on selectable items


class SystemsPanel(QWidget):
    """Emits ``systemSelected(name, root)`` with root None for shipped systems."""

    systemSelected = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current: "tuple[str, str | None] | None" = None
        self._user_folders: "list[str]" = []

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._on_selection)

        open_button = QPushButton("Open folder…")
        open_button.clicked.connect(self.open_folder)
        reload_button = QPushButton("Reload")
        reload_button.setToolTip(
            "Re-read the selected system's files (after editing them externally)."
        )
        reload_button.clicked.connect(self._reload)

        self._inspector = QTabWidget()
        self._devices_tree = QTreeWidget()
        self._devices_tree.setHeaderLabels(["Element", "Value"])
        self._files_text = QPlainTextEdit()
        self._files_text.setReadOnly(True)
        font = self._files_text.font()
        font.setStyleHint(font.StyleHint.Monospace)
        self._files_text.setFont(font)
        self._inspector.addTab(self._devices_tree, "Elements")
        self._inspector.addTab(self._files_text, "Files")

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self._tree)
        top_layout.addWidget(open_button)
        top_layout.addWidget(reload_button)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(top)
        splitter.addWidget(self._inspector)
        splitter.setSizes([260, 380])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._shipped_root = QTreeWidgetItem(self._tree, ["Shipped systems"])
        self._shipped_root.setFlags(self._shipped_root.flags() & ~Qt.ItemIsSelectable)
        for name in hermess.list_systems():
            item = QTreeWidgetItem(self._shipped_root, [name])
            item.setData(0, _ROLE_SYSTEM, (name, None))
        self._shipped_root.setExpanded(True)

    # ---- public --------------------------------------------------------------

    @property
    def current_system(self) -> "tuple[str, str | None] | None":
        """(name, root) of the selected system, root None = shipped."""
        return self._current

    def system_folder(self) -> "Path | None":
        if self._current is None:
            return None
        name, root = self._current
        base = Path(root) if root is not None else hermess.SYSTEMS_DIR
        return base / name

    def refresh_inspector(self) -> None:
        self._devices_tree.clear()
        self._files_text.clear()
        folder = self.system_folder()
        if folder is None:
            return
        desc = sysparse.parse_system(folder)

        def add_group(title, entries, label_keys):
            if not entries:
                return
            group = QTreeWidgetItem(self._devices_tree, [title, ""])
            for entry in entries:
                label = " ".join(
                    filter(None, (entry.get(k) for k in label_keys))
                )
                node = QTreeWidgetItem(group, [entry.kind, label])
                for key, value in entry.params.items():
                    QTreeWidgetItem(node, [key, value])
            group.setExpanded(True)

        add_group("Devices", desc.devices, ("idx", "bus"))
        add_group("Lines", desc.lines, ("bus_i", "bus_j"))
        add_group("Bus initialization", desc.bus_inits, ("bus", "type"))
        add_group("Disturbances", desc.disturbances, ("type", "time"))
        self._devices_tree.resizeColumnToContents(0)

        chunks = []
        for filename in ("sim_param.txt", "sim_dist.txt"):
            path = folder / filename
            if path.exists():
                chunks.append(f"# ===== {filename} =====\n{path.read_text()}")
        self._files_text.setPlainText("\n\n".join(chunks))

    # ---- internals -----------------------------------------------------------

    def _reload(self) -> None:
        """Re-read the files and re-announce the system (updates all views)."""
        self.refresh_inspector()
        if self._current is not None:
            self.systemSelected.emit(self._current[0], self._current[1])

    def _on_selection(self, item, _previous) -> None:
        if item is None:
            return
        selected = item.data(0, _ROLE_SYSTEM)
        if selected is None:
            return
        self._current = selected
        self.refresh_inspector()
        self.systemSelected.emit(selected[0], selected[1])

    def open_folder(self) -> None:
        """Ask for a folder and add its system(s) to the browser."""
        chosen = QFileDialog.getExistingDirectory(self, "Open system folder")
        if not chosen:
            return
        if not self.add_folder(chosen):
            QMessageBox.warning(
                self,
                "No systems found",
                f"{chosen} contains no sim_param.txt "
                "(neither directly nor in subfolders).",
            )

    def add_folder(self, folder: "str | Path", select: bool = True) -> bool:
        """Add a user folder (one system, or a root of systems) to the browser.

        Returns False when the folder holds no system. Already-added folders
        are only re-selected, not duplicated.
        """
        folder = Path(folder)
        for i in range(self._tree.topLevelItemCount()):
            existing = self._tree.topLevelItem(i)
            if existing.text(0) == str(folder):
                if select and existing.childCount():
                    self._tree.setCurrentItem(existing.child(0))
                return True
        if (folder / "sim_param.txt").exists():
            # A single system folder: its parent is the root.
            root, names = folder.parent, [folder.name]
        else:
            root = folder
            names = hermess.list_systems(folder)
            if not names:
                return False
        top = QTreeWidgetItem(self._tree, [str(folder)])
        top.setToolTip(0, str(folder))
        top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
        for name in names:
            item = QTreeWidgetItem(top, [name])
            item.setData(0, _ROLE_SYSTEM, (name, str(root)))
        top.setExpanded(True)
        self._user_folders.append(str(folder))
        if select:
            self._tree.setCurrentItem(top.child(0))
        return True

    def user_folders(self) -> "list[str]":
        """The user folders added this session, in the order they were added."""
        return list(self._user_folders)

    def select_system(self, name: str, root: "str | None") -> bool:
        """Select a system by (name, root); returns False when absent."""
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.data(0, _ROLE_SYSTEM) == (name, root):
                    self._tree.setCurrentItem(child)
                    return True
        return False
