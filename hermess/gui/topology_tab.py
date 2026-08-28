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

"""One-line diagram of the selected system, with an edit mode for building.

In view mode the diagram is read-only: draggable nodes, double-click detail
pop-ups (:mod:`hermess.gui.info_dialog`), power-flow annotation after a run.
Edit mode adds a tool palette on the same canvas: place buses, connect lines,
attach devices (with forms generated from the model classes), delete, edit
the disturbance sequence, undo/redo. The edits live in a
:class:`~hermess.gui.sysdoc.SystemDocument` that serializes back to ordinary
system files; saving is owned by the main window.

Node positions come from :mod:`hermess.gui.graphlayout`, are keyed by bus
name, and survive edits; a bus placed by clicking keeps its click position.
"""

from __future__ import annotations

import copy

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hermess.gui import device_info, param_meta, theme
from hermess.gui.disturbance_editor import DisturbanceManagerDialog
from hermess.gui.graphlayout import spring_layout
from hermess.gui.info_dialog import InfoDialog
from hermess.gui.param_form import DeviceFormDialog, SimpleFormDialog
from hermess.gui.sysdoc import SystemDocument

_NODE_SIZE = 18
_GLYPH_OFFSET = 0.11  # distance of a device glyph from its bus
_HIT_FRACTION = 0.03  # click tolerance, as a fraction of the visible x-range

# Glyph (symbol, color, caption) per device family, matched on the class name.
_GLYPHS = [
    ("Synchronous", "o", theme.ETH_PETROL, "synchronous machine"),
    ("GENROU", "o", theme.ETH_PETROL, "synchronous machine"),
    ("GENSAL", "o", theme.ETH_PETROL, "synchronous machine"),
    ("Marconato", "o", theme.ETH_PETROL, "synchronous machine"),
    ("Grid", "s", theme.ETH_RED, "inverter"),
    ("StaticInfiniteBus", "star", "#000000", "infinite bus"),
    ("Static", "t", theme.ETH_GREY, "load"),
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


def _segment_distance(p, a, b) -> float:
    """Distance of point p to the segment a-b (all 2-arrays)."""
    span = b - a
    length2 = float(span @ span)
    if length2 < 1e-12:
        return float(np.linalg.norm(p - a))
    t = float(np.clip((p - a) @ span / length2, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * span)))


class _OneLineGraph(pg.GraphItem):
    """GraphItem with left-drag node repositioning and double-click details."""

    def __init__(self, moved, double_clicked):
        self._moved = moved  # callback(node_index, (x, y))
        self._double_clicked = double_clicked  # callback(node_index)
        self._drag_index = None
        self._drag_offset = None
        super().__init__()

    def mouseDoubleClickEvent(self, ev):
        points = self.scatter.pointsAt(ev.pos())
        if len(points):
            self._double_clicked(int(points[0].data()))
            ev.accept()
        else:
            ev.ignore()

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


class _ClickableScatter(pg.ScatterPlotItem):
    """Device glyph opening its detail pop-up on double click."""

    def __init__(self, double_clicked, **kwargs):
        super().__init__(**kwargs)
        self._double_clicked = double_clicked

    def mouseDoubleClickEvent(self, ev):
        if len(self.pointsAt(ev.pos())):
            self._double_clicked()
            ev.accept()
        else:
            ev.ignore()


class TopologyTab(QWidget):
    #: Emitted after every change to the edited document (edit mode only).
    documentChanged = Signal()
    #: Emitted when edit mode is entered (True) or left (False).
    editModeChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._desc = None
        self._doc: "SystemDocument | None" = None
        self._pos = np.zeros((0, 2))  # (n_buses, 2), aligned with desc.buses()
        self._pos_by_name: "dict[str, np.ndarray]" = {}
        self._graph_kwargs = {}  # full setData kwargs; setData replaces, not merges
        self._annotations = {}  # bus -> (vmag, vdeg)
        self._bus_labels = []
        self._device_items = []  # (bus_index, angle, scatter, label, connector, entry)
        self._validator = None  # callable(desc) -> list[Issue], set by the main window
        self._pending_device_kind: "str | None" = None
        self._pending_line_bus: "str | None" = None

        self._view = pg.PlotWidget()
        self._view.setAspectLocked(True)
        self._view.hideAxis("bottom")
        self._view.hideAxis("left")
        self._view.setMenuEnabled(False)
        self._view.scene().sigMouseClicked.connect(self._on_scene_click)

        self._graph = _OneLineGraph(self._node_moved, self._bus_double_clicked)
        self._view.addItem(self._graph)

        self._edit_toggle = QPushButton("Edit")
        self._edit_toggle.setCheckable(True)
        self._edit_toggle.toggled.connect(self._on_edit_toggled)

        relayout = QPushButton("Re-layout")
        relayout.clicked.connect(self._relayout)

        caption = QLabel(
            f'<span style="color:{theme.ETH_PETROL}">●</span> synchronous machine   '
            f'<span style="color:{theme.ETH_RED}">■</span> inverter   '
            f'<span style="color:{theme.ETH_GREY}">▼</span> load   '
            "★ infinite bus   "
            f'<span style="color:{theme.ETH_BRONZE}">—</span> transformer   '
            f'<span style="color:{theme.ETH_GREY}">(double-click for details, '
            "drag buses to arrange)</span>"
        )

        bar = QHBoxLayout()
        bar.addWidget(caption)
        bar.addStretch(1)
        bar.addWidget(relayout)
        bar.addWidget(self._edit_toggle)

        self._edit_bar = self._build_edit_bar()
        self._edit_bar.setVisible(False)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(bar)
        layout.addWidget(self._edit_bar)
        layout.addWidget(self._view)
        layout.addWidget(self._status)

    def _build_edit_bar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)

        self._tools = QButtonGroup(self)
        self._tools.setExclusive(True)
        self._tool_buttons: "dict[str, QToolButton]" = {}
        for tool, label, tip in [
            ("move", "Move", "Drag buses, double-click to edit an element"),
            ("bus", "+ Bus", "Click on the canvas to place a bus"),
            ("line", "+ Line", "Click two buses to connect them"),
            ("delete", "Delete", "Click a bus, device or line to remove it"),
        ]:
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tip)
            button.setCheckable(True)
            self._tools.addButton(button)
            self._tool_buttons[tool] = button
            row.addWidget(button)
        self._tool_buttons["move"].setChecked(True)

        device_button = QToolButton()
        device_button.setText("+ Device ▾")
        device_button.setToolTip("Pick a model, then click the bus to attach it to")
        device_button.setCheckable(True)
        device_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(device_button)
        for kind in param_meta.buildable_device_kinds():
            menu.addAction(kind, lambda kind=kind: self._pick_device_kind(kind))
        device_button.setMenu(menu)
        self._tools.addButton(device_button)
        self._tool_buttons["device"] = device_button
        row.addWidget(device_button)

        row.addSpacing(12)
        disturbances = QPushButton("Disturbances…")
        disturbances.clicked.connect(self._edit_disturbances)
        row.addWidget(disturbances)

        undo = QPushButton("Undo")
        undo.clicked.connect(self._undo)
        redo = QPushButton("Redo")
        redo.clicked.connect(self._redo)
        row.addWidget(undo)
        row.addWidget(redo)
        row.addStretch(1)
        return bar

    # ---- public --------------------------------------------------------------

    @property
    def document(self) -> "SystemDocument | None":
        """The edited document, while edit mode is active (else None)."""
        return self._doc

    @property
    def editing(self) -> bool:
        return self._doc is not None

    def set_validator(self, validator) -> None:
        """Callable(desc) -> list of validation Issues, for the live status."""
        self._validator = validator

    def set_system(self, desc) -> None:
        """Show a parsed system read-only (leaves edit mode; may be None)."""
        if self.editing:
            self._leave_edit()
        self._desc = desc
        self._annotations = {}
        self._pos_by_name = {}
        self._render()
        if desc is not None and desc.buses():
            self._view.autoRange(padding=0.15)

    def begin_edit(self, document: "SystemDocument | None" = None) -> None:
        """Enter edit mode, on a copy of the shown system or a given document
        (e.g. a blank one for File > New system)."""
        if document is None:
            document = (
                SystemDocument(copy.deepcopy(self._desc))
                if self._desc is not None
                else SystemDocument.blank()
            )
        self._doc = document
        self._desc = document.desc
        self._annotations = {}
        self._edit_toggle.blockSignals(True)
        self._edit_toggle.setChecked(True)
        self._edit_toggle.blockSignals(False)
        self._edit_bar.setVisible(True)
        self._status.setVisible(True)
        self._render()
        self._update_status()
        self.editModeChanged.emit(True)

    # ---- edit-mode plumbing --------------------------------------------------

    def _on_edit_toggled(self, checked: bool) -> None:
        if checked and not self.editing:
            self.begin_edit()
        elif not checked and self.editing:
            self._leave_edit()
            self.editModeChanged.emit(False)

    def _leave_edit(self) -> None:
        # The document (saved or not) keeps being shown read-only; the main
        # window owns the save/discard decision.
        self._doc = None
        self._pending_line_bus = None
        self._edit_toggle.blockSignals(True)
        self._edit_toggle.setChecked(False)
        self._edit_toggle.blockSignals(False)
        self._edit_bar.setVisible(False)
        self._status.setVisible(False)

    def _active_tool(self) -> str:
        for tool, button in self._tool_buttons.items():
            if button.isChecked():
                return tool
        return "move"

    def _pick_device_kind(self, kind: str) -> None:
        self._pending_device_kind = kind
        button = self._tool_buttons["device"]
        button.setText(f"+ {kind} ▾")
        button.setChecked(True)

    def _changed(self, new_bus_positions: "dict[str, tuple] | None" = None) -> None:
        """Re-render after a document mutation and announce it."""
        for name, position in (new_bus_positions or {}).items():
            self._pos_by_name[name] = np.asarray(position, dtype=float)
        self._desc = self._doc.desc
        self._render()
        self._update_status()
        self.documentChanged.emit()

    def _undo(self) -> None:
        if self.editing and self._doc.can_undo():
            self._doc.undo()
            self._changed()

    def _redo(self) -> None:
        if self.editing and self._doc.can_redo():
            self._doc.redo()
            self._changed()

    def _edit_disturbances(self) -> None:
        if self.editing:
            DisturbanceManagerDialog(self._doc, parent=self).exec()
            self._changed()

    def _update_status(self) -> None:
        if not self.editing:
            return
        desc = self._desc
        counts = (
            f"{len(desc.buses())} buses, {len(desc.lines)} lines, "
            f"{len(desc.devices)} devices, {len(desc.disturbances)} disturbances."
        )
        issues = self._validator(desc) if self._validator is not None else []
        shown = []
        for issue in issues[:3]:
            color = theme.ETH_RED if issue.severity == "error" else theme.ETH_BRONZE
            shown.append(f'<span style="color:{color}">{issue.message}</span>')
        if len(issues) > 3:
            shown.append(f"… and {len(issues) - 3} more")
        self._status.setText("<br>".join([counts] + shown))

    # ---- canvas interaction --------------------------------------------------

    def _hit_threshold(self) -> float:
        (x0, x1), _ = self._view.getPlotItem().vb.viewRange()
        return max((x1 - x0) * _HIT_FRACTION, 1e-6)

    def _nearest_bus(self, point) -> "str | None":
        buses = self._desc.buses() if self._desc is not None else []
        if not buses:
            return None
        distances = np.linalg.norm(self._pos - point, axis=1)
        i = int(np.argmin(distances))
        return buses[i] if distances[i] <= self._hit_threshold() else None

    def _nearest_device(self, point):
        best, best_distance = None, self._hit_threshold()
        for i, angle, _s, _l, _c, entry in self._device_items:
            glyph = self._pos[i] + _GLYPH_OFFSET * np.array(
                [np.cos(angle), np.sin(angle)]
            )
            distance = float(np.linalg.norm(glyph - point))
            if distance <= best_distance:
                best, best_distance = entry, distance
        return best

    def _nearest_line(self, point):
        index = {bus: i for i, bus in enumerate(self._desc.buses())}
        best, best_distance = None, self._hit_threshold()
        for entry in self._desc.lines:
            i, j = index.get(entry.get("bus_i")), index.get(entry.get("bus_j"))
            if i is None or j is None:
                continue
            distance = _segment_distance(point, self._pos[i], self._pos[j])
            if distance <= best_distance:
                best, best_distance = entry, distance
        return best

    def _on_scene_click(self, ev) -> None:
        if not self.editing or ev.button() != Qt.LeftButton:
            return
        tool = self._active_tool()
        if tool == "move":
            return
        vb = self._view.getPlotItem().vb
        p = vb.mapSceneToView(ev.scenePos())
        point = np.array([p.x(), p.y()])

        if tool == "bus":
            if self._nearest_bus(point) is None:
                name = self._doc.add_bus()
                self._changed({name: point})
        elif tool == "line":
            self._line_tool_click(point)
        elif tool == "device":
            bus = self._nearest_bus(point)
            if bus is not None and self._pending_device_kind:
                self._add_device_at(self._pending_device_kind, bus)
        elif tool == "delete":
            self._delete_at(point)

    def _line_tool_click(self, point) -> None:
        bus = self._nearest_bus(point)
        if bus is None or bus == self._pending_line_bus:
            self._pending_line_bus = None
            self._status.setText("Line: cancelled.")
            return
        if self._pending_line_bus is None:
            self._pending_line_bus = bus
            self._status.setText(
                f"Line: from bus {bus} — click the second bus."
            )
            return
        self._doc.add_line(self._pending_line_bus, bus)
        self._pending_line_bus = None
        self._changed()

    def _add_device_at(self, kind: str, bus: str) -> None:
        dialog = DeviceFormDialog(kind, bus, parent=self)
        if dialog.exec():
            self._doc.add_device(kind, bus, dialog.values())
            self._changed()

    def _delete_at(self, point) -> None:
        device = self._nearest_device(point)
        if device is not None:
            self._doc.remove_entry(device)
            self._changed()
            return
        bus = self._nearest_bus(point)
        if bus is not None:
            self._doc.remove_bus(bus)
            self._changed()
            return
        line = self._nearest_line(point)
        if line is not None:
            self._doc.remove_entry(line)
            self._changed()

    # ---- edit dialogs --------------------------------------------------------

    def _bus_double_clicked(self, node_index: int) -> None:
        if not self.editing:
            self._show_bus_info(node_index)
            return
        bus = self._desc.buses()[node_index]
        init = next(
            (e for e in self._desc.bus_inits if e.get("bus") == bus), None
        )
        params = {k: v for k, v in (init.params if init else {}).items() if k != "bus"}
        dialog = SimpleFormDialog(
            f"Bus {bus} initialization",
            param_meta.businit_meta(),
            params=params,
            combos={"type": ["slack", "PV", "PQ"]},
            parent=self,
        )
        if dialog.exec():
            self._doc.set_businit(bus, dialog.values())
            self._changed()

    def _device_double_clicked(self, entry) -> None:
        if not self.editing:
            self._show_device_info(entry)
            return
        bus = entry.get("bus")
        dialog = DeviceFormDialog(entry.kind, bus, params=entry.params, parent=self)
        if dialog.exec():
            self._doc.update_entry(entry, {"bus": bus, **dialog.values()})
            self._changed()

    # ---- rendering -----------------------------------------------------------

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
        if self._desc is not None and self._bus_labels:
            self._update_labels()

    def _render(self) -> None:
        if self._desc is None or not self._desc.buses():
            self._clear_items()
            self._graph_kwargs = {}
            self._graph.setData(pos=np.zeros((0, 2)), adj=np.zeros((0, 2), dtype=int))
            return
        self._ensure_positions()
        self._rebuild()

    def _ensure_positions(self) -> None:
        """Positions for every bus: keep known ones, lay out the new ones."""
        buses = self._desc.buses()
        unknown = [b for b in buses if b not in self._pos_by_name]
        if unknown:
            if len(unknown) == len(buses):
                index = {bus: i for i, bus in enumerate(buses)}
                edges = [
                    (index[e.get("bus_i")], index[e.get("bus_j")])
                    for e in self._desc.lines
                    if e.get("bus_i") in index and e.get("bus_j") in index
                ]
                layout = spring_layout(len(buses), edges)
                for bus, position in zip(buses, layout):
                    self._pos_by_name[bus] = position
            else:
                # New buses normally arrive with a click position; this is the
                # fallback (e.g. after undo of a deletion): fan out near the
                # centroid of the existing ones.
                known = np.array(
                    [self._pos_by_name[b] for b in buses if b in self._pos_by_name]
                )
                base = known.mean(axis=0)
                for k, bus in enumerate(unknown):
                    self._pos_by_name[bus] = base + np.array(
                        [0.18 * (k + 1), 0.12 * (k + 1)]
                    )
        self._pos_by_name = {b: self._pos_by_name[b] for b in buses}
        self._pos = np.array([self._pos_by_name[b] for b in buses])

    def _clear_items(self) -> None:
        for label in self._bus_labels:
            self._view.removeItem(label)
        for _bus, _angle, scatter, label, connector, _entry in self._device_items:
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
                scatter = _ClickableScatter(
                    lambda entry=entry: self._device_double_clicked(entry),
                    symbol=symbol,
                    size=13,
                    pen=pg.mkPen(color),
                    brush=pg.mkBrush(pg.mkColor(color).lighter(160)),
                )
                name = entry.get("idx") or entry.kind
                label = pg.TextItem(name, anchor=(0.5, -0.35), color=color)
                for item in (connector, scatter, label):
                    self._view.addItem(item)
                self._device_items.append((i, angle, scatter, label, connector, entry))

        self._update_positions()
        self._update_labels()

    # ---- geometry ------------------------------------------------------------

    def _node_moved(self, node_index: int, position) -> None:
        self._pos[node_index] = position
        self._pos_by_name[self._desc.buses()[node_index]] = np.asarray(position)
        self._update_positions()

    def _relayout(self) -> None:
        if self._desc is None or not self._desc.buses():
            return
        self._pos_by_name = {}
        self._ensure_positions()
        self._update_positions()
        self._view.autoRange(padding=0.15)

    def _update_positions(self) -> None:
        self._graph.setData(pos=self._pos.copy(), **self._graph_kwargs)
        for i, label in enumerate(self._bus_labels):
            label.setPos(*self._pos[i])
        for i, angle, scatter, label, connector, _entry in self._device_items:
            glyph = self._pos[i] + _GLYPH_OFFSET * np.array(
                [np.cos(angle), np.sin(angle)]
            )
            scatter.setData([glyph[0]], [glyph[1]])
            label.setPos(*glyph)
            connector.setData(
                [self._pos[i][0], glyph[0]], [self._pos[i][1], glyph[1]]
            )

    # ---- detail pop-ups (view mode) ------------------------------------------

    def _show_device_info(self, entry) -> None:
        import html as _html

        title = f"{entry.get('idx') or entry.kind} — {entry.kind}"
        description = device_info.class_description(entry.kind)
        description = _html.escape(description) if description else None
        root = device_info.schematics_dir()
        diagrams = []
        if root is not None:
            diagrams = [
                (caption, root / filename)
                for caption, filename in device_info.schematics_for(entry)
                if (root / filename).exists()
            ]
        InfoDialog(
            title, description, params=entry.params, diagrams=diagrams, parent=self
        ).show()

    def _show_bus_info(self, node_index: int) -> None:
        import html as _html

        bus = self._desc.buses()[node_index]
        parts = []
        init = next((e for e in self._desc.bus_inits if e.get("bus") == bus), None)
        if init is not None:
            fields = ", ".join(
                f"{k} = {v}" for k, v in init.params.items() if k != "bus"
            )
            parts.append(f"Initialization: {_html.escape(fields)}")
        if bus in self._annotations:
            vmag, vdeg = self._annotations[bus]
            parts.append(
                f"Initialized voltage (shown run): {vmag:.4f} p.u. ∠ {vdeg:.2f}°"
            )
        devices = [
            f"{e.get('idx') or e.kind} ({e.kind})"
            for e in self._desc.devices
            if e.get("bus") == bus
        ]
        if devices:
            parts.append("Devices: " + _html.escape(", ".join(devices)))
        lines = [
            f"to bus {e.get('bus_j') if e.get('bus_i') == bus else e.get('bus_i')}"
            + (
                f" (r = {e.get('r')}, x = {e.get('x')}"
                + (", transformer)" if _is_transformer(e) else ")")
            )
            for e in self._desc.lines
            if bus in (e.get("bus_i"), e.get("bus_j"))
        ]
        if lines:
            parts.append("Branches: " + _html.escape("; ".join(lines)))
        InfoDialog(
            f"Bus {bus}",
            "<br>".join(parts) or "No further data for this bus.",
            doc_link=False,
            parent=self,
        ).show()

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
