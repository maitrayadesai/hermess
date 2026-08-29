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

"""Small-signal view: eigenvalue map and modal table, linked both ways."""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hermess.gui import theme

# Damping-ratio guide rays drawn on the eigenvalue map.
_GUIDE_ZETAS = (0.05, 0.10)


class SmallSignalTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ss = None
        self._guides = []

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["#", "Eigenvalue", "f [Hz]", "ζ [%]", "Dominant states"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._highlight_from_table)

        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "Re(λ) [1/s]")
        self._plot.setLabel("left", "Im(λ) [rad/s]")
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        theme.style_plot(self._plot)

        self._scatter = pg.ScatterPlotItem(
            size=9,
            pen=pg.mkPen(theme.ETH_BLUE),
            brush=pg.mkBrush(theme.ETH_BLUE + "90"),
            hoverable=True,
            tip=self._tip,
        )
        self._scatter.sigClicked.connect(self._select_from_plot)
        self._plot.addItem(self._scatter)
        self._highlight = pg.ScatterPlotItem(
            size=14, pen=pg.mkPen(theme.ETH_RED, width=2), brush=None
        )
        self._plot.addItem(self._highlight)

        # Participation factors of the selected mode, as horizontal bars.
        self._part_plot = pg.PlotWidget()
        self._part_plot.setLabel("bottom", "Participation factor (normalized)")
        self._part_plot.setTitle("Select a mode to see its participation factors")
        self._part_plot.showGrid(x=True, alpha=0.2)
        self._part_plot.getViewBox().invertY(True)  # largest participation on top
        self._part_plot.setMouseEnabled(x=False, y=False)
        theme.style_plot(self._part_plot)
        self._part_bars = None

        self._placeholder = QLabel(
            "No small-signal data.\nEnable the small-signal analysis in the "
            "simulation options and run again."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {theme.ETH_GREY};")

        right = QSplitter(Qt.Vertical)
        right.addWidget(self._plot)
        right.addWidget(self._part_plot)
        right.setSizes([420, 260])

        splitter = QSplitter()
        splitter.addWidget(self._table)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 480])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._placeholder)
        layout.addWidget(splitter)
        splitter.setVisible(False)
        self._splitter = splitter

    def set_results(self, results) -> None:
        self._ss = results.small_signal if results is not None else None
        has_data = self._ss is not None and self._ss.eigenvalues.size > 0
        self._splitter.setVisible(has_data)
        self._placeholder.setVisible(not has_data)
        if not has_data:
            self._scatter.clear()
            self._table.setRowCount(0)
            self._show_participation(None)
            return
        self._fill_table()
        self._fill_plot()
        self._show_participation(None)

    # ---- internals -----------------------------------------------------------

    def _fill_table(self) -> None:
        modes = self._ss.modes
        self._table.setRowCount(len(modes))
        for row, mode in enumerate(modes):
            eig = mode["eig"]
            eig_text = (
                f"{eig.real:+.3f} ± {abs(eig.imag):.3f}j"
                if mode["is_complex"]
                else f"{eig.real:+.3f}"
            )
            freq_text = f"{mode['freq_hz']:.3f}" if mode["is_complex"] else "—"
            dominant = ", ".join(
                f"{name} ({pf:.0%})" for name, pf in mode["dominant"][:3]
            )
            for col, text in enumerate(
                [str(mode["id"]), eig_text, freq_text, f"{mode['zeta'] * 100:+.1f}", dominant]
            ):
                item = QTableWidgetItem(text)
                if col == 3 and mode["zeta"] < 0.05:
                    item.setForeground(pg.mkColor(theme.ETH_RED))
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()

    def _fill_plot(self) -> None:
        eigs = self._ss.eigenvalues
        # Map every raw eigenvalue to its mode id for tooltips and selection.
        eig_mode = {}
        for mode in self._ss.modes:
            for member in mode["members"]:
                eig_mode[member] = mode
        spots = [
            {"pos": (eigs[i].real, eigs[i].imag), "data": eig_mode.get(i)}
            for i in range(eigs.size)
        ]
        self._scatter.setData(spots)
        self._highlight.clear()
        self._draw_guides()

    def _draw_guides(self) -> None:
        """Constant-damping rays sigma = -zeta/sqrt(1-zeta^2) * |omega|."""
        for item in self._guides:
            self._plot.removeItem(item)
        self._guides = []
        eigs = self._ss.eigenvalues
        max_im = float(np.max(np.abs(eigs.imag))) or 1.0
        pen = pg.mkPen(theme.ETH_GREY, style=Qt.DashLine, width=1)
        for zeta in _GUIDE_ZETAS:
            slope = zeta / math.sqrt(1 - zeta**2)
            for sign in (1.0, -1.0):
                curve = pg.PlotDataItem(
                    [0.0, -slope * max_im], [0.0, sign * max_im], pen=pen
                )
                curve.setZValue(-10)
                self._plot.addItem(curve)
                self._guides.append(curve)
        zero = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(theme.TEXT, width=1))
        zero.setZValue(-10)
        self._plot.addItem(zero)
        self._guides.append(zero)

    @staticmethod
    def _tip(x, y, data) -> str:
        if data is None:
            return f"{x:.3f} + {y:.3f}j"
        return (
            f"mode {data['id']}: f = {data['freq_hz']:.3f} Hz, "
            f"ζ = {data['zeta'] * 100:.1f}%"
        )

    def _select_from_plot(self, _scatter, points) -> None:
        if len(points) == 0:  # a numpy array; plain truthiness raises
            return
        mode = points[0].data()
        if mode is None:
            return
        for row in range(self._table.rowCount()):
            if self._table.item(row, 0).text() == str(mode["id"]):
                self._table.selectRow(row)
                break

    def _highlight_from_table(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        self._highlight.clear()
        if not rows or self._ss is None:
            self._show_participation(None)
            return
        mode_id = int(self._table.item(rows[0].row(), 0).text())
        for mode in self._ss.modes:
            if mode["id"] == mode_id:
                eigs = self._ss.eigenvalues
                self._highlight.setData(
                    [eigs[m].real for m in mode["members"]],
                    [eigs[m].imag for m in mode["members"]],
                )
                self._show_participation(mode)
                break

    def _show_participation(self, mode, top: int = 12) -> None:
        if self._part_bars is not None:
            self._part_plot.removeItem(self._part_bars)
            self._part_bars = None
        axis = self._part_plot.getAxis("left")
        if mode is None:
            axis.setTicks([[]])
            self._part_plot.setTitle(
                "Select a mode to see its participation factors"
            )
            return
        dominant = mode["dominant"][:top]
        names = [name for name, _pf in dominant]
        values = [pf for _name, pf in dominant]
        ys = list(range(len(dominant)))
        self._part_bars = pg.BarGraphItem(
            x0=0,
            y=ys,
            height=0.7,
            width=values,
            brush=pg.mkBrush(theme.ETH_BLUE),
            pen=pg.mkPen(None),
        )
        self._part_plot.addItem(self._part_bars)
        axis.setTicks([list(zip(ys, names))])
        self._part_plot.setXRange(0, max(values) * 1.1 if values else 1.0)
        self._part_plot.setYRange(-0.6, len(dominant) - 0.4, padding=0)
        label = (
            f"mode {mode['id']}: f = {mode['freq_hz']:.3f} Hz, "
            f"ζ = {mode['zeta'] * 100:.1f}%"
        )
        self._part_plot.setTitle(label)
