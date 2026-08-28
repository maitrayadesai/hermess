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

"""Generated parameter forms for the builder.

The fields, defaults, and tooltips come from :mod:`hermess.gui.param_meta`
(i.e. from the model classes themselves). A field left empty means "use the
model default" and is omitted from the written entry, so generated files stay
as terse as the hand-written ones; only explicit values are stored.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hermess.gui import param_meta

_MODEL_DEFAULT = "(model default)"

# Keys whose values are names, not numbers; exempt from the float check.
_TEXT_KEYS = {"idx", "name", "type", "device", "param", "bus", "bus_i", "bus_j"}


class _ParamGrid(QWidget):
    """The name/value grid of one ParamMeta; empty field = model default."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._edits: "dict[str, QLineEdit]" = {}

    def rebuild(self, meta: param_meta.ParamMeta, values: "dict[str, str]") -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._edits = {}
        for row, (name, default) in enumerate(meta.params.items()):
            label = QLabel(name)
            edit = QLineEdit()
            edit.setText(values.get(name, ""))
            if name in meta.sentinels:
                edit.setPlaceholderText(f"= {meta.sentinels[name]}")
            else:
                edit.setPlaceholderText(default or "—")
            tip = meta.descriptions.get(name, "")
            if name in meta.sentinels:
                tip = (tip + "; " if tip else "") + (
                    f"defaults to the value of {meta.sentinels[name]}"
                )
            if tip:
                label.setToolTip(tip)
                edit.setToolTip(tip)
            self._layout.addWidget(label, row // 2, 2 * (row % 2))
            self._layout.addWidget(edit, row // 2, 2 * (row % 2) + 1)
        self._layout.setColumnStretch(1, 1)
        self._layout.setColumnStretch(3, 1)
        for row, name in enumerate(meta.params):
            widget = self._layout.itemAtPosition(row // 2, 2 * (row % 2) + 1).widget()
            self._edits[name] = widget

    def values(self) -> "dict[str, str]":
        return {
            name: edit.text().strip()
            for name, edit in self._edits.items()
            if edit.text().strip()
        }


class DeviceFormDialog(QDialog):
    """Add or edit one device entry: strategy dropdowns plus the parameter
    grid regenerated for the current strategy selection."""

    def __init__(self, kind: str, bus: str, params: "dict[str, str] | None" = None, parent=None):
        super().__init__(parent)
        self._kind = kind
        params = dict(params or {})
        self._idx = params.pop("idx", "")
        params.pop("bus", None)
        self.setWindowTitle(f"{kind} @ bus {bus}")
        self.setMinimumWidth(680)

        self._strategy_combos: "dict[str, QComboBox]" = {}
        meta = param_meta.device_meta(kind)
        axes = meta.strategy_axes if meta else []

        top = QFormLayout()
        self._idx_edit = QLineEdit(self._idx)
        self._idx_edit.setPlaceholderText("generated")
        top.addRow("idx", self._idx_edit)
        strategies_box = None
        if axes:
            strategies_box = QGroupBox("Control strategies")
            form = QFormLayout(strategies_box)
            for axis in axes:
                combo = QComboBox()
                combo.addItem(_MODEL_DEFAULT, "")
                for choice in param_meta.strategy_choices(axis):
                    combo.addItem(choice, choice)
                if params.get(axis):
                    index = combo.findData(params.get(axis))
                    combo.setCurrentIndex(max(index, 0))
                combo.currentIndexChanged.connect(self._rebuild)
                form.addRow(axis, combo)
                self._strategy_combos[axis] = combo
        self._initial_params = {
            k: v for k, v in params.items() if k not in self._strategy_combos
        }

        self._grid = _ParamGrid()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._grid)
        scroll.setMinimumHeight(320)

        hint = QLabel(
            "Empty fields use the model defaults (shown grey) and are not "
            "written to the system file."
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        if strategies_box is not None:
            layout.addWidget(strategies_box)
        layout.addWidget(hint)
        layout.addWidget(scroll)
        layout.addWidget(buttons)

        self._rebuild()

    def _selected_strategies(self) -> "dict[str, str]":
        return {
            axis: combo.currentData()
            for axis, combo in self._strategy_combos.items()
            if combo.currentData()
        }

    def _rebuild(self) -> None:
        # Carry the user's current explicit values across a strategy change
        # where the parameter names still exist.
        current = self._grid.values() or self._initial_params
        meta = param_meta.device_meta(self._kind, self._selected_strategies())
        if meta is None:
            QMessageBox.warning(
                self,
                "Unavailable combination",
                f"{self._kind} cannot be instantiated with this strategy "
                "selection.",
            )
            return
        self._meta = meta
        self._grid.rebuild(meta, current)

    def _accept(self) -> None:
        problems = _numeric_problems(self._grid.values())
        missing = [m for m in self._meta.mandatory if m not in self._grid.values()]
        if missing:
            problems.append(f"mandatory parameter(s) not set: {', '.join(missing)}")
        if problems:
            QMessageBox.warning(self, "Invalid values", "\n".join(problems))
            return
        self.accept()

    def values(self) -> "dict[str, str]":
        """The explicit entry parameters (idx, strategies, filled fields)."""
        out: dict[str, str] = {}
        if self._idx_edit.text().strip():
            out["idx"] = self._idx_edit.text().strip()
        out.update(self._selected_strategies())
        out.update(self._grid.values())
        return out


class SimpleFormDialog(QDialog):
    """Form for a fixed-field entry (Line, BusInit); optional combo fields."""

    def __init__(
        self,
        title: str,
        meta: param_meta.ParamMeta,
        params: "dict[str, str] | None" = None,
        combos: "dict[str, list[str]] | None" = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        params = dict(params or {})
        self._combo_fields: "dict[str, QComboBox]" = {}

        form = QFormLayout()
        for name, choices in (combos or {}).items():
            combo = QComboBox()
            combo.addItems(choices)
            if params.get(name) in choices:
                combo.setCurrentText(params.pop(name))
            form.addRow(name, combo)
            self._combo_fields[name] = combo
            meta = param_meta.ParamMeta(
                kind=meta.kind,
                params={k: v for k, v in meta.params.items() if k != name},
                descriptions=meta.descriptions,
            )

        self._grid = _ParamGrid()
        self._grid.rebuild(meta, params)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._grid)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        problems = _numeric_problems(self._grid.values())
        if problems:
            QMessageBox.warning(self, "Invalid values", "\n".join(problems))
            return
        self.accept()

    def values(self) -> "dict[str, str]":
        out = {name: combo.currentText() for name, combo in self._combo_fields.items()}
        out.update(self._grid.values())
        return out


def _numeric_problems(values: "dict[str, str]") -> "list[str]":
    problems = []
    for name, text in values.items():
        if name in _TEXT_KEYS or text.startswith("["):
            continue  # names, and [a;b] arrays (e.g. multi-mass shaft data)
        try:
            float(text)
        except ValueError:
            problems.append(f"{name}: \"{text}\" is not a number")
    return problems
