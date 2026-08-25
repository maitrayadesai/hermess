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

"""Plain-data view of a finished simulation.

:class:`SimulationResults` collects the trajectories, the initial power flow
and the small-signal data of a run into picklable numpy/pandas containers,
detached from the symbolic model. :func:`extract_results` builds it from the
:class:`~hermess.system.DaeSim` a run returns. The container is what crosses
process boundaries (the GUI runs simulations in a worker process) and what a
script would save to disk, so it must stay free of CasADi objects.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass
class DeviceTrajectories:
    """Differential-state trajectories of one device unit."""

    model: str  #: model name, e.g. ``"GridForming_inverter_model"``
    unit: str  #: unit identifier from the system file, e.g. ``"GFMI2"``
    bus: str  #: bus the unit is connected to
    states: "dict[str, np.ndarray]"  #: state name -> trajectory, shape (nts,)


@dataclass
class SmallSignalResults:
    """Small-signal analysis data at the operating point."""

    eigenvalues: np.ndarray  #: complex eigenvalues of the reduced state matrix
    state_names: "list[str]"  #: state labels, ordering of the rows of ``participation``
    participation: np.ndarray  #: normalized participation factors (state x mode)
    modes: "list[dict]"  #: mode dicts from :meth:`DaeSim._build_modes`
    A: Optional[np.ndarray] = None  #: reduced state matrix ``dx/dt = A dx``


@dataclass
class SimulationResults:
    """All plottable data of one finished run, detached from the model."""

    system: str  #: system name (``config.testsystemfile``)
    t: np.ndarray  #: output time grid, shape (nts,)
    voltage: "dict[str, np.ndarray]"  #: bus -> complex voltage, shape (nts,)
    power: "dict[str, np.ndarray]"  #: bus -> complex injection P+jQ, shape (nts,)
    devices: "list[DeviceTrajectories]" = field(default_factory=list)
    small_signal: Optional[SmallSignalResults] = None
    power_flow_bus: Optional[pd.DataFrame] = None
    power_flow_branch: Optional[pd.DataFrame] = None
    config: "dict[str, Any]" = field(default_factory=dict)  #: resolved run settings
    hermess_version: str = ""
    created: str = ""  #: ISO timestamp of extraction

    def voltage_magnitude(self, bus: str) -> np.ndarray:
        """Voltage magnitude trajectory of one bus [p.u.]."""
        return np.abs(self.voltage[bus])

    def buses(self) -> "list[str]":
        """Bus names in system order."""
        return list(self.voltage.keys())


def extract_results(dae, config=None) -> SimulationResults:
    """Build a :class:`SimulationResults` from a finished
    :class:`~hermess.system.DaeSim`.

    Expects the per-bus and per-device result dictionaries to be filled, i.e.
    ``save_data`` has run (as :func:`hermess.run.run` does after the
    simulation).

    :param dae: The finished model, e.g. the return value of
        :func:`hermess.simulate`.
    :param config: The :class:`~hermess.config.Config` of the run, recorded for
        provenance (optional).
    """
    import hermess

    grid = dae.grid

    voltage = {
        bus: traj[0, :] + 1j * traj[1, :] for bus, traj in grid.yf.items()
    }
    power = {bus: traj[0, :] + 1j * traj[1, :] for bus, traj in grid.sf.items()}

    devices = []
    for item in dae.device_list:
        if not item.properties.get("save_data") or not item.xf:
            continue
        for unit, row in item.int.items():
            devices.append(
                DeviceTrajectories(
                    model=item._name,
                    unit=str(unit),
                    bus=str(item.bus[row]),
                    states={
                        state: np.asarray(item.xf[state][row, :])
                        for state in item.states
                        if state in item.xf
                    },
                )
            )

    small_signal = None
    eigs = getattr(dae, "eigenvalues", None)
    if eigs is not None and np.size(eigs) > 0:
        small_signal = SmallSignalResults(
            eigenvalues=np.asarray(eigs),
            state_names=list(dae.state_names),
            participation=np.asarray(dae.participation_factors_normalized),
            modes=list(dae.modes) if dae.modes is not None else [],
            A=np.asarray(dae.A) if dae.A is not None else None,
        )

    # The initial power flow is a nicety; never let its reconstruction sink
    # the extraction of an otherwise complete run.
    pf_bus = pf_branch = None
    try:
        pf_bus, pf_branch = grid.power_flow_tables(dae)
    except Exception:
        logging.warning("Initial power flow tables could not be reconstructed.")

    return SimulationResults(
        system=config.testsystemfile if config is not None else "",
        t=np.asarray(dae.time_steps),
        voltage=voltage,
        power=power,
        devices=devices,
        small_signal=small_signal,
        power_flow_bus=pf_bus,
        power_flow_branch=pf_branch,
        config=config.model_dump(mode="json") if config is not None else {},
        hermess_version=hermess.__version__,
        created=datetime.datetime.now().isoformat(timespec="seconds"),
    )
