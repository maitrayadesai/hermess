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

"""Inverter outer voltage-control strategies (the reactive / voltage side).

The voltage controller is the AVR-analogue of the converter: it turns the
reactive-power / voltage setpoints into the voltage-magnitude reference ``Vcd``
that the inner control ladder regulates the capacitor voltage to. It owns the
reactive-power measurement state ``Qc_tilde`` and the ``Qref`` / ``Vref``
setpoints.

The strategy owns the ``Qc_tilde`` state but the host writes its measurement-
filter equation ``d Qc_tilde/dt = omega_f (Qc - Qc_tilde)`` because ``Qc`` comes
from the shared Park-transform loop in ``Inverter.fgcall``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List

import casadi as ca
import numpy as np

if TYPE_CHECKING:
    from hermess.system import Dae


class VoltageControl(ABC):
    """Abstract base class for inverter outer voltage-control strategies.

    Must expose the voltage-magnitude reference: :meth:`fgcall` returns the ``Vcd``
    vector consumed by the inner control ladder (host-mediated via
    ``host.voltage_command``). Reads host params/states/setpoints by attribute.
    """

    @abstractmethod
    def states(self) -> List[str]:
        ...

    def algebs(self) -> List[str]:
        return []

    def algebs_units(self) -> Dict[str, str]:
        return {}

    def algebs_x0(self) -> Dict[str, float]:
        return {}

    @abstractmethod
    def units(self) -> List[str]:
        ...

    @abstractmethod
    def params(self) -> Dict[str, float]:
        ...

    @abstractmethod
    def x0(self) -> Dict[str, float]:
        ...

    @abstractmethod
    def descriptions(self) -> Dict[str, str]:
        ...

    @abstractmethod
    def setpoints(self) -> Dict[str, float]:
        ...

    @abstractmethod
    def fgcall(self, host, dae: Dae):
        """Publish the voltage-magnitude reference on ``host.Vcd`` (read by the inner
        controller via ``host.voltage_command(dae)``). The host writes the
        ``Qc_tilde`` measurement-filter equation (``Qc`` is host-computed)."""
        ...

    def finit_sequential(
        self, host, dae: Dae, Qc: np.ndarray, Vcd: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Resolve the voltage controller's states/setpoints from the
        (frame-invariant) reactive power ``Qc`` and the inner controller's voltage
        command ``Vcd``. This is where the Q-V gauge lives. The base raises; each
        voltage law declares its own resolution."""
        raise NotImplementedError(
            f"{type(self).__name__} provides no sequential voltage init; implement "
            f"finit_sequential() or set _init_method='joint' on the device."
        )


class QVDroop(VoltageControl):
    """Reactive-power / voltage droop: ``Vcd = Vref + Kq (Qref - Qc_tilde)``.

    Owns the filtered reactive-power state ``Qc_tilde``, the droop gain ``Kq`` and
    the ``Qref`` / ``Vref`` setpoints.
    """

    def states(self) -> List[str]:
        return ["Qc_tilde"]

    def units(self) -> List[str]:
        return ["p.u."]

    def params(self) -> Dict[str, float]:
        return {"Kq": 0.1}

    def x0(self) -> Dict[str, float]:
        return {"Qc_tilde": 0}

    def setpoints(self) -> Dict[str, float]:
        return {"Qref": 0.01, "Vref": 1.05}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Kq": "Droop coefficient for Q-V",
            "Qref": "Reactive power set point",
            "Vref": "Voltage set point",
            "Qc_tilde": "Filtered internal reactive power",
        }

    def fgcall(self, host, dae: Dae):
        # Publish the voltage-magnitude command on the host (read by the inner
        # controller via host.voltage_command).
        host.Vcd = host.Vref + host.Kq * (host.Qref - dae.x[host.Qc_tilde])

    def finit_sequential(
        self, host, dae: Dae, Qc: np.ndarray, Vcd: np.ndarray
    ) -> Dict[str, np.ndarray]:
        # The Q-V droop Vcd = Vref + Kq(Qref - Qc_tilde) is static, so Qref/Vref are
        # a 1-parameter gauge; the convention Qref = Qc (the dispatched reactive
        # power, = Qc_tilde at steady state) zeroes the droop term, giving Vref =
        # Vcd. The power filter settles at Qc_tilde = Qc.
        return {"Qc_tilde": Qc, "Qref": Qc, "Vref": Vcd}


VOLTAGE_REGISTRY: Dict[str, type] = {
    "QVDroop": QVDroop,
}
