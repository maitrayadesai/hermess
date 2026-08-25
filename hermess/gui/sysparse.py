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

"""Read-only parser of the system text files, for display in the GUI.

Mirrors the tokenization of :func:`hermess.utils.data_loader.read` (comment
lines, continuation lines ending with ``,`` or ``;``, comma-separated
``key = value`` pairs after the class name) but keeps the values as the raw
strings from the file and instantiates nothing, so the inspector can show any
system file without touching the simulator's global state, and without
evaluating the arithmetic expressions the loader accepts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Entry:
    """One logical line of a system file."""

    kind: str  #: class name, e.g. ``"GridForming"``, ``"Line"``, ``"Disturbance"``
    params: "dict[str, str]" = field(default_factory=dict)  #: raw value strings

    def get(self, key: str, default: str = "") -> str:
        return self.params.get(key, default)


@dataclass
class SystemDescription:
    """Parsed view of one system folder (``sim_param.txt`` + ``sim_dist.txt``)."""

    name: str
    folder: Path
    devices: "list[Entry]" = field(default_factory=list)
    lines: "list[Entry]" = field(default_factory=list)
    bus_inits: "list[Entry]" = field(default_factory=list)
    disturbances: "list[Entry]" = field(default_factory=list)

    def buses(self) -> "list[str]":
        """Bus names, in first-seen order across lines, inits and devices."""
        seen: dict[str, None] = {}
        for e in self.lines:
            for key in ("bus_i", "bus_j"):
                if e.get(key):
                    seen.setdefault(e.get(key))
        for e in self.bus_inits + self.devices:
            if e.get("bus"):
                seen.setdefault(e.get("bus"))
        return list(seen)


def _logical_lines(text: str):
    """Yield logical lines: comments and blanks dropped, continuations joined."""
    lines = iter(text.splitlines())
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        while line.endswith((",", ";")):
            nxt = next(lines, None)
            if nxt is None:
                break
            nxt = nxt.strip()
            if not nxt:
                break
            if nxt.startswith("#"):
                continue
            line += " " + nxt
        yield line


def parse_entries(text: str) -> "list[Entry]":
    """Parse the text of one system file into :class:`Entry` objects."""
    entries = []
    for line in _logical_lines(text):
        parts = [p.strip() for p in line.split(",")]
        kind = parts.pop(0)
        params: dict[str, str] = {}
        for part in parts:
            key, sep, value = part.partition("=")
            if not sep:
                continue  # stray fragment; the loader warns, the viewer skips
            value = value.strip()
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1]
            params[key.strip()] = value
        entries.append(Entry(kind=kind, params=params))
    return entries


def parse_system(folder: "str | Path") -> SystemDescription:
    """Parse a system folder into a :class:`SystemDescription`.

    Missing files are tolerated (a system without disturbances is valid).
    """
    folder = Path(folder)
    desc = SystemDescription(name=folder.name, folder=folder)

    param_file = folder / "sim_param.txt"
    if param_file.exists():
        for entry in parse_entries(param_file.read_text()):
            if entry.kind == "Line":
                desc.lines.append(entry)
            elif entry.kind == "BusInit":
                desc.bus_inits.append(entry)
            elif entry.kind == "Disturbance":
                desc.disturbances.append(entry)
            else:
                desc.devices.append(entry)

    dist_file = folder / "sim_dist.txt"
    if dist_file.exists():
        for entry in parse_entries(dist_file.read_text()):
            if entry.kind == "Disturbance":
                desc.disturbances.append(entry)

    return desc
