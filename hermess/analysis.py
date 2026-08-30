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

"""Post-processing and notebook workflow: address, extract, tabulate and plot
the signals of a finished run.

Everything here is plain numpy / pandas / matplotlib glue around the
:class:`~hermess.system.DaeSim` object that :func:`hermess.simulate` returns.
The core idea is that **every quantity in a run has an address**,
``owner:quantity``::

    SG1:omega      a machine state           GFMI2:Pc_tilde   a converter state
    SG1:f          frequency [Hz]            GFMI2:f          frequency [Hz]
    SG1:P          power injection [MW]      bus3:v           voltage magnitude
    bus3:theta     voltage angle [deg]       line1-2:P        branch flow [MW]

:func:`signals` lists them all, and anything that takes a "what to plot"
argument accepts the same flexible selector::

    plot(dae, "SG1:omega")                  one signal
    plot(dae, "*:f")                        that quantity on every device
    plot(dae, "f")                          same, the "*:" is implied
    plot(dae, ["bus1:v", "bus3:v"])         a list
    plot(dae, "bus*:v")                     a glob
    plot(dae, {"SG1": ["omega", "delta"]})  a dict
    plot_states(dae, "GFMI2")               every state of one device
    compare({"droop": d1, "VSM": d2}, "GFMI2:f")   the same signal across runs

One import gives a notebook the whole workflow, including
:func:`hermess.simulate` and the system-file helpers::

    from hermess.analysis import *

    root = copy_system("3bus_loadstep")      # editable local copy of the system
    dae = simulate("3bus_loadstep", system_root=root, T_end=5.0, quiet=True)
    plot(dae, ["*:f", "bus*:v"])

The plots use the active matplotlib style; pass ``color=`` (or ``colors=`` on
:func:`compare` and :func:`plot_system`) to override.
"""

from __future__ import annotations

import difflib
import fnmatch
import re
import shutil
from collections import namedtuple
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import casadi as ca
import matplotlib.pyplot as plt
import numpy as np

import hermess
from hermess import list_systems, register, registered, simulate, unregister
from hermess.results import _DERIVED_OUTPUTS, _derived_outputs

__all__ = [
    # systems
    "list_systems",
    "copy_system",
    "show_system",
    "set_param",
    "set_disturbances",
    "read_events",
    # running
    "simulate",
    "summary",
    # signals
    "signals",
    "signal_names",
    "get",
    "to_dataframe",
    "to_csv",
    "metrics",
    # plotting
    "plot",
    "plot_system",
    "plot_states",
    "compare",
    "plot_frequency",
    "plot_voltages",
    "plot_active_power",
    "plot_modes",
    "mark_events",
    # devices / raw access
    "get_device",
    "device_label",
    "frequency_hz",
    "bus_voltage",
    "state_index",
    # analysis
    "small_signal",
    "modal_table",
    "participation_table",
    "state_matrix",
    "power_flow_table",
    # user-defined models (re-exported from hermess)
    "register",
    "registered",
    "unregister",
]

#: The systems shipped inside the installed package (copy them out with
#: :func:`copy_system` before editing).
PACKAGE_SYSTEMS = Path(hermess.__file__).parent / "systems"

#: Neutral gray for annotations (event markers, secondary text).
_GRAY = "0.5"


# ---------------------------------------------------------------------------
# System files: copy, show, edit
# ---------------------------------------------------------------------------


def copy_system(name: str, dest: str | Path = "systems", overwrite: bool = False) -> Path:
    """Copy ``hermess/systems/<name>`` into ``<dest>/<name>`` and return ``dest``.

    Edit the copy, never the installed package. Pass the returned path as
    ``system_root`` to :func:`hermess.simulate`. Re-running without
    ``overwrite`` keeps your edits.
    """
    dest = Path(dest)
    target = dest / name
    if overwrite and target.exists():
        shutil.rmtree(target)
    if not target.exists():
        shutil.copytree(PACKAGE_SYSTEMS / name, target)
    return dest.resolve()


def show_system(root: str | Path, name: str, which: Sequence[str] = ("sim_param.txt", "sim_dist.txt"),
                strip_license: bool = True) -> None:
    """Print the system files (without the license header) for reading."""
    for fname in which:
        text = (Path(root) / name / fname).read_text()
        if strip_license:
            lines = [ln for ln in text.splitlines() if not _is_license_line(ln)]
            text = "\n".join(lines).strip("\n")
        bar = "=" * 22
        print(f"{bar}  {name}/{fname}  {bar}\n{text}\n")


_LICENSE_WORDS = ("©", "Copyright", "Licensed under", "you may not use", "You may obtain",
                  "gnu.org/licenses", "distributed \"AS IS\"", "express or implied",
                  "permissions and limitations", "Simulation-only fork", "doi.org/10.5905",
                  "For inquiries", "Original author", "maintainer: Maitraya", "Created:", "Last Modified:")


def _is_license_line(line: str) -> bool:
    s = line.strip()
    if not s.startswith("#"):
        return False
    return any(w in s for w in _LICENSE_WORDS) or s == "#"


def _records(text: str) -> list[list[int]]:
    """Group physical line indices into logical records (continuation lines end with ',' or ';')."""
    lines = text.splitlines()
    recs, i = [], 0
    while i < len(lines):
        rec = [i]
        while lines[i].rstrip().endswith((",", ";")) and i + 1 < len(lines):
            i += 1
            rec.append(i)
        recs.append(rec)
        i += 1
    return recs


def set_param(root: str | Path, name: str, idx: str, **values) -> None:
    """Change parameters of one device record in ``<root>/<name>/sim_param.txt``.

    A text-level edit of the system file, keeping everything else in the
    record untouched. Example: ``set_param(root, "3bus_loadstep", "GFMI2",
    Kp=0.05)`` or ``set_param(root, "3bus_loadstep", "GFMI2", angle='"VSM"',
    H_v=2.0)``. A parameter that does not exist yet is appended to the
    record. Numbers are written with ``repr``; pass strings with their quotes
    (``angle='"VSM"'``).
    """
    path = Path(root) / name / "sim_param.txt"
    lines = path.read_text().splitlines()
    hit = False
    for rec in _records("\n".join(lines)):
        block = "\n".join(lines[i] for i in rec)
        if re.search(rf'\bidx\s*=\s*"{re.escape(idx)}"', block) is None:
            continue
        hit = True
        for key, val in values.items():
            sval = val if isinstance(val, str) else repr(float(val))
            pat = re.compile(rf"(\b{re.escape(key)}\s*=\s*)([^,\n]+)")
            if pat.search(block):
                block = pat.sub(lambda m: m.group(1) + sval, block, count=1)
            else:
                block = block.rstrip().rstrip(",") + f", {key} = {sval}"
        new_lines = block.split("\n")
        lines[rec[0] : rec[-1] + 1] = new_lines
        break
    if not hit:
        raise KeyError(f'no device with idx = "{idx}" in {path}')
    path.write_text("\n".join(lines) + "\n")


def set_disturbances(root: str | Path, name: str, rows: Iterable[str] | str) -> None:
    """Overwrite ``sim_dist.txt`` of a local system copy with the given
    ``Disturbance`` rows.

    ``rows`` is a list of strings (or one multi-line string), e.g.::

        set_disturbances(root, "3bus_loadstep", [
            'Disturbance, time = 1.0, type = "FAULT_BUS", bus = "2", y = 20',
            'Disturbance, time = 1.1, type = "CLEAR_FAULT_BUS", bus = "2"',
        ])
    """
    if isinstance(rows, str):
        rows = [r for r in rows.splitlines() if r.strip()]
    path = Path(root) / name / "sim_dist.txt"
    header = "# Disturbances for this local copy of the system (edit freely).\n"
    path.write_text(header + "\n".join(r.strip() for r in rows) + "\n")


_DIST_RE = re.compile(r"^\s*Disturbance\s*,(.*)$")


def read_events(root: str | Path, name: str) -> list[tuple[float, str, str]]:
    """Parse ``sim_dist.txt`` into ``(time, type, where)`` tuples, in time order.

    A finished run already carries the same list as ``dae.events``; this reads
    it from the files, e.g. before simulating.
    """
    path = Path(root) / name / "sim_dist.txt"
    events = []
    for line in path.read_text().splitlines():
        m = _DIST_RE.match(line)
        if not m or line.strip().startswith("#"):
            continue
        fields = {}
        for part in m.group(1).split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k.strip()] = v.strip().strip('"')
        typ = fields.get("type", "?")
        if "LINE" in typ:
            where = f"{fields.get('bus_i')}-{fields.get('bus_j')}"
        elif typ == "SETPOINT":
            where = f"{fields.get('device')}:{fields.get('param')} = {fields.get('value')}"
        else:
            where = fields.get("bus")
        events.append((float(fields.get("time", "nan")), typ, str(where)))
    return sorted(events)


def summary(dae) -> str:
    """One-paragraph description of what was simulated: size, devices, disturbances."""
    devs = []
    for dev in dae.device_list:
        for u in range(dev.n):
            devs.append(f"{_owner_of(dev, u)} ({dev.__class__.__name__} at bus {dev.bus[u]})")
    ev = ", ".join(f"{t:g} s {typ.replace('_', ' ').lower()} at {w}" for t, typ, w in getattr(dae, "events", [])) or "none"
    txt = (
        f"System '{getattr(getattr(dae, 'cfg', None), 'testsystemfile', None)}': "
        f"{dae.grid.nn} buses, {dae.grid.nb} branches, {len(devs)} devices.\n"
        f"  devices     : {', '.join(devs)}\n"
        f"  model size  : nx = {dae.nx} device states, ny = {dae.ny} algebraic "
        f"({dae.nv} bus voltages + {dae.n_priv} private), nl = {dae.nl} line-current states\n"
        f"  network     : {'dynamic lines (EMT-like)' if dae.line_dyn else 'quasi-static (RMS)'}, "
        f"{dae.fn} Hz, {dae.Sb} MVA base, reference frame '{dae.omega_mode}'\n"
        f"  time        : {dae.T_start} to {dae.T_end} s, output step {dae.t} s\n"
        f"  disturbances: {ev}"
    )
    print(txt)
    return txt


# ---------------------------------------------------------------------------
# Signals: one address for every quantity in a run
# ---------------------------------------------------------------------------

Entry = namedtuple("Entry", "name owner quantity unit kind description get")

_DERIVED_DESCR = {
    "f": "frequency",
    "P": "active power injected into the network",
    "Q": "reactive power injected into the network",
    "v": "voltage magnitude",
    "theta": "voltage angle",
    "vre": "voltage, real part",
    "vim": "voltage, imaginary part",
    "i": "current magnitude (sending end)",
}

_MACHINE_CLASSES = ("GENROU", "GENSAL", "Marconato")


def _is_machine(dev) -> bool:
    cls = dev.__class__.__name__
    return "Synchronous" in cls or cls in _MACHINE_CLASSES


def _is_source(dev) -> bool:
    if _is_machine(dev):
        return True
    from hermess.devices.inverter import Inverter

    return isinstance(dev, Inverter)


def _owner_of(dev, unit: int) -> str:
    """The name a user addresses a device unit by: its ``idx``, else Class@bus."""
    inv = {u: k for k, u in getattr(dev, "int", {}).items()}
    name = inv.get(unit)
    if name is None:
        name = f"{dev.__class__.__name__}@{dev.bus[unit]}"
    return str(name)


def _catalog(dae) -> dict[str, Entry]:
    """Build (and cache on the run) the address book of every available signal."""
    cached = getattr(dae, "_signal_catalog", None)
    if cached is not None:
        return cached

    cat: dict[str, Entry] = {}

    def add(owner, quantity, unit, kind, descr, getter):
        name = f"{owner}:{quantity}"
        cat[name] = Entry(name, owner, quantity, unit, kind, descr, getter)

    Sb = float(dae.Sb)

    # --- devices: states, private algebraics, and derived f / P / Q ----------
    for dev in dae.device_list:
        if not getattr(dev, "xf", None) and not getattr(dev, "yf_int", None):
            continue  # e.g. static loads, which store no trajectories
        units = {s: u for s, u in zip(dev.states, getattr(dev, "units", []))}
        for u in range(dev.n):
            owner = _owner_of(dev, u)
            for s in dev.states:
                if s not in dev.xf:
                    continue
                add(owner, s, units.get(s, ""), "state", dev._descr.get(s, ""),
                    lambda d=dev, s=s, u=u: np.asarray(d.xf[s][u]))
            for s in getattr(dev, "yf_int", {}):
                add(owner, s, dev._algebs_int_units.get(s, ""), "algebraic", dev._descr.get(s, ""),
                    lambda d=dev, s=s, u=u: np.asarray(d.yf_int[s][u]))
            if _is_source(dev):
                add(owner, "f", "Hz", "derived", _DERIVED_DESCR["f"],
                    lambda d=dev, u=u: frequency_hz(dae, d, u))
                # The device's own electrical power, evaluated from the expression
                # the model published (machines: air-gap power; converters:
                # terminal power), converted from device p.u. to MW / MVAr.
                Sn = float(dev.Sn[u])
                if getattr(dev, "Pe", None) is not None:
                    add(owner, "P", "MW", "derived", "air-gap electrical power",
                        lambda d=dev, u=u, Sn=Sn: _eval_over_trajectory(dae, d.Pe)[u] * Sn)
                if getattr(dev, "Pc", None) is not None:
                    add(owner, "P", "MW", "derived", "terminal active power",
                        lambda d=dev, u=u, Sn=Sn: _eval_over_trajectory(dae, d.Pc)[u] * Sn)
                if getattr(dev, "Qc", None) is not None:
                    add(owner, "Q", "MVAr", "derived", "terminal reactive power",
                        lambda d=dev, u=u, Sn=Sn: _eval_over_trajectory(dae, d.Qc)[u] * Sn)

    # --- buses --------------------------------------------------------------
    for b in dae.grid.buses:
        b = str(b)
        owner = f"bus{b}"
        add(owner, "v", "p.u.", "bus", _DERIVED_DESCR["v"],
            lambda b=b: np.hypot(dae.grid.yf[b][0], dae.grid.yf[b][1]))
        add(owner, "theta", "deg", "bus", _DERIVED_DESCR["theta"],
            lambda b=b: np.degrees(np.arctan2(dae.grid.yf[b][1], dae.grid.yf[b][0])))
        add(owner, "vre", "p.u.", "bus", _DERIVED_DESCR["vre"], lambda b=b: np.asarray(dae.grid.yf[b][0]))
        add(owner, "vim", "p.u.", "bus", _DERIVED_DESCR["vim"], lambda b=b: np.asarray(dae.grid.yf[b][1]))
        add(owner, "P", "MW", "bus", _DERIVED_DESCR["P"], lambda b=b: np.asarray(dae.grid.sf[b][0]) * Sb)
        add(owner, "Q", "MVAr", "bus", _DERIVED_DESCR["Q"], lambda b=b: np.asarray(dae.grid.sf[b][1]) * Sb)

    # --- branches -----------------------------------------------------------
    line = getattr(dae.grid, "line", None)
    i_full = getattr(dae, "i_full", None)
    if line is not None and i_full is not None:
        for k, (bi, bj) in enumerate(zip(line.bus_i, line.bus_j)):
            owner = f"line{bi}-{bj}"
            add(owner, "i", "p.u.", "branch", _DERIVED_DESCR["i"],
                lambda k=k: np.hypot(i_full[4 * k + 0], i_full[4 * k + 1]))
            add(owner, "i_re", "p.u.", "branch", "sending-end current, real part",
                lambda k=k: np.asarray(i_full[4 * k + 0]))
            add(owner, "i_im", "p.u.", "branch", "sending-end current, imaginary part",
                lambda k=k: np.asarray(i_full[4 * k + 1]))
            add(owner, "P", "MW", "branch", "active power flow, sending end",
                lambda k=k, b=str(bi): (dae.grid.yf[b][0] * i_full[4 * k + 0]
                                        + dae.grid.yf[b][1] * i_full[4 * k + 1]) * Sb)
            add(owner, "Q", "MVAr", "branch", "reactive power flow, sending end",
                lambda k=k, b=str(bi): (dae.grid.yf[b][1] * i_full[4 * k + 0]
                                        - dae.grid.yf[b][0] * i_full[4 * k + 1]) * Sb)

    dae._signal_catalog = cat
    return cat


def signals(dae, what: object = None, kind: str | None = None):
    """The address book of the run as a table: every signal, its unit and meaning.

    ``signals(dae)`` lists everything; ``signals(dae, "SG1")`` or
    ``signals(dae, "*:f")`` filters with the same selector the plots take;
    ``kind`` filters by ``'state'``, ``'algebraic'``, ``'derived'``, ``'bus'`` or
    ``'branch'``.
    """
    import pandas as pd

    cat = _catalog(dae)
    names = list(cat) if what is None else signal_names(dae, what)
    rows = [{"signal": n, "owner": cat[n].owner, "quantity": cat[n].quantity,
             "unit": cat[n].unit, "kind": cat[n].kind, "description": cat[n].description}
            for n in names if kind is None or cat[n].kind == kind]
    df = pd.DataFrame(rows)
    pd.set_option("display.max_colwidth", None)
    return df


def signal_names(dae, what: object) -> list[str]:
    """Resolve a selector into canonical signal names, in catalog order, deduplicated.

    Accepts a string (``"SG1:omega"``, ``"f"``, ``"bus*:v"``, ``"SG1"``), a list of
    them, a ``{owner: quantity-or-list}`` dict, a device object, or a ``(device,
    state)`` tuple. Matching is case-insensitive and understands ``*`` and ``?``.
    """
    cat = _catalog(dae)
    out: list[str] = []

    def emit(names):
        for n in names:
            if n not in out:
                out.append(n)

    def match(owner_pat: str, qty_pat: str) -> list[str]:
        qp = qty_pat.lower()
        # A bus or branch may be addressed with or without its prefix: "3:v" == "bus3:v".
        for op in (owner_pat.lower(), f"bus{owner_pat}".lower(), f"line{owner_pat}".lower()):
            hits = [n for n, e in cat.items()
                    if fnmatch.fnmatchcase(e.owner.lower(), op) and fnmatch.fnmatchcase(e.quantity.lower(), qp)]
            if hits:
                return hits
        return []

    def one(token) -> None:
        # devices and (device, state) tuples
        if hasattr(token, "states") and hasattr(token, "n"):
            emit([n for u in range(token.n) for n in match(_owner_of(token, u).lower(), "*")])
            return
        if isinstance(token, tuple) and len(token) == 2 and hasattr(token[0], "states"):
            dev, qty = token
            emit([n for u in range(dev.n) for n in match(_owner_of(dev, u).lower(), str(qty).lower())])
            return
        s = str(token).strip()
        if ":" in s:
            owner_pat, qty_pat = s.split(":", 1)
            hits = match(owner_pat or "*", qty_pat or "*")
        else:
            # no colon: an owner (-> all its quantities) or a quantity (-> all owners)
            hits = match(s, "*") or match("*", s)
        if not hits:
            close = difflib.get_close_matches(s, list(cat), n=6, cutoff=0.4)
            raise KeyError(f"no signal matches {s!r}. Did you mean: {', '.join(close) or 'run signals(dae) to list them'}?")
        emit(hits)

    if what is None:
        return list(cat)
    if isinstance(what, Mapping):
        for owner, qty in what.items():
            quantities = [qty] if isinstance(qty, str) or not isinstance(qty, Iterable) else list(qty)
            for q in quantities:
                one(f"{owner}:{q}")
        return out
    if isinstance(what, (str, tuple)) or not isinstance(what, Iterable):
        one(what)
        return out
    for token in what:
        one(token)
    return out


def get(dae, what: object) -> dict[str, np.ndarray]:
    """Resolve a selector and return ``{signal name: values}`` (each of length nts)."""
    cat = _catalog(dae)
    return {n: cat[n].get() for n in signal_names(dae, what)}


def to_dataframe(dae, what: object = "*:*", every: int = 1):
    """Selected signals as a pandas DataFrame indexed by time [s] (``every``: keep
    every n-th sample, for exporting a manageable file)."""
    import pandas as pd

    data = {n: v[::every] for n, v in get(dae, what).items()}
    return pd.DataFrame(data, index=pd.Index(dae.time_steps[::every], name="t"))


def to_csv(dae, path: str | Path, what: object, every: int = 1, float_format: str = "%.6g") -> Path:
    """Write selected signals to CSV as ``t`` plus one named column per signal."""
    df = to_dataframe(dae, what, every=every)
    path = Path(path)
    df.to_csv(path, float_format=float_format)
    return path


def metrics(dae, what: object = "*:f", settle_from: float | None = None):
    """Excursion metrics per signal: pre-event value, nadir/peak and when, final value
    and the largest rate of change. Defaults to every device frequency."""
    import pandas as pd

    t = dae.time_steps
    t0 = min((e[0] for e in getattr(dae, "events", [])), default=t[0])
    pre = np.searchsorted(t, t0) - 1
    pre = max(pre, 0)
    tail = np.searchsorted(t, settle_from) if settle_from is not None else int(0.9 * len(t))
    rows = []
    cat = _catalog(dae)
    for name, v in get(dae, what).items():
        v = np.asarray(v, dtype=float)
        rate = np.abs(np.diff(v)) / np.diff(t)
        i_min, i_max = int(np.argmin(v)), int(np.argmax(v))
        far = i_min if abs(v[i_min] - v[pre]) >= abs(v[i_max] - v[pre]) else i_max
        rows.append({
            "signal": name, "unit": cat[name].unit,
            "pre-event": v[pre], "extreme": v[far], "t_extreme [s]": t[far],
            "deviation": v[far] - v[pre], "final": v[tail:].mean(),
            "max |rate| [/s]": rate.max() if rate.size else np.nan,
        })
    return pd.DataFrame(rows).set_index("signal")


# ---------------------------------------------------------------------------
# Raw access to devices and results
# ---------------------------------------------------------------------------


def get_device(dae, key: str):
    """Find a device by its ``idx`` (e.g. ``"SG1"``) or by class name (e.g. ``"GridForming"``)."""
    for dev in dae.device_list:
        if dev.__class__.__name__ == key:
            return dev
        if hasattr(dev, "int") and key in dev.int:
            return dev
    raise KeyError(f"no device matching {key!r}; have "
                   f"{[list(getattr(d, 'int', {}).keys()) or d.__class__.__name__ for d in dae.device_list]}")


def device_label(dev, unit: int = 0) -> str:
    cls = dev.__class__.__name__
    short = {"GridForming": "GFM", "GridSupporting": "GS", "GridFollowing": "GFL"}.get(
        cls, "SG" if _is_machine(dev) else cls)
    return f"{_owner_of(dev, unit)} ({short}, bus {dev.bus[unit]})"


def state_index(dev, state: str, unit: int = 0) -> int:
    """Global index of a device state in the stacked state vector ``dae.x``."""
    return int(getattr(dev, state)[unit])


def _eval_over_trajectory(dae, expr) -> np.ndarray:
    """Evaluate a CasADi expression of (x, y) along the stored trajectory -> (n, nts)."""
    pairs = [("omega_ref", "omega_ref_expr"), ("omega_ref_buses", "omega_ref_buses_expr"),
             ("omega_ref_lines", "omega_ref_lines_expr")]
    syms = [getattr(dae, a) for a, b in pairs if getattr(dae, a, None) is not None and getattr(dae, b, None) is not None]
    exprs = [getattr(dae, b) for a, b in pairs if getattr(dae, a, None) is not None and getattr(dae, b, None) is not None]
    e = ca.substitute(expr, ca.vertcat(*syms), ca.vertcat(*exprs)) if syms else expr
    sw = [("s", "sinit"), ("sl", "slinit")]
    ssyms = [getattr(dae, a) for a, b in sw if getattr(dae, a, None) is not None and getattr(dae, b, None) is not None]
    svals = [ca.DM(getattr(dae, b)) for a, b in sw if getattr(dae, a, None) is not None and getattr(dae, b, None) is not None]
    if ssyms:
        e = ca.substitute(e, ca.vertcat(*ssyms), ca.vertcat(*svals))
    f = ca.Function("f", [dae.x, dae.y], [e])
    nts = dae.x_full.shape[1]
    out = f.map(nts)(dae.x_full, dae.y_full)
    return np.asarray(out).reshape(e.size1(), nts)


def frequency_hz(dae, dev, unit: int = 0) -> np.ndarray:
    """Frequency of one device unit in Hz along the trajectory.

    Synchronous machines: the rotor speed state ``omega`` (absolute p.u.).
    Converters: the converter frequency (``omega_c``) or the PLL frequency
    (``omega_pll``) the model itself published, evaluated over the stored run
    with the segment-aware snapshot machinery of
    :func:`hermess.results.extract_results`, so it stays correct across a
    ``SETPOINT`` disturbance and for user-defined strategies.
    """
    cls = dev.__class__.__name__
    if _is_machine(dev) and "omega" in getattr(dev, "states", []):
        return np.asarray(dev.xf["omega"][unit]) * dae.fn
    derived = _derived_outputs(dae, dev)
    for name in _DERIVED_OUTPUTS:
        if name in derived:
            return np.asarray(derived[name][unit]) * dae.fn
    raise ValueError(f"do not know how to read a frequency from {cls}")


def bus_voltage(dae, bus: str) -> np.ndarray:
    """Voltage magnitude [p.u.] at a bus along the trajectory."""
    v = dae.grid.yf[str(bus)]
    return np.hypot(v[0], v[1])


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def mark_events(ax, dae, label: bool = True, color: str = _GRAY) -> None:
    """Dashed vertical lines at the disturbance times stored on ``dae.events``."""
    seen = set()
    k = 0
    for t, typ, where in getattr(dae, "events", []):
        ax.axvline(t, color=color, ls="--", lw=0.9, alpha=0.8)
        if label and t not in seen:
            ax.annotate(typ.replace("_", " ").lower(), (t, 1.0 - 0.07 * (k % 4)),
                        xycoords=("data", "axes fraction"), xytext=(3, -2),
                        textcoords="offset points", fontsize=8, color=color, va="top")
            seen.add(t)
            k += 1


def _ylabel(entries) -> str:
    units = {e.unit for e in entries}
    kinds = {e.quantity for e in entries}
    qty = list(kinds)[0] if len(kinds) == 1 else ""
    unit = list(units)[0] if len(units) == 1 else ""
    return f"{qty} [{unit}]" if qty and unit else (f"[{unit}]" if unit else qty)


def plot(dae, what: object, ax=None, events: bool = True, label_prefix: str = "",
         figsize=None, title: str | None = None, **kw):
    """Plot any selection of signals against time.

    Signals are grouped by unit: everything sharing a unit lands on one axes, and
    a mixed selection produces one panel per unit. Pass ``ax`` to force a single
    axes (e.g. to overlay two runs yourself). Style keywords (``color=``,
    ``lw=``, ...) pass through to matplotlib::

        plot(dae, "SG1:omega")
        plot(dae, "f")                       # every device frequency
        plot(dae, ["*:f", "bus*:v"])         # two panels, Hz and p.u.
        plot(dae, {"GFMI2": ["Pc_tilde", "delta_c"]})
    """
    cat = _catalog(dae)
    names = signal_names(dae, what)
    if not names:
        raise KeyError(f"selector {what!r} matched no signals")
    t = dae.time_steps

    if ax is not None:
        groups = [names]
        axes = [ax]
        fig = ax.figure
    else:
        by_unit: dict[str, list[str]] = {}
        for n in names:
            by_unit.setdefault(cat[n].unit, []).append(n)
        groups = list(by_unit.values())
        fig, axs = plt.subplots(len(groups), 1, sharex=True,
                                figsize=figsize or (9, 3.2 * len(groups)), squeeze=False)
        axes = list(axs[:, 0])

    for a, group in zip(axes, groups):
        for n in group:
            a.plot(t, cat[n].get(), label=f"{label_prefix}{n}", **kw)
        if events:
            mark_events(a, dae)
        a.set_ylabel(_ylabel([cat[n] for n in group]))
        a.ticklabel_format(axis="y", useOffset=False)
        if len(group) > 12:
            # too many curves to name: say how many, and let the user select fewer
            a.annotate(f"{len(group)} signals ({cat[group[0]].quantity})", (0.01, 0.03),
                       xycoords="axes fraction", fontsize=8, color=_GRAY)
        elif len(group) > 1 or label_prefix:
            a.legend(ncol=2 if len(group) > 6 else 1, fontsize=8 if len(group) > 4 else None)
        elif group and title is None and ax is None:
            a.set_title(group[0])
    axes[-1].set_xlabel("time [s]")
    if title:
        (fig.suptitle if len(axes) > 1 else axes[0].set_title)(title)
    if ax is None:
        fig.tight_layout()
    return axes[0] if len(axes) == 1 else axes


def plot_states(dae, who: object = "*", states: object = "*", ncols: int = 4,
                figsize=None, events: bool = True, **kw):
    """One small panel per state, the way you look at a device you are debugging.

        plot_states(dae, "SG1")                       every state of SG1
        plot_states(dae, "SG1", ["omega", "delta"])   two of them
        plot_states(dae, "*", "omega")                that state on every device
        plot_states(dae, "GFM*")                      every state of every GFM
    """
    cat = _catalog(dae)
    names = [n for n in signal_names(dae, who) if fnmatch.fnmatchcase(cat[n].quantity.lower(), str(states).lower())] \
        if isinstance(states, str) else \
        [n for n in signal_names(dae, who) if cat[n].quantity in set(states)]
    names = [n for n in names if cat[n].kind in ("state", "algebraic", "derived")]
    if not names:
        raise KeyError(f"no states match who={who!r}, states={states!r}")
    t = dae.time_steps
    nrows = int(np.ceil(len(names) / ncols))
    ncols = min(ncols, len(names))
    fig, axs = plt.subplots(nrows, ncols, sharex=True, squeeze=False,
                            figsize=figsize or (3.2 * ncols, 2.2 * nrows))
    for a, n in zip(axs.ravel(), names):
        a.plot(t, cat[n].get(), **kw)
        if events:
            mark_events(a, dae, label=False)
        a.set_title(n, fontsize=9)
        a.set_ylabel(cat[n].unit, fontsize=8)
        a.tick_params(labelsize=8)
        a.ticklabel_format(axis="y", useOffset=False)
    for a in axs.ravel()[len(names):]:
        a.set_visible(False)
    for a in axs[-1, :]:
        a.set_xlabel("time [s]", fontsize=9)
    fig.tight_layout()
    return axs


def compare(runs: Mapping[str, object], what: object, ncols: int = 2, figsize=None,
            events: bool = True, colors: Sequence[str] | None = None, **kw):
    """The same signals across several runs: one panel per signal, one line per run.

    ``colors`` gives one color per run; the default is the active matplotlib
    color cycle.

        compare({"droop": dae1, "VSM": dae2}, ["GFMI2:f", "GFMI2:P"])
    """
    import matplotlib as mpl

    if colors is None:
        colors = mpl.rcParams["axes.prop_cycle"].by_key().get("color", ["C0"])
    first = next(iter(runs.values()))
    names = signal_names(first, what)
    n = len(names)
    ncols = min(ncols, n)
    nrows = int(np.ceil(n / ncols))
    fig, axs = plt.subplots(nrows, ncols, sharex=True, squeeze=False,
                            figsize=figsize or (6.0 * ncols, 3.4 * nrows))
    for a, name in zip(axs.ravel(), names):
        for (lbl, dae), color in zip(runs.items(), list(colors) * (len(runs) // max(len(colors), 1) + 1)):
            try:
                series = get(dae, name)[name]
            except KeyError:
                continue                      # a signal that does not exist in this run
            a.plot(dae.time_steps, series, label=lbl, color=color, **kw)
        cat = _catalog(first)
        a.set_title(name, fontsize=10)
        a.set_ylabel(cat[name].unit)
        a.ticklabel_format(axis="y", useOffset=False)
        if events:
            mark_events(a, first, label=False)
        a.legend(fontsize=8)
    for a in axs.ravel()[n:]:
        a.set_visible(False)
    for a in axs[-1, :]:
        a.set_xlabel("time [s]")
    fig.tight_layout()
    return axs


def plot_frequency(dae, who: object = None, ax=None, title="Frequency", **kw):
    """Frequency [Hz] of every machine and converter, or of a selection
    (``who="SG*"``, ``who=["SG1", "GFMI2"]``)."""
    names = "*:f" if who is None else [f"{w}:f" if ":" not in str(w) else str(w) for w in np.atleast_1d(who)]
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4))
    plot(dae, names, ax=ax, **kw)
    ax.set_title(title)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("frequency [Hz]")
    ax.legend()
    return ax


def plot_voltages(dae, buses: object = None, ax=None, title="Bus voltages", **kw):
    """Voltage magnitude [p.u.] at all buses, or at a selection
    (``buses=["1", "3"]``, ``buses="bus3*"``)."""
    names = "bus*:v" if buses is None else [f"bus{b}:v" if not str(b).startswith("bus") else f"{b}:v"
                                            for b in np.atleast_1d(buses)]
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4))
    plot(dae, names, ax=ax, **kw)
    ax.set_title(title)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("|V| [p.u.]")
    return ax


def plot_active_power(dae, who: object = None, ax=None, title="Active power", **kw):
    """Active power [MW] injected by every machine and converter, or by a selection."""
    names = "*:P" if who is None else [f"{w}:P" if ":" not in str(w) else str(w) for w in np.atleast_1d(who)]
    cat = _catalog(dae)
    names = [n for n in signal_names(dae, names) if cat[n].kind == "derived"] if who is None else names
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4))
    plot(dae, names, ax=ax, **kw)
    ax.set_title(title)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("P [MW]")
    ax.legend()
    return ax


# ---------------------------------------------------------------------------
# The single-line diagram
# ---------------------------------------------------------------------------


def _device_kind(dev) -> str:
    """One of 'machine', 'gfm', 'gsp', 'gfl', 'svc', 'infinite', 'conv', 'load'."""
    cls = dev.__class__.__name__
    if _is_machine(dev):
        return "machine"
    if cls == "GridForming":
        return "gfm"
    if cls == "GridSupporting":
        return "gsp"
    if cls == "GridFollowing":
        return "gfl"
    if cls == "SVC":
        return "svc"
    if "Infinite" in cls:
        return "infinite"
    from hermess.devices.inverter import Inverter

    if isinstance(dev, Inverter):
        return "conv"  # a user-registered converter model
    return "load"


def _device_type_label(dev) -> str:
    """The model type shown next to a device: which machine/converter/load model it
    is, plus the strategies that define its behavior."""
    kind, cls = _device_kind(dev), dev.__class__.__name__
    if kind == "machine":
        base = {"SynchronousTransient": "transient",
                "SynchronousSubtransient": "subtransient",
                "SynchronousSubtransientSP": "subtransient (Sauer-Pai)",
                "SynchronousSubtransientSP_DAE": "subtransient (Sauer-Pai, DAE)",
                "SynchronousSubtransientSP6": "6th order (Sauer-Pai)",
                "SynchronousSubtransientSP6DAE": "6th order (Sauer-Pai, DAE)",
                "SynchronousFluxDecay": "flux decay"}.get(cls, cls)
        extras = [type(getattr(dev, a, None)).__name__ for a in ("_avr", "_governor", "_pss", "_shaft")]
        extras = [e for e in extras if e not in ("NoneType", "SingleMass")]
        return " · ".join([base] + extras)
    if kind in ("gfm", "gsp", "gfl", "conv"):
        parts = []
        for attr in ("_angle", "_inner", "_filter", "_pll"):
            obj = getattr(dev, attr, None)
            if obj is not None:
                parts.append(type(obj).__name__.replace("Angle", "").replace("Control", ""))
        return " · ".join(parts)
    if kind == "load":
        if cls == "StaticZIP":
            shares = [(s, float(getattr(dev, f"{s.lower()}_share", [0])[0])) for s in ("Z", "I", "P")]
            on = [f"{s}" for s, v in shares if v > 0.999]
            if len(on) == 1:
                return f"constant {on[0]}"
            return "ZIP " + "/".join(f"{v:.0%}".rstrip("%") for _, v in shares)
        return {"StaticLoadPower": "constant P", "StaticLoadImpedance": "constant Z"}.get(cls, cls)
    return cls


def _device_display_name(dev, unit: int) -> str:
    """The device's ``idx``, or '' when the loader auto-generated one (loads and
    other rows written without ``idx = "..."``)."""
    name = _owner_of(dev, unit)
    auto = name.startswith(getattr(dev, "_name", "\0")) or name.startswith(dev.__class__.__name__)
    return "" if auto else name


def _device_size_label(dae, dev, unit: int) -> str:
    """What the device is worth: the rating for a source, the scheduled demand for
    a load (its ``Sn`` is only the per-unit base)."""
    if _device_kind(dev) == "load":
        bi = getattr(dae, "bus_init", None)
        if bi is not None:
            for k, b in enumerate(np.atleast_1d(bi.bus)):
                if str(b) == str(dev.bus[unit]):
                    return f"{float(np.atleast_1d(bi.p)[k]):g} MW"
        return ""
    if hasattr(dev, "Sn") and len(np.atleast_1d(dev.Sn)) > unit:
        return f"{float(dev.Sn[unit]):g} MVA"
    return ""


#: How each device category is drawn: color and legend label. Override the
#: colors per call with ``plot_system(..., colors={"machine": "k", ...})``.
_KIND_STYLE = {
    "machine":  dict(color="tab:blue",   label="synchronous machine"),
    "gfm":      dict(color="tab:cyan",   label="grid-forming converter"),
    "gsp":      dict(color="tab:olive",  label="grid-supporting converter"),
    "gfl":      dict(color="tab:green",  label="grid-following converter"),
    "conv":     dict(color="tab:orange", label="converter"),
    "svc":      dict(color="tab:purple", label="SVC"),
    "infinite": dict(color="tab:gray",   label="infinite bus"),
    "load":     dict(color="tab:red",    label="load"),
}


def _sym(ax, kind, xy, r, color, lw=1.4):
    """Draw one device symbol centred at ``xy`` with radius ``r`` (data units)."""
    from matplotlib.patches import Circle, Polygon, Rectangle

    x, y = xy
    if kind in ("machine", "infinite"):
        ax.add_patch(Circle(xy, r, facecolor="white", edgecolor=color, lw=lw, zorder=4))
        ax.text(x, y, "∼" if kind == "machine" else "∞", ha="center", va="center",
                fontsize=max(6, 11 * r / 0.05), color=color, zorder=5)
    elif kind in ("gfm", "gsp", "gfl", "conv"):
        # converter: a square split by its diagonal, DC on one side, AC on the other
        ax.add_patch(Rectangle((x - r, y - r), 2 * r, 2 * r, facecolor="white",
                               edgecolor=color, lw=lw, zorder=4))
        ax.plot([x - r, x + r], [y + r, y - r], color=color, lw=lw * 0.8, zorder=5)
        fs = max(5, 9 * r / 0.05)
        ax.text(x - 0.42 * r, y - 0.42 * r, "∼", ha="center", va="center", fontsize=fs, color=color, zorder=5)
        ax.text(x + 0.42 * r, y + 0.42 * r, "=", ha="center", va="center", fontsize=fs, color=color, zorder=5)
    elif kind == "svc":
        ax.add_patch(Polygon([(x, y + r), (x + r, y), (x, y - r), (x - r, y)], closed=True,
                             facecolor="white", edgecolor=color, lw=lw, zorder=4))
        ax.text(x, y, "±", ha="center", va="center", fontsize=max(6, 10 * r / 0.05), color=color, zorder=5)
    else:  # load: the usual arrow
        r = r * 0.85
        ax.add_patch(Polygon([(x - r, y + r), (x + r, y + r), (x, y - r)], closed=True,
                             facecolor=color, edgecolor=color, lw=lw, alpha=0.85, zorder=4))


def _dist_to_segments(points: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Distance from each point to each segment A->B, as an (n_points, n_segments) array."""
    if len(A) == 0:
        return np.full((len(points), 1), np.inf)
    AB = B - A
    denom = np.einsum("ij,ij->i", AB, AB)
    denom = np.where(denom > 1e-12, denom, 1.0)
    AP = points[:, None, :] - A[None, :, :]
    t = np.clip(np.einsum("nmj,mj->nm", AP, AB) / denom, 0.0, 1.0)
    proj = A[None, :, :] + t[:, :, None] * AB[None, :, :]
    return np.linalg.norm(points[:, None, :] - proj, axis=2)


def _free_direction(p: np.ndarray, obstacles, segments, radius: float,
                    hint: np.ndarray | None = None, n_dirs: int = 24, bias: float = 0.4,
                    extra_radius: float | None = None):
    """The direction from ``p`` whose end point is farthest from everything already
    drawn (other buses, placed symbols, branch lines), nudged toward ``hint``.

    This is what keeps a dense area readable: each symbol and each label goes into
    the free space around its bus instead of at a fixed offset.
    """
    angles = np.linspace(0.0, 2 * np.pi, n_dirs, endpoint=False)
    dirs = np.column_stack([np.cos(angles), np.sin(angles)])
    obs = np.asarray(obstacles, dtype=float) if len(obstacles) else np.empty((0, 2))
    if len(obs):
        obs = obs[np.linalg.norm(obs - p, axis=1) > 1e-9]          # never avoid our own bus
    score = np.full(n_dirs, 10.0 * radius)
    for r in ([radius] if extra_radius is None else [radius, extra_radius]):
        pts = p + dirs * r
        if len(obs):
            score = np.minimum(score, np.linalg.norm(pts[:, None, :] - obs[None, :, :], axis=2).min(1))
        if segments is not None and len(segments[0]):
            score = np.minimum(score, _dist_to_segments(pts, *segments).min(1))
    score = score / radius
    if hint is not None:
        score = score + bias * (dirs @ hint)
    return dirs[int(np.argmax(score))]


def _system_layout(dae, pos: Mapping | None = None, iterations: int = 200):
    """Positions for the buses: the given ones, or a deterministic layout from the
    topology alone (spectral start, then stress majorization on graph distances)."""
    buses = [str(b) for b in dae.grid.buses]
    n = len(buses)
    if pos is not None:
        return {b: np.asarray(pos[b], dtype=float) for b in buses}
    if n == 1:
        return {buses[0]: np.zeros(2)}

    index = {b: i for i, b in enumerate(buses)}
    A = np.zeros((n, n))
    line = dae.grid.line
    for bi, bj in zip(line.bus_i, line.bus_j):
        i, j = index[str(bi)], index[str(bj)]
        A[i, j] = A[j, i] = 1.0

    from scipy.sparse.csgraph import shortest_path

    D = shortest_path(A, unweighted=True, directed=False)
    finite = np.isfinite(D)
    D = np.where(finite, D, (D[finite].max() if finite.any() else 1.0) * 1.5)
    np.fill_diagonal(D, 0.0)

    # spectral start: the two Fiedler-like eigenvectors of the graph Laplacian
    L = np.diag(A.sum(1)) - A
    _, vecs = np.linalg.eigh(L)
    X = vecs[:, 1:3] if n > 2 else np.array([[0.0, 0.0], [1.0, 0.0]])[:n]
    X = X + 1e-6 * np.arange(n)[:, None]          # break exact ties deterministically

    # stress majorization (SMACOF) with the usual 1/d^2 weights
    W = np.where(D > 0, 1.0 / np.where(D > 0, D, 1.0) ** 2, 0.0)
    np.fill_diagonal(W, 0.0)
    Vm = np.diag(W.sum(1)) - W
    Vinv = np.linalg.pinv(Vm)
    for _ in range(iterations):
        diff = X[:, None, :] - X[None, :, :]
        dist = np.linalg.norm(diff, axis=2)
        ratio = np.where(dist > 1e-9, D / np.where(dist > 1e-9, dist, 1.0), 0.0)
        B = -W * ratio
        np.fill_diagonal(B, 0.0)
        np.fill_diagonal(B, -B.sum(1))
        X = Vinv @ (B @ X)

    # canonical orientation: widest spread horizontal, deterministic sign
    X = X - X.mean(0)
    _, _, Vt = np.linalg.svd(X, full_matrices=False)
    X = X @ Vt.T
    for k in (0, 1):
        if X[0, k] > 0:
            X[:, k] *= -1
    span = np.ptp(X, axis=0).max() or 1.0
    X = X / span

    # Stress alone happily puts two buses on top of each other (they are one hop
    # from the same neighbours), which then collides their symbols and labels.
    # In the normalized layout, push apart anything closer than a readable gap.
    min_sep = min(0.65 / np.sqrt(n), 0.25)
    for _ in range(120):
        diff = X[:, None, :] - X[None, :, :]
        dist = np.linalg.norm(diff, axis=2)
        np.fill_diagonal(dist, np.inf)
        close = dist < min_sep
        if not close.any():
            break
        gap = np.where(close, min_sep - dist, 0.0)          # 0 off the diagonal, no inf/inf
        w = gap / np.where(dist > 1e-9, dist, 1.0)
        X = X + 0.35 * np.einsum("ij,ijk->ik", w, diff)
    X = X - X.mean(0)
    X = X / (np.ptp(X, axis=0).max() or 1.0)
    return {b: X[i] for i, b in enumerate(buses)}


def plot_system(dae, ax=None, pos: Mapping | None = None, figsize=None,
                bus_labels: bool = True, device_labels: str | None = "auto",
                color_by: str | None = None, at: float | None = None,
                legend: bool = True, title: str | None = None,
                device_scale: float = 1.0, annotate_branches: bool = False,
                colors: Mapping | None = None):
    """Draw the system: the network, and every device with its model type.

    Buses are dots joined by their branches (transformer branches carry the usual
    two-circle glyph, and a branch opened by a disturbance is dashed). Each device
    hangs off its bus with the classic symbol -- a circle with ``∼`` for a
    synchronous machine, a split square for a converter, an arrow for a load, a
    diamond for an SVC -- colored by category and labeled with the model type.

    :param pos: ``{bus: (x, y)}`` to impose your own layout (e.g. the published
        geographic one). Omitted, the layout is computed from the topology and is
        deterministic, so figures are reproducible.
    :param device_labels: ``"idx"`` (names only), ``"type"`` (model types),
        ``"full"`` (both, plus the rating), ``None``, or ``"auto"`` -- full on
        small systems, names only once there are many devices.
    :param color_by: a signal selector resolving to one signal per bus (e.g.
        ``"bus*:v"``); the buses are then colored by its value at time ``at``
        (default: the end of the run), with a colorbar. Turns the diagram into a
        map of the result.
    :param annotate_branches: write the sending-end active power on each branch.
    :param colors: override the per-category colors, e.g.
        ``{"machine": "k", "load": "0.4"}`` (categories as in the legend:
        ``machine``, ``gfm``, ``gsp``, ``gfl``, ``svc``, ``infinite``,
        ``load``).

        plot_system(dae)                                  # the system as drawn from the files
        plot_system(dae, color_by="bus*:v", at=1.02)      # the voltage dip during a fault
    """
    style = {k: dict(v) for k, v in _KIND_STYLE.items()}
    for k, c in (colors or {}).items():
        style[k]["color"] = c
    grid = dae.grid
    P = _system_layout(dae, pos=pos)
    buses = [str(b) for b in grid.buses]
    extent = np.array([P[b] for b in buses])
    span = np.ptp(extent, axis=0)
    span = np.where(span > 1e-9, span, 1.0)
    if ax is None:
        k = max(1.0, np.sqrt(len(buses)) / 2.6)
        ratio = float(np.clip((span[1] + 0.35) / (span[0] + 0.35), 0.45, 1.3))
        width = 6.5 * k
        _, ax = plt.subplots(figsize=figsize or (width, width * ratio + 0.9))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.grid(False)

    # The layout is normalized to ~1 across, so symbol sizes are absolute here and
    # must shrink as the network gets denser.
    unit = 0.045 * device_scale * np.sqrt(6.0 / max(6, len(buses)))
    line = grid.line

    # --- branches ---------------------------------------------------------
    seen: dict[tuple, int] = {}
    for k in range(grid.nb):
        bi, bj = str(line.bus_i[k]), str(line.bus_j[k])
        a, b = P[bi], P[bj]
        key = tuple(sorted((bi, bj)))
        rank = seen.get(key, 0)
        seen[key] = rank + 1
        d = b - a
        nrm = np.linalg.norm(d) or 1.0
        perp = np.array([-d[1], d[0]]) / nrm
        off = perp * (0.035 * ((rank + 1) // 2) * (1 if rank % 2 else -1))   # separate parallel branches
        a2, b2 = a + off, b + off
        is_open = bool(grid.line_is_open[k]) if getattr(grid, "line_is_open", None) else False
        ax.plot(*zip(a2, b2), color=_GRAY, lw=1.3, ls=":" if is_open else "-",
                alpha=0.55 if is_open else 0.9, zorder=1)
        mid = 0.5 * (a2 + b2)
        if abs(float(line.trafo[k]) - 1.0) > 1e-9:  # transformer: two touching circles
            from matplotlib.patches import Circle

            for s in (-1, 1):
                ax.add_patch(Circle(mid + d / nrm * s * unit * 0.34, unit * 0.48,
                                    facecolor="white", edgecolor=_GRAY, lw=1.0, zorder=2))
        label_box = dict(facecolor="white", alpha=0.75, pad=0.6, edgecolor="none")
        if is_open:
            ax.text(*mid, "open", ha="center", va="center", fontsize=7,
                    color=_GRAY, zorder=3, bbox=label_box)
        elif annotate_branches:
            name = f"line{bi}-{bj}:P"
            if name in _catalog(dae):
                ax.text(*mid, f"{_catalog(dae)[name].get()[0]:.0f} MW", ha="center", va="center",
                        fontsize=7, color=_GRAY, zorder=3, bbox=label_box)

    # --- buses ------------------------------------------------------------
    xy = np.array([P[b] for b in buses])
    if color_by is not None:
        idx = -1 if at is None else int(np.searchsorted(dae.time_steps, at))
        idx = int(np.clip(idx, 0, len(dae.time_steps) - 1))
        cat = _catalog(dae)
        vals, unit_lbl = [], ""
        for b in buses:
            hits = [n for n in signal_names(dae, color_by) if cat[n].owner == f"bus{b}"]
            vals.append(cat[hits[0]].get()[idx] if hits else np.nan)
            unit_lbl = cat[hits[0]].unit if hits else unit_lbl
        sc = ax.scatter(xy[:, 0], xy[:, 1], c=vals, s=130, cmap="RdYlBu", zorder=3,
                        edgecolor="k", linewidth=0.4)
        cb = ax.figure.colorbar(sc, ax=ax, shrink=0.65, fraction=0.035, pad=0.06)
        cb.set_label(f"{color_by} [{unit_lbl}] at t = {dae.time_steps[idx]:.3g} s")
    else:
        ax.scatter(xy[:, 0], xy[:, 1], s=42, color="black", zorder=3)

    # (bus labels are drawn after the devices, on the side the devices left free)

    # --- devices ----------------------------------------------------------
    at_bus: dict[str, list] = {}
    for dev in dae.device_list:
        for u in range(dev.n):
            at_bus.setdefault(str(dev.bus[u]), []).append((dev, u))
    n_dev = sum(len(v) for v in at_bus.values())
    if device_labels == "auto":
        device_labels = "full" if n_dev <= 8 else "idx"

    def _anchor(d):
        """Text alignment that makes a label grow away from ``d``."""
        return ("left" if d[0] > 0.3 else "right" if d[0] < -0.3 else "center",
                "bottom" if d[1] > 0.3 else "top" if d[1] < -0.3 else "center")

    # when a category has a single model type, the legend carries it and the
    # per-device label can be shorter (this is what keeps dense diagrams readable)
    types_by_kind: dict[str, set] = {}
    for items in at_bus.values():
        for dev, _ in items:
            types_by_kind.setdefault(_device_kind(dev), set()).add(_device_type_label(dev))

    centroid = xy.mean(0)
    kinds_present: dict[str, set] = {}
    device_dir: dict[str, np.ndarray] = {}
    widest = 0
    # everything already on the page, so later symbols can dodge it
    segments = (np.array([P[str(line.bus_i[k])] for k in range(grid.nb)]),
                np.array([P[str(line.bus_j[k])] for k in range(grid.nb)]))
    occupied = [P[b] for b in buses]
    for bus, items in sorted(at_bus.items(), key=lambda kv: -len(kv[1])):
        p = P[bus]
        # hint: the side of the bus the network does not occupy
        neigh = [P[str(line.bus_j[k])] if str(line.bus_i[k]) == bus else P[str(line.bus_i[k])]
                 for k in range(grid.nb) if bus in (str(line.bus_i[k]), str(line.bus_j[k]))]
        if neigh:
            v = np.mean([(q - p) / (np.linalg.norm(q - p) or 1.0) for q in neigh], axis=0)
            hint = -v if np.linalg.norm(v) > 1e-6 else np.array([0.0, -1.0])
        else:
            hint = p - centroid
        hint = hint / (np.linalg.norm(hint) or 1.0)
        device_dir[bus] = hint
        for m, (dev, u) in enumerate(items):
            direction = _free_direction(p, occupied, segments, radius=unit * 3.0,
                                        extra_radius=unit * 4.6, hint=hint)
            centre = p + direction * unit * 3.0
            occupied.append(centre)
            kind = _device_kind(dev)
            color = style[kind]["color"]
            kinds_present.setdefault(kind, set()).add(_device_type_label(dev))
            ax.plot(*zip(p, centre - direction * unit), color=color, lw=1.2, zorder=2)
            _sym(ax, kind, centre, unit, color)
            if device_labels:
                name = _device_display_name(dev, u)
                if device_labels == "type":
                    text = _device_type_label(dev)
                elif device_labels == "full":
                    size = _device_size_label(dae, dev, u)
                    kind_type = _device_type_label(dev)
                    if len(types_by_kind.get(kind, ())) < 2 and legend:
                        kind_type = ""            # already stated once, in the legend
                    detail = " · ".join(x for x in (kind_type, size) if x)
                    text = f"{name}\n{detail}" if name and detail else (name or detail)
                else:
                    text = name
                if text:
                    longest = max(len(ln) for ln in text.splitlines())
                    widest = max(widest, longest)
                    ha, va = _anchor(direction)
                    lp = centre + direction * unit * 1.25
                    ax.annotate(text, lp, ha=ha, va=va, fontsize=7, color=color,
                                zorder=6, linespacing=1.3)
                    # the label is wide text, not a point: block out its extent so the
                    # next device (and the bus labels) are placed clear of it
                    half = 0.5 * 0.011 * longest
                    shift = {"left": half, "right": -half, "center": 0.0}[ha]
                    for frac in (-1.0, -0.5, 0.0, 0.5, 1.0):
                        occupied.append(lp + np.array([shift + frac * half, 0.0]))

    if bus_labels:
        for b in buses:
            d = _free_direction(P[b], occupied, segments, radius=unit * 1.1,
                                hint=-device_dir.get(b, np.array([0.0, 1.0])), bias=0.15)
            pos_lbl = P[b] + d * unit * 1.1
            occupied.append(pos_lbl)
            ha, va = _anchor(d)
            ax.annotate(b, pos_lbl, ha=ha, va=va,
                        fontsize=8 if len(buses) <= 20 else 7, color="black", zorder=6,
                        bbox=dict(facecolor="white", alpha=0.6, pad=0.6, edgecolor="none"))

    if legend and kinds_present:
        from matplotlib.lines import Line2D

        markers = {"machine": "o", "gfm": "s", "gsp": "s", "gfl": "s", "conv": "s",
                   "svc": "D", "infinite": "o", "load": "v"}

        def _types(k):
            types = sorted(t for t in kinds_present[k] if t)
            if len(types) <= 2:
                return ", ".join(types)
            families = sorted({t.split(" · ")[0] for t in types})     # the model, not every strategy mix
            return ", ".join(families[:4]) + (f", +{len(families) - 4} more" if len(families) > 4 else "")

        handles = [Line2D([], [], marker=markers[k], color="none", markerfacecolor="white",
                          markeredgecolor=style[k]["color"], markersize=9,
                          label=(f"{style[k]['label']}: {_types(k)}"
                                 if _types(k) and _types(k).lower() != style[k]["label"].lower()
                                 else style[k]["label"]))
                   for k in style if k in kinds_present]
        ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.05),
                  fontsize=8, ncol=1 if len(handles) > 3 else len(handles), frameon=False)

    name = getattr(getattr(dae, "cfg", None), "testsystemfile", None)
    ax.set_title(title if title is not None else
                 f"{name or 'system'}: {grid.nn} buses, {grid.nb} branches, {n_dev} devices")
    # room for the symbols, plus room for the text hanging off them
    pad_y = 6 * unit + 0.05
    pad_x = pad_y + 0.011 * widest
    ax.set_xlim(extent[:, 0].min() - pad_x, extent[:, 0].max() + pad_x)
    ax.set_ylim(extent[:, 1].min() - pad_y, extent[:, 1].max() + pad_y)
    return ax


def power_flow_table(dae, which: str = "bus"):
    """The initial power flow as a DataFrame: ``which="bus"`` or ``"branch"``.

    Thin wrapper around ``dae.grid.power_flow_tables(dae)``; the operating point
    the whole simulation starts from.
    """
    bus, branch = dae.grid.power_flow_tables(dae)
    if which == "bus":
        return bus
    if which == "branch":
        return branch
    raise KeyError(f"which must be 'bus' or 'branch', not {which!r}")


# ---------------------------------------------------------------------------
# Small-signal analysis
# ---------------------------------------------------------------------------


def state_matrix(dae, as_frame: bool = False):
    """The reduced state matrix ``A`` at the operating point (the linearization the
    eigenvalues come from), running the analysis first if needed.

    Returns the raw ``(n, n)`` array, or a labeled DataFrame with ``as_frame=True``.
    """
    small_signal(dae)
    if getattr(dae, "A", None) is None:
        raise RuntimeError("no state matrix available (the small-signal analysis was skipped)")
    if not as_frame:
        return dae.A
    import pandas as pd

    return pd.DataFrame(dae.A, index=dae.state_names, columns=dae.state_names)


def participation_table(dae, mode: int = 1, top: int | None = 10):
    """Participation factors of one mode as a DataFrame (thin wrapper around
    ``dae.participation_table``). ``mode`` is the id from :func:`modal_table`."""
    small_signal(dae)
    return dae.participation_table(mode=mode, top=top)


def small_signal(dae, report: bool = False, top_k: int = 4):
    """Run the eigenvalue / participation analysis at the operating point of the
    run (a single CasADi Jacobian plus ``numpy.linalg.eig``) and return the list
    of mode dicts, least damped first. Set ``report=True`` to also print the
    built-in modal report."""
    if getattr(dae, "eigenvalues", None) is None or len(dae.eigenvalues) == 0 or not getattr(dae, "modes", None):
        dae.eigenvalue_analysis()
    if report:
        dae.print_modal_report(top_k=top_k)
    return list(dae.modes)


def modal_table(dae, n: int | None = 8, min_freq: float | None = None, max_freq: float | None = None,
                oscillatory_only: bool = False):
    """A pandas table of the modes: eigenvalue, frequency, damping ratio, dominant states."""
    import pandas as pd

    pd.set_option("display.max_colwidth", None)
    pd.set_option("display.width", 200)
    modes = small_signal(dae)
    rows = []
    for m in modes:
        if oscillatory_only and not m["is_complex"]:
            continue
        if min_freq is not None and m["freq_hz"] < min_freq:
            continue
        if max_freq is not None and m["freq_hz"] > max_freq:
            continue
        dom = ", ".join(f"{name} ({pf:.2f})" for name, pf in m["dominant"][:3])
        rows.append(
            {
                "mode": m["id"],
                "eigenvalue": f"{m['sigma']:+.3f} {'± ' + format(m['omega'], '.3f') + 'j' if m['is_complex'] else ''}",
                "f [Hz]": round(m["freq_hz"], 3) if m["is_complex"] else np.nan,
                "zeta": round(m["zeta"], 3),
                "dominant states": dom,
            }
        )
    df = pd.DataFrame(rows)
    return df.head(n) if n else df


def plot_modes(dae, ax=None, label: str | None = None, color: str | None = None,
               damping_ref: float = 0.05, fmax: float | None = None,
               xlim: tuple[float, float] | None = None, annotate: bool = False, **kw):
    """s-plane scatter of the eigenvalues (imaginary axis in Hz).

    ``fmax`` and ``xlim`` zoom into the slow part of the spectrum, e.g.
    ``plot_modes(dae, fmax=5, xlim=(-6, 0.5))`` for the electromechanical modes.
    Call twice with different ``label``/``color`` on the same ``ax`` to compare two
    operating points or two designs. ``annotate=True`` writes the mode ids.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 5))
    small_signal(dae)
    lam = np.asarray(dae.eigenvalues)
    keep = np.ones(lam.size, dtype=bool)
    if fmax is not None:
        keep &= np.abs(lam.imag) <= 2 * np.pi * fmax
    if xlim is not None:
        keep &= (lam.real >= xlim[0]) & (lam.real <= xlim[1])
    lam_k = lam[keep]
    ax.scatter(lam_k.real, lam_k.imag / (2 * np.pi), s=30, label=label, color=color,
               edgecolor="none", alpha=0.9, zorder=3, **kw)
    if annotate:
        for m in dae.modes:
            e = m["eig"]
            if keep[m["rep_idx"]] and m["is_complex"]:
                ax.annotate(str(m["id"]), (e.real, e.imag / (2 * np.pi)), xytext=(4, 2),
                            textcoords="offset points", fontsize=8, color=_GRAY)
    if not getattr(ax, "_hermess_wedge", False):
        ymax = max(abs(lam_k.imag).max() / (2 * np.pi) if lam_k.size else 0.5, 0.5) * 1.1
        xmin = (xlim[0] if xlim is not None else min(lam_k.real.min(), -0.1) * 1.05)
        xmax = (xlim[1] if xlim is not None else max(0.1, 0.05 * abs(xmin)))
        slope = np.sqrt(1 - damping_ref**2) / damping_ref
        xs = np.linspace(xmin, 0, 50)
        ax.plot(xs, -xs * slope / (2 * np.pi), color=_GRAY, ls=":", lw=1)
        ax.plot(xs, xs * slope / (2 * np.pi), color=_GRAY, ls=":", lw=1)
        ax.axvline(0, color="k", lw=0.8)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(-ymax, ymax)
        ax.set_xlabel(r"real part $\sigma$ [1/s]")
        ax.set_ylabel("frequency [Hz]")
        ax.set_title(f"Eigenvalues (dotted: $\\zeta$ = {damping_ref:g})")
        ax._hermess_wedge = True
    if label:
        ax.legend(loc="upper left")
    return ax
