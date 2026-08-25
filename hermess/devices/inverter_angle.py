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

"""Inverter angle-source strategies (what makes a converter forming vs following).

An angle source is selected on a converter line of a system file, e.g.
``angle = "Droop"``; the names accepted at any moment are returned by
``hermess.registered("angle")``. Every model below documents its equations and a
table mapping the code parameter names to the mathematical symbols used there.

The angle source produces the converter frequency ``omega_c`` and integrates the
converter-frame angle ``delta_c``. It fuses the synchronous machine's governor and
shaft roles (an inverter has no separable mechanical-power intermediate), so the
active-power droop and the power-measurement state ``Pc_tilde`` live here. It is
the mandatory axis: a grid-forming converter sets its own frequency from the droop
off nominal (``DroopAngle``, exposing ``host.omega_c``); a grid-following
converter rides on a PLL's frequency (``PLLAngle``, reading ``host.pll_frequency``).
Future variants: VSM (swing ODE), dVOC, matching control.

The angle source owns the ``Pc_tilde`` state and the droop, but the first-order
power-measurement filter equation ``d Pc_tilde/dt = omega_f (Pc - Pc_tilde)`` is
written by the host, because ``Pc`` is computed from the shared Park-transform loop
in ``Inverter.fgcall``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List

import casadi as ca
import numpy as np

if TYPE_CHECKING:
    from hermess.system import Dae


class AngleSource(ABC):
    """Abstract base class for inverter angle-source strategies (pluggable).

    Must own ``delta_c`` (and, for the droop family, ``Pc_tilde``) and expose the
    converter frequency: :meth:`fgcall` returns the ``omega_c`` vector consumed by
    the host's inner control ladder and writes ``dae.f[delta_c]``. The strategy
    reads host params/states/setpoints by attribute (``host.Kp``, ``host.Pref``,
    ``dae.x[host.Pc_tilde]``) and, for the following variant, the synchronizing
    frequency via ``host.pll_frequency(dae)``.
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
    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b):
        """Return the ``omega_c`` vector and write ``dae.f[delta_c]`` (the angle
        dynamics). Grid-forming variants also set ``host.omega_c``; grid-following
        variants leave it unset and read ``host.pll_frequency(dae)`` instead."""
        ...

    def steady_frequency(self, host, dae: Dae) -> np.ndarray:
        """The converter frequency at steady state, fed to the inner-control init's
        decoupling terms. Nominal for ANY synchronizing source: ``delta_c`` steady
        forces ``omega_c = omega_ref = omega_net``, independent of the angle law."""
        return dae.omega_net * np.ones(host.n)

    def finit_sequential(
        self, host, dae: Dae, Pc: np.ndarray, delta_c: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Resolve the angle source's states/setpoints from the (frame-invariant)
        active power ``Pc`` and the inner-controller's frame angle ``delta_c``. The
        base raises; each angle source declares its own."""
        raise NotImplementedError(
            f"{type(self).__name__} provides no sequential angle init; implement "
            f"finit_sequential() or set _init_method='joint' on the device."
        )


class _PowerDroopAngle(AngleSource):
    """Shared declarations for the power-droop angle family (``Pc_tilde`` +
    ``delta_c`` states, ``Kp`` droop gain, ``Pref`` setpoint). Concrete subclasses
    differ only in the frequency anchor inside :meth:`fgcall`."""

    def states(self) -> List[str]:
        return ["Pc_tilde", "delta_c"]

    def units(self) -> List[str]:
        return ["p.u.", "rad"]

    def params(self) -> Dict[str, float]:
        return {"Kp": 0.02}

    def x0(self) -> Dict[str, float]:
        return {"Pc_tilde": 0.1, "delta_c": 0}

    def setpoints(self) -> Dict[str, float]:
        return {"Pref": 0.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Kp": "Droop coefficient for P-f",
            "Pref": "Active power set point",
            "Pc_tilde": "Filtered internal active power",
            "delta_c": "Converter-frame angle relative to the network",
        }

    def finit_sequential(
        self, host, dae: Dae, Pc: np.ndarray, delta_c: np.ndarray
    ) -> Dict[str, np.ndarray]:
        # Synchronization fixes Pref = Pc (omega_c = omega_net => the droop term is
        # zero); the power-measurement filter settles at Pc_tilde = Pc. delta_c is
        # the inner controller's frame-alignment result, owned here.
        return {"Pc_tilde": Pc, "delta_c": delta_c, "Pref": Pc}


class DroopAngle(_PowerDroopAngle):
    r"""Grid-forming droop angle source: the converter sets its own frequency
    from the active-power droop off the nominal frequency.

    Selected on a converter line with ``angle = "Droop"``.

    **Model.**

    .. math::

       \omega_c &= \omega_{net} + R_c^{p} \left( p_c^{*} - \tilde{p}_c \right) \\
       \dot{\delta}_c &= \omega_b \left( \omega_c - \omega_{ref} \right)

    The filtered active power obeys the measurement filter
    :math:`\dot{\tilde{p}}_c = \omega_f ( p_c - \tilde{p}_c )`, written by the
    host converter (:math:`p_c` comes from the shared Park-transform loop in
    ``Inverter.fgcall``). :math:`\omega_{ref}` is the reference frequency
    selected by ``omega_mode`` and :math:`\omega_{net}` the nominal network
    frequency (1 p.u.). The converter frequency is exposed as ``host.omega_c``
    (read by the center-of-inertia / single reference-frame machinery in
    ``system.py``).

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``Kp``", ":math:`R_c^{p}`", "P-f droop coefficient", "0.02"
       "``Pc_tilde``", ":math:`\tilde{p}_c`", "filtered active power (state) [p.u.]", ""
       "``delta_c``", ":math:`\delta_c`", "converter-frame angle relative to the network (state) [rad]", ""
       "``Pref``", ":math:`p_c^{*}`", "active-power setpoint (set to :math:`p_c` by the initialization)", ""
    """

    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b):
        host.omega_c = dae.omega_net + host.Kp * (host.Pref - dae.x[host.Pc_tilde])
        delta_omega_c = host.omega_c - omega_ref_vec
        dae.f[host.delta_c] = omega_b * delta_omega_c
        return host.omega_c


class PLLAngle(_PowerDroopAngle):
    r"""Grid-following angle source: the converter frequency rides on the PLL's
    synchronizing frequency plus the active-power droop. Pairs with a PLL
    strategy (which owns :math:`\omega_{pll}` and the PLL states).

    Selected on a converter line with ``angle = "PLL"``.

    **Model.**

    .. math::

       \omega_c &= \omega_{pll} + R_c^{p} \left( p_c^{*} - \tilde{p}_c \right) \\
       \dot{\delta}_c &= \omega_b \left( \omega_c - \omega_{ref} \right)

    with :math:`\omega_{pll}` the synchronizing frequency estimated by the PLL
    strategy (read host-mediated via ``host.pll_frequency``). The filtered
    active power obeys :math:`\dot{\tilde{p}}_c = \omega_f ( p_c - \tilde{p}_c )`,
    written by the host converter; :math:`\omega_{ref}` is the reference
    frequency selected by ``omega_mode``.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``Kp``", ":math:`R_c^{p}`", "P-f droop coefficient", "0.02"
       "``Pc_tilde``", ":math:`\tilde{p}_c`", "filtered active power (state) [p.u.]", ""
       "``delta_c``", ":math:`\delta_c`", "converter-frame angle relative to the network (state) [rad]", ""
       "``Pref``", ":math:`p_c^{*}`", "active-power setpoint (set to :math:`p_c` by the initialization)", ""
    """

    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b):
        omega_pll = host.pll_frequency(dae)
        omega_c = omega_pll + host.Kp * (host.Pref - dae.x[host.Pc_tilde])
        delta_omega_c = omega_c - omega_ref_vec
        dae.f[host.delta_c] = omega_b * delta_omega_c
        return omega_c


ANGLE_REGISTRY: Dict[str, type] = {
    "Droop": DroopAngle,
    "PLL": PLLAngle,
}
