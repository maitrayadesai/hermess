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

"""One-line diagram of the selected system (read-only, draggable nodes).

Built from the parsed text files, so it works before any simulation; after a
run of the same system the buses are annotated with the initial power flow
(|V| and angle). Node positions come from :mod:`hermess.gui.graphlayout` and
can be adjusted by dragging.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hermess.gui import theme
from hermess.gui.graphlayout import spring_layout

_NODE_SIZE = 18
_GLYPH_OFFSET = 0.11  # distance of a device glyph from its bus

# Glyph (symbol, color, caption) per device family, matched on the class name.
_GLYPHS = [
    ("Synchronous", "o", theme.ETH_PETROL, "synchronous machine"),
    ("Grid", "s", theme.ETH_RED, "inverter"),
    ("Static", "t", theme.ETH_GREY, "load"),
    ("Infinite", "star", "#000000", "infinite bus"),
]
_GLYPH_OTHER = ("d", theme.ETH_PURPLE, "other device")


def _glyph_for(kind: str):
    for prefix, symbol, color, caption in _GLYPHS:
        if kind.startswith(prefix):
            return symbol, color, caption
    return _GLYPH_OTHER


def _is_transformer(entry) -> bool:
    try:
        return abs(float(entry.get("trafo", "1") or "1") - 1.0) > 1e-9
    except ValueError:
        return False


class _OneLineGraph(pg.GraphItem):
    """GraphItem with left-drag node repositioning."""

    def __init__(self, moved):
        self._moved = moved  # callback(node_index, (x, y))
        self._drag_index = None
        self._drag_offset = None
        super().__init__()

    def mouseDragEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            ev.ignore()
            return
        if ev.isStart():
            points = self.scatter.pointsAt(ev.buttonDownPos())
            if not len(points):
                ev.ignore()
                return
            self._drag_index = int(points[0].data())
            self._drag_offset = self.pos[self._drag_index] - [
                ev.buttonDownPos().x(),
                ev.buttonDownPos().y(),
            ]
        elif ev.isFinish():
            self._drag_index = None
            return
        if self._drag_index is None:
            ev.ignore()
            return
        position = np.array([ev.pos().x(), ev.pos().y()]) + self._drag_offset
        self._moved(self._drag_index, position)
        ev.accept()


class TopologyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._desc = None
        self._pos = None  # (n_buses, 2)
        self._graph_kwargs = {}  # full setData kwargs; setData replaces, not merges
        self._annotations = {}  # bus -> (vmag, vdeg)
        self._bus_labels = []
        self._device_items = []  # (bus_index, angle, scatter, label, connector)

        self._view = pg.PlotWidget()
        self._view.setAspectLocked(True)
        self._view.hideAxis("bottom")
        self._view.hideAxis("left")
        self._view.setMenuEnabled(False)

        self._graph = _OneLineGraph(self._node_moved)
        self._view.addItem(self._graph)

        relayout = QPushButton("Re-layout")
        relayout.clicked.connect(self._relayout)

        caption = QLabel(
            f'<span style="color:{theme.ETH_PETROL}">●</span> synchronous machine   '
            f'<span style="color:{theme.ETH_RED}">■</span> inverter   '
            f'<span style="color:{theme.ETH_GREY}">▼</span> load   '
            "★ infinite bus   "
            f'<span style="color:{theme.ETH_BRONZE}">—</span> transformer'
        )

        bar = QHBoxLayout()
        bar.addWidget(caption)
        bar.addStretch(1)
        bar.addWidget(relayout)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(bar)
        layout.addWidget(self._view)

    # ---- public --------------------------------------------------------------

    def set_system(self, desc) -> None:
        """Show a parsed system (may be None to clear)."""
        self._desc = desc
        self._annotations = {}
        if desc is None or not desc.buses():
            self._clear_items()
            self._graph_kwargs = {}
            self._graph.setData(pos=np.zeros((0, 2)), adj=np.zeros((0, 2), dtype=int))
            return
        self._layout_positions()
        self._rebuild()
        self._view.autoRange(padding=0.15)

    def set_results(self, results) -> None:
        """Annotate the buses with a finished run's initial power flow."""
        self._annotations = {}
        if (
            results is not None
            and self._desc is not None
            and results.power_flow_bus is not None
            # A run of another system must not annotate this diagram.
            and results.system.split("/")[-1] == self._desc.name
        ):
            table = results.power_flow_bus
            for _, row in table.iterrows():
                self._annotations[str(row["Bus"])] = (
                    float(row["V Magnitude (pu)"]),
                    float(row["V Phase (deg)"]),
                )
        if self._desc is not None:
            self._update_labels()

    # ---- construction --------------------------------------------------------

    def _layout_positions(self) -> None:
        buses = self._desc.buses()
        index = {bus: i for i, bus in enumerate(buses)}
        edges = [
            (index[e.get("bus_i")], index[e.get("bus_j")])
            for e in self._desc.lines
            if e.get("bus_i") in index and e.get("bus_j") in index
        ]
        self._pos = spring_layout(len(buses), edges)

    def _clear_items(self) -> None:
        for label in self._bus_labels:
            self._view.removeItem(label)
        for _bus, _angle, scatter, label, connector in self._device_items:
            self._view.removeItem(scatter)
            self._view.removeItem(label)
            self._view.removeItem(connector)
        self._bus_labels = []
        self._device_items = []

    def _rebuild(self) -> None:
        self._clear_items()
        desc = self._desc
        buses = desc.buses()
        index = {bus: i for i, bus in enumerate(buses)}

        adjacency = []
        pens = []
        for entry in desc.lines:
            i, j = index.get(entry.get("bus_i")), index.get(entry.get("bus_j"))
            if i is None or j is None:
                continue
            adjacency.append((i, j))
            color = theme.ETH_BRONZE if _is_transformer(entry) else "#9A9DA2"
            c = pg.mkColor(color)
            pens.append((c.red(), c.green(), c.blue(), 255, 2.5))
        adjacency = np.array(adjacency, dtype=int).reshape(-1, 2)
        pens = np.array(
            pens,
            dtype=[
                ("red", np.ubyte),
                ("green", np.ubyte),
                ("blue", np.ubyte),
                ("alpha", np.ubyte),
                ("width", float),
            ],
        )
        self._graph_kwargs = dict(
            adj=adjacency,
            pen=pens,
            size=_NODE_SIZE,
            symbol="o",
            symbolPen=pg.mkPen(theme.ETH_BLUE, width=2),
            symbolBrush=pg.mkBrush("#FFFFFF"),
            data=np.arange(len(buses)),
            pxMode=True,
        )

        for bus in buses:
            label = pg.TextItem(anchor=(0.5, -0.4), color=theme.TEXT)
            self._view.addItem(label)
            self._bus_labels.append(label)

        # Device glyphs, fanned out around their bus away from the graph center.
        center = self._pos.mean(axis=0)
        per_bus: dict[int, list] = {}
        for entry in desc.devices:
            i = index.get(entry.get("bus"))
            if i is not None:
                per_bus.setdefault(i, []).append(entry)
        for i, entries in per_bus.items():
            outward = self._pos[i] - center
            base = np.arctan2(outward[1], outward[0]) if np.linalg.norm(outward) > 1e-9 else np.pi / 2
            for slot, entry in enumerate(entries):
                angle = base + (slot - (len(entries) - 1) / 2) * 0.7
                symbol, color, _caption = _glyph_for(entry.kind)
                connector = pg.PlotDataItem(pen=pg.mkPen("#B0B3B8", width=1))
                scatter = pg.ScatterPlotItem(
                    symbol=symbol,
                    size=13,
                    pen=pg.mkPen(color),
                    brush=pg.mkBrush(pg.mkColor(color).lighter(160)),
                )
                name = entry.get("idx") or entry.kind
                label = pg.TextItem(name, anchor=(0.5, -0.35), color=color)
                for item in (connector, scatter, label):
                    self._view.addItem(item)
                self._device_items.append((i, angle, scatter, label, connector))

        self._update_positions()
        self._update_labels()

    # ---- geometry ------------------------------------------------------------

    def _node_moved(self, node_index: int, position) -> None:
        self._pos[node_index] = position
        self._update_positions()

    def _relayout(self) -> None:
        if self._desc is None:
            return
        self._layout_positions()
        self._update_positions()
        self._view.autoRange(padding=0.15)

    def _update_positions(self) -> None:
        self._graph.setData(pos=self._pos.copy(), **self._graph_kwargs)
        for i, label in enumerate(self._bus_labels):
            label.setPos(*self._pos[i])
        for i, angle, scatter, label, connector in self._device_items:
            glyph = self._pos[i] + _GLYPH_OFFSET * np.array(
                [np.cos(angle), np.sin(angle)]
            )
            scatter.setData([glyph[0]], [glyph[1]])
            label.setPos(*glyph)
            connector.setData(
                [self._pos[i][0], glyph[0]], [self._pos[i][1], glyph[1]]
            )

    def _update_labels(self) -> None:
        for bus, label in zip(self._desc.buses(), self._bus_labels):
            if bus in self._annotations:
                vmag, vdeg = self._annotations[bus]
                label.setHtml(
                    f'<div style="text-align:center"><b>{bus}</b><br>'
                    f'<span style="font-size:8pt">{vmag:.3f} ∠ {vdeg:.1f}°</span></div>'
                )
            else:
                label.setHtml(f"<b>{bus}</b>")
