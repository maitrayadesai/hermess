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

"""Inverter inner-control strategies (the cascaded voltage/current loops).

The inner controller is the converter's fast actuator: it regulates the capacitor
voltage to the reference ``Vcd`` from the outer voltage loop and produces the
switching voltage ``Vsw`` that drives the filter. It is a single strategy axis,
swapped as a whole unit (cascaded PI + virtual impedance) rather than block-by-
block.

It owns the four PI integrator states (``xi_d``/``xi_q`` voltage loop,
``gamma_d``/``gamma_q`` current loop) and the controller / virtual-impedance gains.
It reads the filter capacitance/inductance (``host.Cf`` / ``host.Lf``) via the
host for the cross-coupling decoupling terms.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Set

import casadi as ca
import numpy as np

if TYPE_CHECKING:
    from hermess.system import Dae


class InnerControl(ABC):
    """Abstract base class for inverter inner-control strategies.

    :meth:`fgcall` consumes the converter-frame internal quantities (from the
    host's Park transforms), the converter frequency ``omega_c`` and the voltage
    reference ``Vcd``, writes its PI integrator state equations into ``dae.f``, and
    returns the switching voltage ``(Vswd, Vswq)`` in the network frame (consumed
    by the filter strategy).
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
    def fgcall(self, host, dae: Dae, internals, omega_c, delta_c):
        """Run the inner control. ``internals`` is a dict of the converter-frame
        quantities {"Vfd","Vfq","itd","itq","ifd","ifq"}; the voltage command is read
        via ``host.voltage_command(dae)``. Publishes the switching voltage on
        ``host.Vswd``/``host.Vswq`` (read by the filter via
        ``host.switching_voltage(dae)``) and the current references on
        ``host.ifd_ref``/``host.ifq_ref`` (via ``host.current_ref(dae)``); writes the
        integrator state equations into ``dae.f``."""
        ...

    def requires(self) -> Set[str]:
        """Plant capability tags this controller needs from the filter (checked at
        construction, warning on mismatch). Empty by default."""
        return set()

    def finit_sequential(self, host, dae: Dae, filt, omega_c) -> Dict[str, np.ndarray]:
        """Steady-state init of the control loop. ``filt`` is the filter strategy's
        init dict (op-point + Vsw); ``omega_c`` is the synchronizing frequency from
        the angle source. Returns the integrator states plus the frame angle
        ``delta_c`` and the voltage command ``Vcd`` -- handed by the host to the
        angle (the delta_c slot) and the voltage controller (which unpacks Vcd)."""
        raise NotImplementedError(
            f"{type(self).__name__} provides no sequential inner-control init; "
            f"implement finit_sequential() or set _init_method='joint' on the device."
        )


class Cascaded(InnerControl):
    """Cascaded voltage + current PI control with virtual impedance.

    Voltage loop (xi): regulates the capacitor voltage to ``Vcd`` (minus the
    virtual-impedance drop), producing the filter-current reference. Current loop
    (gamma): regulates the filter current, producing the switching voltage. With
    the cross-coupling decoupling and feed-forward terms.
    """

    def states(self) -> List[str]:
        return ["xi_d", "xi_q", "gamma_d", "gamma_q"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u.", "p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "Kpv": 0.59,
            "Kiv": 736,
            "Kffv": 0,
            "Kpc": 1.27,
            "Kic": 14.3,
            "Kffc": 0,
            "Rv": 0,
            "Lv": 0.2,
        }

    def x0(self) -> Dict[str, float]:
        return {"xi_d": 0, "xi_q": 0, "gamma_d": 0, "gamma_q": 0}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Kpv": "Proportional gain for voltage controller",
            "Kiv": "Integral gain for voltage controller",
            "Kffv": "Feed-forward gain of voltage controller",
            "Kpc": "Proportional gain for current controller",
            "Kic": "Integral gain for current controller",
            "Kffc": "Feed-forward gain of current controller",
            "Rv": "Virtual impedance resistance",
            "Lv": "Virtual impedance inductance",
            "xi_d": "Integrator state of the d-component of the internal voltage",
            "xi_q": "Integrator state of the q-component of the internal voltage",
            "gamma_d": "Integrator state of the d-component of the internal current",
            "gamma_q": "Integrator state of the q-component of the internal current",
        }

    def fgcall(self, host, dae: Dae, internals, omega_c, delta_c):
        Vfd_int = internals["Vfd"]
        Vfq_int = internals["Vfq"]
        itd_int = internals["itd"]
        itq_int = internals["itq"]
        ifd_int = internals["ifd"]
        ifq_int = internals["ifq"]

        # Voltage-magnitude command from the outer loop, host-mediated.
        Vcd = host.voltage_command(dae)

        # Voltage controller references (with virtual impedance drop).
        Vfd_ref = Vcd - host.Rv * itd_int + omega_c * host.Lv * itq_int
        Vfq_ref = -host.Rv * itq_int - omega_c * host.Lv * itd_int

        # Current controller references (voltage PI + decoupling + feed-forward).
        ifd_ref = (
            host.Kpv * (Vfd_ref - Vfd_int)
            + host.Kiv * dae.x[host.xi_d]
            - omega_c * host.Cf * Vfq_int
            + host.Kffv * itd_int
        )
        ifq_ref = (
            host.Kpv * (Vfq_ref - Vfq_int)
            + host.Kiv * dae.x[host.xi_q]
            + omega_c * host.Cf * Vfd_int
            + host.Kffv * itq_int
        )

        # Publish the current references and read them back through the host
        # accessor (the interception seam for a future current limiter, which would
        # make host.current_ref a saturated algebraic). With no limiter the
        # accessor returns these same expressions.
        host.ifd_ref, host.ifq_ref = ifd_ref, ifq_ref
        ifd_ref, ifq_ref = host.current_ref(dae)

        # Switching-voltage references (current PI + decoupling + feed-forward).
        Vswd_ref = (
            host.Kpc * (ifd_ref - ifd_int)
            + host.Kic * dae.x[host.gamma_d]
            - omega_c * host.Lf * ifq_int
            + host.Kffc * Vfd_int
        )
        Vswq_ref = (
            host.Kpc * (ifq_ref - ifq_int)
            + host.Kic * dae.x[host.gamma_q]
            + omega_c * host.Lf * ifd_int
            + host.Kffc * Vfq_int
        )

        # Rotate the switching voltage back to the network (external) frame and
        # publish it on the host (read by the filter via host.switching_voltage).
        host.Vswd, host.Vswq = host.to_external(Vswd_ref, Vswq_ref, delta_c)

        # PI integrator dynamics.
        dae.f[host.xi_d] = Vfd_ref - Vfd_int
        dae.f[host.xi_q] = Vfq_ref - Vfq_int
        dae.f[host.gamma_d] = ifd_ref - ifd_int
        dae.f[host.gamma_q] = ifq_ref - ifq_int

    def requires(self) -> Set[str]:
        # The cascaded voltage loop regulates the capacitor voltage and feeds Cf
        # forward, so it presupposes a shunt-capacitor (LC/LCL) plant.
        return {"shunt_capacitor"}

    def finit_sequential(self, host, dae: Dae, filt, omega_c) -> Dict[str, np.ndarray]:
        """Steady-state of the cascaded control ladder. Solves the 6 conditions
        (the four PI integrators steady + the two switching-voltage matches) for
        the frame angle ``delta_c``, the voltage command ``Vcd`` and the four
        integrators. ``Pc_tilde/Qc_tilde`` are not solved here: they are the
        frame-invariant powers, computed by the host from the filter op-point."""
        n = host.n
        n_unknowns = 6

        delta_c = ca.SX.sym("delta_c", n)
        Vcd = ca.SX.sym("Vcd", n)
        xi_d = ca.SX.sym("xi_d", n)
        xi_q = ca.SX.sym("xi_q", n)
        gamma_d = ca.SX.sym("gamma_d", n)
        gamma_q = ca.SX.sym("gamma_q", n)

        Vfd_ext, Vfq_ext = filt["Vfd_ext"], filt["Vfq_ext"]
        ifd_ext, ifq_ext = filt["ifd_ext"], filt["ifq_ext"]
        itd_ext, itq_ext = filt["itd_ext"], filt["itq_ext"]
        Vswd, Vswq = filt["Vswd"], filt["Vswq"]

        itd_int, itq_int = host.to_internal(itd_ext, itq_ext, delta_c)
        ifd_int, ifq_int = host.to_internal(ifd_ext, ifq_ext, delta_c)
        Vfd_int, Vfq_int = host.to_internal(Vfd_ext, Vfq_ext, delta_c)
        Vswd_int, Vswq_int = host.to_internal(Vswd, Vswq, delta_c)

        Vfd_ref = Vcd - host.Rv * itd_int + omega_c * host.Lv * itq_int
        Vfq_ref = -host.Rv * itq_int - omega_c * host.Lv * itd_int

        ifd_ref = (
            host.Kpv * (Vfd_ref - Vfd_int)
            + host.Kiv * xi_d
            - omega_c * host.Cf * Vfq_int
            + host.Kffv * itd_int
        )
        ifq_ref = (
            host.Kpv * (Vfq_ref - Vfq_int)
            + host.Kiv * xi_q
            + omega_c * host.Cf * Vfd_int
            + host.Kffv * itq_int
        )

        Vswd_ref = (
            host.Kpc * (ifd_ref - ifd_int)
            + host.Kic * gamma_d
            - omega_c * host.Lf * ifq_int
            + host.Kffc * Vfd_int
        )
        Vswq_ref = (
            host.Kpc * (ifq_ref - ifq_int)
            + host.Kic * gamma_q
            + omega_c * host.Lf * ifd_int
            + host.Kffc * Vfq_int
        )

        outputs = ca.SX(np.zeros(n_unknowns * n))
        outputs[0:n] = Vfd_ref - Vfd_int
        outputs[n : 2 * n] = Vfq_ref - Vfq_int
        outputs[2 * n : 3 * n] = ifd_ref - ifd_int
        outputs[3 * n : 4 * n] = ifq_ref - ifq_int
        outputs[4 * n : 5 * n] = Vswd_ref - Vswd_int
        outputs[5 * n : 6 * n] = Vswq_ref - Vswq_int

        h = ca.Function(
            "h",
            [ca.vertcat(delta_c, Vcd, xi_d, xi_q, gamma_d, gamma_q)],
            [ca.vertcat(outputs)],
        )
        G = ca.rootfinder("G", "newton", h)
        sol = np.array(G(ca.vertcat(np.zeros(n_unknowns * n)))).flatten()

        return {
            "delta_c": sol[0:n],
            "Vcd": sol[n : 2 * n],
            "xi_d": sol[2 * n : 3 * n],
            "xi_q": sol[3 * n : 4 * n],
            "gamma_d": sol[4 * n : 5 * n],
            "gamma_q": sol[5 * n : 6 * n],
        }


INNER_REGISTRY: Dict[str, type] = {
    "Cascaded": Cascaded,
}
