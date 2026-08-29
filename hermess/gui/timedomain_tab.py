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

"""Time-domain view: a checkable signal tree and an overlaid pyqtgraph plot."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hermess.gui import theme

# Device model names are long; abbreviate the common ones in the tree.
_MODEL_ABBREV = {
    "Synchronous_machine_transient_model": "SM",
    "Synchronous_machine_subtransient_model": "SM",
    "Synchronous_machine_subtransient_model_Sauer_Pai": "SM (Sauer-Pai)",
    "Synchronous_machine_subtransient_model_Sauer_Pai_6th_order": "SM (Sauer-Pai, 6th)",
    "GridForming_inverter_model": "Grid-forming inverter",
    "GridSupporting_inverter_model": "Grid-supporting inverter",
    "Infinite_bus": "Infinite bus",
}

_ROLE_SIGNAL = Qt.UserRole


class TimeDomainTab(QWidget):
    """Shows one run's trajectories; the tree selects, the plot overlays."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = None

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemChanged.connect(self._replot)

        clear = QPushButton("Clear selection")
        clear.clicked.connect(self._clear_selection)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._tree)
        left_layout.addWidget(clear)

        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "Time [s]")
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._plot.addLegend(
            offset=(10, 10),
            brush=pg.mkBrush(255, 255, 255, 210),
            pen=pg.mkPen(theme.BORDER),
            labelTextColor=theme.TEXT,
        )
        theme.style_plot(self._plot)
        item = self._plot.getPlotItem()
        item.setDownsampling(auto=True, mode="peak")
        item.setClipToView(True)

        self._placeholder = QLabel(
            "No run yet. Select a system and press Run (F5);\n"
            "the trajectories appear here."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {theme.ETH_GREY};")

        self._splitter = QSplitter()
        self._splitter.addWidget(left)
        self._splitter.addWidget(self._plot)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([260, 700])
        self._splitter.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._placeholder)
        layout.addWidget(self._splitter)

    # ---- data ----------------------------------------------------------------

    def set_results(self, results) -> None:
        """Show a run; preserves the checked signals where they still exist."""
        checked = self.selected_signals()
        self._results = results
        self._placeholder.setVisible(results is None)
        self._splitter.setVisible(results is not None)
        self._rebuild_tree(restore=checked)
        self._replot()

    def selected_signals(self) -> "list[tuple]":
        """The checked signal ids, e.g. ``("V", "3")`` or ``("dev", 1, "omega")``."""
        signals = []

        def walk(item):
            for i in range(item.childCount()):
                child = item.child(i)
                sid = child.data(0, _ROLE_SIGNAL)
                if sid is not None and child.checkState(0) == Qt.Checked:
                    signals.append(sid)
                walk(child)

        walk(self._tree.invisibleRootItem())
        return signals

    def signal_array(self, sid: tuple) -> "tuple[str, np.ndarray]":
        """(label, trajectory) of one signal id in the current run."""
        res = self._results
        kind = sid[0]
        if kind == "V":
            return f"|V| {sid[1]}", np.abs(res.voltage[sid[1]])
        if kind == "P":
            return f"P {sid[1]}", np.real(res.power[sid[1]])
        if kind == "Q":
            return f"Q {sid[1]}", np.imag(res.power[sid[1]])
        dev = res.devices[sid[1]]
        return f"{dev.unit}:{sid[2]}", dev.states[sid[2]]

    # ---- internals -----------------------------------------------------------

    def _rebuild_tree(self, restore=()) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        res = self._results
        if res is None:
            self._tree.blockSignals(False)
            return

        def add_group(title):
            group = QTreeWidgetItem(self._tree, [title])
            group.setFlags(group.flags() & ~Qt.ItemIsUserCheckable)
            return group

        def add_signal(group, label, sid):
            item = QTreeWidgetItem(group, [label])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked if sid in restore else Qt.Unchecked)
            item.setData(0, _ROLE_SIGNAL, sid)

        voltages = add_group("Bus voltage magnitude [p.u.]")
        for bus in res.voltage:
            add_signal(voltages, f"Bus {bus}", ("V", bus))
        voltages.setExpanded(True)

        power = add_group("Bus injections [p.u.]")
        for bus in res.power:
            add_signal(power, f"P bus {bus}", ("P", bus))
            add_signal(power, f"Q bus {bus}", ("Q", bus))

        for i, dev in enumerate(res.devices):
            model = _MODEL_ABBREV.get(dev.model, dev.model)
            group = add_group(f"{dev.unit} @ bus {dev.bus} ({model})")
            for state in dev.states:
                add_signal(group, state, ("dev", i, state))

        self._tree.blockSignals(False)

    def _clear_selection(self) -> None:
        self._tree.blockSignals(True)

        def walk(item):
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, _ROLE_SIGNAL) is not None:
                    child.setCheckState(0, Qt.Unchecked)
                walk(child)

        walk(self._tree.invisibleRootItem())
        self._tree.blockSignals(False)
        self._replot()

    def _replot(self) -> None:
        self._plot.clear()
        # clear() removes the legend's items but keeps stale references; reset it.
        legend = self._plot.getPlotItem().legend
        if legend is not None:
            legend.clear()
        if self._results is None:
            return
        t = self._results.t
        colors = {}
        for i, sid in enumerate(self.selected_signals()):
            label, trajectory = self.signal_array(sid)
            colors[sid] = theme.series_color(i)
            n = min(len(t), len(trajectory))
            self._plot.plot(
                t[:n],
                trajectory[:n],
                pen=pg.mkPen(colors[sid], width=1.5),
                name=label,
            )
        self._update_chips(colors)

    _chip_cache: "dict[str, QIcon]" = {}

    @classmethod
    def _chip(cls, color: str) -> QIcon:
        """A small filled square matching the curve color."""
        if color not in cls._chip_cache:
            pixmap = QPixmap(12, 12)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(1, 1, 10, 10, 2, 2)
            painter.end()
            cls._chip_cache[color] = QIcon(pixmap)
        return cls._chip_cache[color]

    def _update_chips(self, colors: dict) -> None:
        """Mark each checked signal in the tree with its curve color."""

        def walk(item):
            for i in range(item.childCount()):
                child = item.child(i)
                sid = child.data(0, _ROLE_SIGNAL)
                if sid is not None:
                    child.setIcon(
                        0, self._chip(colors[sid]) if sid in colors else QIcon()
                    )
                walk(child)

        # setIcon emits itemChanged, which triggers _replot: block while
        # decorating or the two feed each other forever.
        self._tree.blockSignals(True)
        try:
            walk(self._tree.invisibleRootItem())
        finally:
            self._tree.blockSignals(False)
