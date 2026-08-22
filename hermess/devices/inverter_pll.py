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

"""Inverter phase-locked-loop (frequency/phase estimator) strategies.

The PLL is a measurement strategy, separate from the angle source (the inverter
analogue of the synchronous machine's PSS): it produces a signal (``omega_pll``)
consumed by another strategy (the angle source), host-mediated via
``host.pll_frequency(dae)``, and never references its consumer. Being a distinct
axis lets a grid-forming converter carry a PLL for FRT/monitoring without baking
it into "grid-following". ``pll=None`` (the default) means no PLL block.

It owns its integrator/angle states (``epsilon`` / ``delta_pll``), registered last
in the state vector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List

import casadi as ca
import numpy as np

if TYPE_CHECKING:
    from hermess.system import Dae


class PLL(ABC):
    """Abstract base class for inverter PLL (frequency estimator) strategies.

    Like the SG strategies, the PLL does not own state arrays or DAE indices; it
    declares them and the host ``Inverter`` registers them on itself. Its
    :meth:`fgcall` writes its own state equations into ``dae.f`` and publishes the
    estimated synchronizing frequency on ``host.omega_pll`` (an algebraic
    expression, not a registered variable), which the host exposes to consumers
    via ``host.pll_frequency(dae)`` and which the reference-frame machinery in
    ``system.py`` reads for grid-following devices.
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
    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b) -> None:
        """Write the PLL state equations into ``dae.f`` and set ``host.omega_pll``
        to the estimated synchronizing frequency (read by the angle source via
        ``host.pll_frequency(dae)``)."""
        ...

    def finit_sequential(self, host, dae: Dae, Vfd_ext, Vfq_ext) -> Dict[str, np.ndarray]:
        """Steady-state init of the PLL from the filter voltage (decoupled).
        Returns its state values (e.g. ``epsilon``, ``delta_pll``). The base raises;
        a PLL without a sequential init falls under the joint init."""
        raise NotImplementedError(
            f"{type(self).__name__} provides no sequential PLL init; implement "
            f"finit_sequential() or set _init_method='joint' on the device."
        )


class SRF_PLL(PLL):
    """Synchronous-reference-frame PLL: locks the PLL frame to the filter voltage
    by driving its q-axis component to zero through a PI loop.

    States: ``epsilon`` (PI integrator), ``delta_pll`` (PLL-frame angle relative to
    the network).
    """

    def states(self) -> List[str]:
        return ["epsilon", "delta_pll"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {"Kpll_p": 0.5, "Kpll_i": 4.69}

    def x0(self) -> Dict[str, float]:
        return {"epsilon": 0, "delta_pll": 0}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Kpll_p": "Proportional gain for PLL",
            "Kpll_i": "Integral gain for PLL",
            "epsilon": "PLL integrator state",
            "delta_pll": "angle difference between the dq-reference frame of the PLL and the network",
        }

    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b) -> None:
        Vfd_ext_s = host.var_sym(dae, "Vfd_ext")
        Vfq_ext_s = host.var_sym(dae, "Vfq_ext")
        delta_pll_s = host.var_sym(dae, "delta_pll")

        # PLL q-axis voltage: the q-component of the filter voltage rotated into
        # the PLL frame (the d-component is unused).
        _, Vfq_pll = host.to_internal(Vfd_ext_s, Vfq_ext_s, delta_pll_s)
        host.omega_pll = (
            dae.omega_net
            + host.Kpll_p * Vfq_pll
            + host.Kpll_i * dae.x[host.epsilon]
        )
        delta_omega_pll = host.omega_pll - omega_ref_vec

        dae.f[host.epsilon] = Vfq_pll
        dae.f[host.delta_pll] = omega_b * delta_omega_pll

    def finit_sequential(self, host, dae: Dae, Vfd_ext, Vfq_ext) -> Dict[str, np.ndarray]:
        """PLL lock at steady state: the PLL frame aligns so its q-axis voltage is
        zero (``Vfq_pll = 0``), the integrator settles (``epsilon = 0``), and
        ``delta_pll`` is the filter-voltage angle. Solved as a 3x3 Newton for
        (Vfq_pll, epsilon, delta_pll); the first is an intermediate."""
        n = host.n
        n_unknowns = 3

        Vfq_pll = ca.SX.sym("Vfq_pll", n)
        epsilon = ca.SX.sym("epsilon", n)
        delta_pll = ca.SX.sym("delta_pll", n)

        outputs = ca.SX(np.zeros(n_unknowns * n))
        outputs[:n] = (
            Vfd_ext * np.sin(-delta_pll) + Vfq_ext * np.cos(-delta_pll) - Vfq_pll
        )
        outputs[n : 2 * n] = Vfq_pll
        outputs[2 * n : 3 * n] = host.Kpll_p * Vfq_pll + host.Kpll_i * epsilon

        h = ca.Function(
            "h", [ca.vertcat(Vfq_pll, epsilon, delta_pll)], [ca.vertcat(outputs)]
        )
        G = ca.rootfinder("G", "newton", h)
        sol = np.array(G(ca.vertcat(np.zeros(n_unknowns * n)))).flatten()

        return {"epsilon": sol[n : 2 * n], "delta_pll": sol[2 * n : 3 * n]}


PLL_REGISTRY: Dict[str, type] = {
    "SRF_PLL": SRF_PLL,
}
