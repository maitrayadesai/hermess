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

"""Simulation options dialog, generated from :class:`hermess.config.Config`.

The form is built from the pydantic field annotations, so a new config field
appears here without GUI changes (in the "Other" tab unless added to
``_GROUPS``). The dialog edits a plain overrides dict on top of the shipped
defaults; only values that differ from the defaults are kept, so a run uses
exactly what :func:`hermess.simulate` would use plus the user's changes.
"""

from __future__ import annotations

import json
import typing

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hermess.config import Config, config as default_config

# Fields the GUI owns (system selection, figure switches): never shown.
_HIDDEN = {
    "testsystemfile",
    "system_root",
    "plot",
    "plot_voltage",
    "plot_diff",
    "print_power_flow",
    "small_signal_figures",
    "T_start",
}

_GROUPS = {
    "General": ["T_end", "ts", "fn", "Sb"],
    "Integrator": ["int_scheme_sim", "int_scheme_sim_options"],
    "Reference frame": ["omega_mode", "omega_single_idx"],
    "Model && analysis": [
        "line_dyn",
        "incl_lim",
        "skip_disturance",
        "small_signal_analysis",
        "debug_check_init",
        "log_level",
    ],
}

_LABELS = {
    "T_end": "End time [s]",
    "ts": "Time step [s]",
    "fn": "Frequency [Hz]",
    "Sb": "Base power [MW]",
    "int_scheme_sim": "Integration scheme",
    "int_scheme_sim_options": "Integrator options (JSON)",
    "omega_mode": "Reference frame",
    "omega_single_idx": "Reference device (single mode)",
    "line_dyn": "Dynamic network (line differential equations)",
    "incl_lim": "Include state limiters (slower)",
    "skip_disturance": "Skip disturbances",
    "small_signal_analysis": "Small-signal analysis at the operating point",
    "debug_check_init": "Debug initialization check",
    "log_level": "Log level",
}


def validate_overrides(overrides: dict) -> None:
    """Raise when an overrides dict does not fit the current Config schema.

    ``Config.updated`` (pydantic ``model_copy``) skips validation, and the
    model ignores unknown keys, so both must be checked explicitly here.
    """
    unknown = set(overrides) - set(Config.model_fields)
    if unknown:
        raise ValueError(f"Unknown configuration fields: {sorted(unknown)}")
    Config.model_validate({**default_config.model_dump(), **overrides})


def _literal_choices(annotation):
    """The Literal[...] choices of an annotation, unwrapping Optional; or None."""
    for candidate in (annotation, *typing.get_args(annotation)):
        if typing.get_origin(candidate) is typing.Literal:
            return list(typing.get_args(candidate))
    return None


def _is_optional(annotation) -> bool:
    return type(None) in typing.get_args(annotation)


class OptionsDialog(QDialog):
    """Edits config overrides; :meth:`overrides` returns the resulting dict."""

    def __init__(self, overrides: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulation options")
        self.setMinimumWidth(480)
        self._defaults = default_config.model_dump()
        self._widgets: dict[str, QWidget] = {}
        self._result = dict(overrides)

        fields = {
            name: field
            for name, field in Config.model_fields.items()
            if name not in _HIDDEN
        }
        grouped = {name for names in _GROUPS.values() for name in names}
        tabs = QTabWidget(self)
        for title, names in _GROUPS.items():
            page = QWidget()
            form = QFormLayout(page)
            for name in names:
                if name in fields:
                    form.addRow(_LABELS.get(name, name), self._make_widget(name, fields[name]))
            tabs.addTab(page, title)
        leftover = [name for name in fields if name not in grouped]
        if leftover:
            page = QWidget()
            form = QFormLayout(page)
            for name in leftover:
                form.addRow(_LABELS.get(name, name), self._make_widget(name, fields[name]))
            tabs.addTab(page, "Other")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def overrides(self) -> dict:
        """The edited overrides (only values differing from the defaults)."""
        return self._result

    # ---- widget construction -------------------------------------------------

    def _current(self, name):
        return self._result.get(name, self._defaults[name])

    def _make_widget(self, name: str, field) -> QWidget:
        annotation = field.annotation
        value = self._current(name)
        choices = _literal_choices(annotation)

        if annotation is bool:
            widget = QCheckBox()
            widget.setChecked(bool(value))
        elif choices is not None:
            widget = QComboBox()
            for choice in choices:
                widget.addItem(str(choice), choice)
            widget.setCurrentIndex(max(widget.findData(value), 0))
        elif annotation is dict or typing.get_origin(annotation) is dict:
            widget = QPlainTextEdit()
            widget.setPlainText(json.dumps(value, indent=2))
            widget.setFixedHeight(120)
        else:
            widget = QLineEdit()
            widget.setText("" if value is None else str(value))
            if _is_optional(annotation):
                widget.setPlaceholderText("empty = default")

        self._widgets[name] = widget
        return widget

    # ---- collection ----------------------------------------------------------

    def _read_widget(self, name: str, widget: QWidget):
        annotation = Config.model_fields[name].annotation
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, QPlainTextEdit):
            return json.loads(widget.toPlainText() or "{}")
        text = widget.text().strip()
        if not text:
            if _is_optional(annotation):
                return None
            raise ValueError(f"{name} must not be empty")
        if annotation is float or float in typing.get_args(annotation):
            return float(text)
        if annotation is int or int in typing.get_args(annotation):
            return int(text)
        return text

    def _accept(self) -> None:
        collected = {}
        for name, widget in self._widgets.items():
            try:
                value = self._read_widget(name, widget)
            except (ValueError, json.JSONDecodeError) as exc:
                QMessageBox.warning(
                    self, "Invalid value", f"{_LABELS.get(name, name)}: {exc}"
                )
                return
            if value != self._defaults[name]:
                collected[name] = value
        # Validate the whole set through pydantic before accepting it.
        try:
            validate_overrides(collected)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid options", str(exc))
            return
        self._result = collected
        self.accept()

    def _restore(self) -> None:
        self._result = {}
        for name, widget in self._widgets.items():
            value = self._defaults[name]
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(widget.findData(value), 0))
            elif isinstance(widget, QPlainTextEdit):
                widget.setPlainText(json.dumps(value, indent=2))
            else:
                widget.setText("" if value is None else str(value))
