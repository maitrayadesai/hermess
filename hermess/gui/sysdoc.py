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

"""The editable system document behind the GUI's builder mode.

A :class:`SystemDocument` wraps a mutable
:class:`~hermess.gui.sysparse.SystemDescription` with the operations the
canvas needs (place a bus, connect a line, attach a device, edit and delete),
snapshot-based undo, and a serializer back to the ordinary system files.
The two text files stay the single source of truth: what the builder saves is
a normal system folder that scripts, the CLI and version control handle like
any hand-written one. Parameter values are kept as the raw strings from the
file, so numbers round-trip verbatim; comments and layout of hand-written
files are NOT preserved (the GUI rewrites the files on save).
"""

from __future__ import annotations

import copy
import datetime
from pathlib import Path

import hermess
from hermess.gui.sysparse import Entry, SystemDescription, parse_system

# Values of these keys are strings in the file grammar and must be quoted on
# serialization (a bare `bus = 1` would be read back as the float 1.0).
_STRING_KEYS = {
    "idx", "name", "bus", "bus_i", "bus_j", "type", "device", "param",
    "avr", "governor", "pss", "shaft",
    "filter", "angle", "voltage", "inner", "pll",
}

# idx prefix per device family, for generated unit names (SG1, GFM2, ...).
_IDX_PREFIXES = [
    ("GridForming", "GFM"),
    ("GridSupporting", "GFS"),
    ("GridFollowing", "GFL"),
    ("Synchronous", "SG"),
    ("GENROU", "SG"),
    ("GENSAL", "SG"),
    ("Marconato", "SG"),
    ("StaticInfiniteBus", "INF"),
    ("Static", "LOAD"),
    ("SVC", "SVC"),
]

# Builder defaults for a new line. Deliberately not the Line class defaults:
# those are near-zero placeholders, and b = 0 in particular is rejected by
# the dynamic-network model (the line charging is the bus capacitance, so
# every bus needs nonzero summed shunt susceptance under line_dyn).
LINE_DEFAULTS = {"r": "0.01", "x": "0.1", "g": "0.0", "b": "0.03", "trafo": "1"}

_UNDO_DEPTH = 50


def _fmt(key: str, value: str) -> str:
    value = str(value)
    return f'"{value}"' if key in _STRING_KEYS else value


class SystemDocument:
    """A mutable system with undo and file serialization."""

    def __init__(self, desc: SystemDescription):
        self.desc = desc
        self.dirty = False
        self._undo: "list[SystemDescription]" = []
        self._redo: "list[SystemDescription]" = []

    # ---- construction --------------------------------------------------------

    @classmethod
    def blank(cls, name: str = "untitled") -> "SystemDocument":
        return cls(SystemDescription(name=name, folder=Path(name)))

    @classmethod
    def load(cls, folder: "str | Path") -> "SystemDocument":
        return cls(parse_system(folder))

    # ---- undo ----------------------------------------------------------------

    def _checkpoint(self) -> None:
        self._undo.append(copy.deepcopy(self.desc))
        del self._undo[:-_UNDO_DEPTH]
        self._redo.clear()
        self.dirty = True

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self.desc)
            self.desc = self._undo.pop()
            self.dirty = True

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self.desc)
            self.desc = self._redo.pop()
            self.dirty = True

    # ---- naming --------------------------------------------------------------

    def next_bus_name(self) -> str:
        numeric = [int(b) for b in self.desc.buses() if b.isdigit()]
        return str(max(numeric, default=0) + 1)

    def next_idx(self, kind: str) -> str:
        prefix = next(
            (p for k, p in _IDX_PREFIXES if kind.startswith(k)), kind[:3].upper()
        )
        taken = {e.get("idx") for e in self.desc.devices}
        n = 1
        while f"{prefix}{n}" in taken:
            n += 1
        return f"{prefix}{n}"

    # ---- topology operations -------------------------------------------------

    def add_bus(self, name: "str | None" = None) -> str:
        """Create a bus (its BusInit entry). The first bus becomes the slack,
        further ones PQ; the type is edited in the bus dialog."""
        self._checkpoint()
        name = name or self.next_bus_name()
        has_slack = any(e.get("type") == "slack" for e in self.desc.bus_inits)
        self.desc.bus_inits.append(
            Entry(
                "BusInit",
                {
                    "bus": name,
                    "p": "0",
                    "q": "0",
                    "v": "1.0",
                    "type": "PQ" if has_slack else "slack",
                },
            )
        )
        return name

    def remove_bus(self, bus: str) -> None:
        """Remove a bus with everything attached to or referencing it."""
        self._checkpoint()
        d = self.desc
        d.bus_inits = [e for e in d.bus_inits if e.get("bus") != bus]
        d.devices = [e for e in d.devices if e.get("bus") != bus]
        d.lines = [e for e in d.lines if bus not in (e.get("bus_i"), e.get("bus_j"))]
        d.disturbances = [
            e
            for e in d.disturbances
            if bus not in (e.get("bus"), e.get("bus_i"), e.get("bus_j"))
        ]

    def add_line(self, bus_i: str, bus_j: str, params: "dict | None" = None) -> Entry:
        self._checkpoint()
        entry = Entry(
            "Line", {"bus_i": bus_i, "bus_j": bus_j, **LINE_DEFAULTS, **(params or {})}
        )
        self.desc.lines.append(entry)
        return entry

    def add_device(self, kind: str, bus: str, params: "dict | None" = None) -> Entry:
        entry_params = dict(params or {})
        entry_params.setdefault("idx", self.next_idx(kind))
        self._checkpoint()
        entry = Entry(kind, {"idx": entry_params.pop("idx"), "bus": bus, **entry_params})
        self.desc.devices.append(entry)
        return entry

    def clear(self) -> None:
        """Empty the canvas: every bus, line, device and disturbance (undoable)."""
        self._checkpoint()
        self.desc.devices = []
        self.desc.lines = []
        self.desc.bus_inits = []
        self.desc.disturbances = []

    def set_businit(self, bus: str, params: dict) -> Entry:
        """Update the BusInit of ``bus``, creating it when missing."""
        self._checkpoint()
        values = {"bus": bus, **{k: str(v) for k, v in params.items() if k != "bus"}}
        for entry in self.desc.bus_inits:
            if entry.get("bus") == bus:
                entry.params = values
                return entry
        entry = Entry("BusInit", values)
        self.desc.bus_inits.append(entry)
        return entry

    def add_disturbance(self, params: "dict | None" = None) -> Entry:
        self._checkpoint()
        entry = Entry("Disturbance", dict(params or {"time": "1.0", "type": "LOAD"}))
        self.desc.disturbances.append(entry)
        return entry

    def update_entry(self, entry: Entry, params: dict) -> None:
        """Replace an entry's parameters (undoable)."""
        # The undo snapshot deep-copies the description, so mutate the entry
        # that lives in the CURRENT description, found by identity.
        self._checkpoint()
        entry.params = {k: str(v) for k, v in params.items()}

    def remove_entry(self, entry: Entry) -> None:
        self._checkpoint()
        for group in (
            self.desc.devices,
            self.desc.lines,
            self.desc.bus_inits,
            self.desc.disturbances,
        ):
            if entry in group:
                group.remove(entry)
                return

    # ---- serialization -------------------------------------------------------

    def _header(self, filename: str) -> str:
        stamp = datetime.date.today().isoformat()
        return (
            f"# {filename} of system \"{self.desc.name}\"\n"
            f"# Written by the HERMESS GUI on {stamp}. Edit freely; the GUI\n"
            "# rewrites this file on save and does not preserve comments.\n\n"
        )

    @staticmethod
    def _emit(entry: Entry) -> str:
        parts = [entry.kind] + [
            f"{key} = {_fmt(key, value)}" for key, value in entry.params.items()
        ]
        return ", ".join(parts)

    def sim_param_text(self) -> str:
        blocks = []
        for group in (self.desc.devices, self.desc.lines, self.desc.bus_inits):
            if group:
                blocks.append("\n".join(self._emit(e) for e in group))
        return self._header("sim_param.txt") + "\n\n".join(blocks) + "\n"

    def sim_dist_text(self) -> str:
        def time_key(entry: Entry):
            try:
                return float(entry.get("time", "0") or "0")
            except ValueError:
                return 0.0

        body = "\n".join(
            self._emit(e) for e in sorted(self.desc.disturbances, key=time_key)
        )
        return self._header("sim_dist.txt") + body + ("\n" if body else "")

    def save(self, folder: "str | Path") -> Path:
        """Write the system files into ``folder`` (created if needed).

        The systems shipped with the package are read-only: a ``folder``
        inside ``hermess.SYSTEMS_DIR`` raises a ``PermissionError`` before
        anything is written.
        """
        folder = hermess._assert_not_shipped(folder, "save a system into")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "sim_param.txt").write_text(self.sim_param_text())
        (folder / "sim_dist.txt").write_text(self.sim_dist_text())
        self.desc.folder = folder
        self.desc.name = folder.name
        self.dirty = False
        return folder
