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

"""Pre-flight validation of a (system, options) pair, run before a simulation
starts so obvious mistakes surface as one readable dialog instead of a failed
run minutes later.

Checks are static, based on the parsed system files and the resolved
configuration; nothing is built or imported from the model layer. Errors block
the run (the core would reject or fail on them anyway); warnings ask the user
to confirm.
"""

from __future__ import annotations

from dataclasses import dataclass

from hermess.config import config as default_config

#: Output-step count above which a run is flagged as very large.
_MANY_STEPS = 2_000_000


@dataclass
class Issue:
    severity: str  #: ``"error"`` (blocks the run) or ``"warning"`` (confirm)
    message: str


def _error(message: str) -> Issue:
    return Issue("error", message)


def _warning(message: str) -> Issue:
    return Issue("warning", message)


def _components(buses: "list[str]", edges: "list[tuple[str, str]]"):
    """Connected components over the bus set, as lists of bus names."""
    parent = {bus: bus for bus in buses}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j in edges:
        if i in parent and j in parent:
            parent[find(i)] = find(j)
    groups: dict[str, list] = {}
    for bus in buses:
        groups.setdefault(find(bus), []).append(bus)
    return sorted(groups.values(), key=len, reverse=True)


def _is_dae_device(entry) -> bool:
    """Whether a device entry certainly adds private algebraic variables."""
    return entry.get("filter") == "LCL_static" or "DAE" in entry.kind


def validate(desc, overrides: dict) -> "list[Issue]":
    """Validate the parsed system against the effective run options.

    :param desc: A :class:`~hermess.gui.sysparse.SystemDescription`.
    :param overrides: The GUI's config overrides on top of the shipped
        defaults.
    """
    issues: list[Issue] = []
    cfg = {**default_config.model_dump(), **overrides}

    # ---- network connectivity ----------------------------------------------
    buses = desc.buses()
    edges = [
        (e.get("bus_i"), e.get("bus_j"))
        for e in desc.lines
        if e.get("bus_i") and e.get("bus_j")
    ]
    if len(buses) > 1:
        components = _components(buses, edges)
        if len(components) > 1:
            detached = ", ".join(
                "{" + ", ".join(sorted(c)) + "}" for c in components[1:]
            )
            issues.append(
                _error(
                    f"The network is not connected: bus group(s) {detached} have "
                    f"no line to the main group "
                    "{" + ", ".join(sorted(components[0])) + "}. "
                    "Add the missing Line entries in sim_param.txt."
                )
            )
    elif not buses:
        issues.append(_error("The system defines no buses."))

    # Dangling references: an entry naming a bus that no other entry defines.
    known = set(buses)
    for entry in desc.disturbances:
        for key in ("bus", "bus_i", "bus_j"):
            value = entry.get(key)
            if value and value not in known:
                issues.append(
                    _warning(
                        f"Disturbance at t = {entry.get('time', '?')} refers to "
                        f"bus \"{value}\", which does not exist in the system."
                    )
                )

    # ---- integration scheme -------------------------------------------------
    scheme = cfg["int_scheme_sim"]
    line_dyn = cfg["line_dyn"]
    if scheme in ("cvodes", "rk"):
        if not line_dyn:
            issues.append(
                _error(
                    f"The integration scheme \"{scheme}\" only supports ODE "
                    "systems, but with line_dyn off the network voltages are "
                    "algebraic variables, so the model is a DAE. Use \"idas\" "
                    "or \"collocation\", or enable dynamic lines."
                )
            )
        else:
            culprits = [e for e in desc.devices if _is_dae_device(e)]
            if culprits:
                names = ", ".join(
                    f"{e.get('idx') or e.kind}" for e in culprits
                )
                issues.append(
                    _error(
                        f"The integration scheme \"{scheme}\" only supports ODE "
                        f"systems, but {names} add(s) algebraic variables "
                        "(quasi-static filter or DAE model variant). Use "
                        "\"idas\" or \"collocation\"."
                    )
                )

    # ---- shunt susceptance under dynamic lines ------------------------------
    # With line_dyn the line charging b is the bus capacitance of the dynamic
    # network; GridSim.setup rejects any bus whose summed b is zero.
    if line_dyn and buses:
        b_sum = {bus: 0.0 for bus in buses}
        parseable = True
        for e in desc.lines:
            try:
                b_val = float(e.get("b", "0") or "0")
            except ValueError:
                parseable = False
                continue
            for key in ("bus_i", "bus_j"):
                if e.get(key) in b_sum:
                    b_sum[e.get(key)] += b_val
        bare = sorted(bus for bus, total in b_sum.items() if total == 0.0)
        if bare and parseable:
            issues.append(
                _error(
                    f"Bus(es) {', '.join(bare)} have zero summed line charging "
                    "b, which the dynamic network model rejects (b is the bus "
                    "capacitance). Give their lines a nonzero b, or disable "
                    "dynamic lines."
                )
            )

    # ---- inverter filter vs network model (mirror of the core's warning) ----
    for entry in desc.devices:
        filt = entry.get("filter")
        is_inverter = entry.kind.startswith("Grid")
        if not is_inverter:
            continue
        static_filter = filt == "LCL_static"
        if static_filter and line_dyn:
            issues.append(
                _warning(
                    f"{entry.get('idx') or entry.kind} uses the quasi-static "
                    "filter LCL_static on a dynamic network (line_dyn on); the "
                    "pairing is physically incoherent."
                )
            )
        elif not static_filter and not line_dyn:
            issues.append(
                _warning(
                    f"{entry.get('idx') or entry.kind} uses a dynamic filter on "
                    "a quasi-static network (line_dyn off); the pairing is "
                    "physically incoherent. Select filter = \"LCL_static\" or "
                    "enable dynamic lines."
                )
            )

    # ---- reference frame ----------------------------------------------------
    if cfg["omega_mode"] == "single" and cfg["omega_single_idx"]:
        units = {e.get("idx") for e in desc.devices if e.get("idx")}
        if cfg["omega_single_idx"] not in units:
            issues.append(
                _error(
                    f"omega_mode is \"single\" with reference device "
                    f"\"{cfg['omega_single_idx']}\", but no device in this "
                    f"system has that idx (available: {', '.join(sorted(units)) or 'none'})."
                )
            )

    # ---- time grid ----------------------------------------------------------
    ts, t_end = cfg["ts"], cfg["T_end"]
    if ts <= 0:
        issues.append(_error(f"The time step ts = {ts} must be positive."))
    if t_end <= 0:
        issues.append(_error(f"The end time T_end = {t_end} must be positive."))
    if ts > 0 and t_end > 0:
        if ts >= t_end:
            issues.append(
                _error(
                    f"The time step ts = {ts} is not smaller than "
                    f"T_end = {t_end}; there is nothing to integrate."
                )
            )
        elif t_end / ts > _MANY_STEPS:
            issues.append(
                _warning(
                    f"T_end / ts is about {t_end / ts:.0f} output steps; the "
                    "run may take very long and use a lot of memory."
                )
            )

    return issues
