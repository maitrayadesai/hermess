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

"""Disturbance editing for the builder: one form per event whose fields
follow the selected type, and a manager listing the sequence."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from hermess.gui.param_meta import DISTURBANCE_FIELDS
from hermess.gui.sysparse import Entry

_BUS_FIELDS = {"bus", "bus_i", "bus_j"}


def summarize(entry: Entry) -> str:
    """One list line for a disturbance entry."""
    kind = entry.get("type", "?")
    rest = ", ".join(
        f"{key} = {value}"
        for key, value in entry.params.items()
        if key not in ("time", "type") and value
    )
    return f"t = {entry.get('time', '?')} s   {kind}   {rest}"


class DisturbanceFormDialog(QDialog):
    """Add or edit one disturbance; the fields follow the selected type."""

    def __init__(self, buses: "list[str]", params: "dict[str, str] | None" = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Disturbance")
        self.setMinimumWidth(340)
        self._buses = buses
        params = dict(params or {})

        self._type = QComboBox()
        self._type.addItems(list(DISTURBANCE_FIELDS))
        if params.get("type") in DISTURBANCE_FIELDS:
            self._type.setCurrentText(params["type"])
        self._type.currentTextChanged.connect(self._rebuild)

        self._form = QFormLayout()
        self._fields: "dict[str, QComboBox | QLineEdit]" = {}
        self._initial = params

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        outer = QFormLayout()
        outer.addRow("type", self._type)
        layout.addLayout(outer)
        layout.addLayout(self._form)
        layout.addWidget(buttons)
        self._rebuild()

    def _rebuild(self) -> None:
        current = {name: self._value_of(w) for name, w in self._fields.items()}
        current = {**self._initial, **{k: v for k, v in current.items() if v}}
        while self._form.count():
            item = self._form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._fields = {}
        for name in DISTURBANCE_FIELDS[self._type.currentText()]:
            if name == "type":
                continue
            if name in _BUS_FIELDS and self._buses:
                widget = QComboBox()
                widget.setEditable(True)  # allow buses not yet placed
                widget.addItems(self._buses)
                if current.get(name):
                    widget.setCurrentText(current[name])
                else:
                    widget.setCurrentIndex(-1)
            else:
                widget = QLineEdit(current.get(name, ""))
            self._form.addRow(name, widget)
            self._fields[name] = widget

    @staticmethod
    def _value_of(widget) -> str:
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return widget.text().strip()

    def _accept(self) -> None:
        values = self.values()
        problems = []
        for name in ("time", "y", "p_delta", "q_delta", "value"):
            if values.get(name):
                try:
                    float(values[name])
                except ValueError:
                    problems.append(f"{name}: \"{values[name]}\" is not a number")
        if not values.get("time"):
            problems.append("time must be set")
        for name in self._fields:
            if name in _BUS_FIELDS and not values.get(name):
                problems.append(f"{name} must be set")
        if problems:
            QMessageBox.warning(self, "Invalid disturbance", "\n".join(problems))
            return
        self.accept()

    def values(self) -> "dict[str, str]":
        out = {"type": self._type.currentText()}
        for name, widget in self._fields.items():
            value = self._value_of(widget)
            if value:
                out[name] = value
        return out


class DisturbanceManagerDialog(QDialog):
    """The event sequence of the edited system: list, add, edit, remove.

    Operates directly on the :class:`~hermess.gui.sysdoc.SystemDocument`, so
    every change is undoable like any other edit.
    """

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Disturbances")
        self.setMinimumSize(460, 320)
        self._doc = document

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _item: self._edit())

        add_button = QPushButton("Add…")
        add_button.clicked.connect(self._add)
        edit_button = QPushButton("Edit…")
        edit_button.clicked.connect(self._edit)
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self._remove)
        buttons = QHBoxLayout()
        for b in (add_button, edit_button, remove_button):
            buttons.addWidget(b)
        buttons.addStretch(1)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        close.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(buttons)
        layout.addWidget(close)
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for entry in self._doc.desc.disturbances:
            item = QListWidgetItem(summarize(entry))
            item.setData(0x0100, entry)  # Qt.UserRole
            self._list.addItem(item)

    def _selected_entry(self):
        item = self._list.currentItem()
        return item.data(0x0100) if item is not None else None

    def _add(self) -> None:
        dialog = DisturbanceFormDialog(self._doc.desc.buses(), parent=self)
        if dialog.exec():
            self._doc.add_disturbance(dialog.values())
            self._refresh()

    def _edit(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        dialog = DisturbanceFormDialog(
            self._doc.desc.buses(), params=entry.params, parent=self
        )
        if dialog.exec():
            self._doc.update_entry(entry, dialog.values())
            self._refresh()

    def _remove(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self._doc.remove_entry(entry)
            self._refresh()
