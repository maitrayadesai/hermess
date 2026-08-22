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

"""Inverter output-filter (electrical-plant) strategies.

The filter owns the converter's network-interface states and writes their
dynamics, driven by the switching voltage ``Vsw`` from the inner controller and
the network voltage. It is the inverter analogue of the synchronous machine's
electromagnetic model (the electrical plant the controllers act on), here as a
pluggable strategy that combines freely with any angle / voltage / inner / pll
choice.

A filter exposes the terminal-current states (``itd_ext`` / ``itq_ext``, read by
the host's network injection ``gcall``) and the capacitor-voltage / filter-current
states that the control ladder reads through ``host.var_sym`` -- which lets a
quasi-static realization (``LCL_static``) make them algebraic transparently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Set

import casadi as ca
import numpy as np

if TYPE_CHECKING:
    from hermess.system import Dae


class Filter(ABC):
    """Abstract base class for inverter output-filter models (pluggable strategy).

    Like the synchronous-machine strategies (AVR/governor/...), the filter does
    not own state arrays or DAE indices. It declares the states, private
    algebraics and parameters it needs, and the host ``Inverter`` registers them
    on itself (filter first, so its states occupy the leading block of the state
    vector). It reads host parameters/states by attribute (``host.Lf``,
    ``host.var_sym(dae, "Vfd_ext")``, ...).
    """

    @abstractmethod
    def states(self) -> List[str]:
        """Return ordered list of differential-state names."""
        ...

    def algebs(self) -> List[str]:
        """Return ordered list of device-private *algebraic* variable names.

        Default empty (dynamic filter: every quantity is a differential state). A
        quasi-static realization returns its quantities here instead and writes
        ``0 = RHS`` residuals into ``dae.g``."""
        return []

    def algebs_units(self) -> Dict[str, str]:
        return {}

    def algebs_x0(self) -> Dict[str, float]:
        return {}

    @abstractmethod
    def units(self) -> List[str]:
        """Return units for each state, same length as states()."""
        ...

    @abstractmethod
    def params(self) -> Dict[str, float]:
        """Return dict of parameter names -> default values."""
        ...

    @abstractmethod
    def x0(self) -> Dict[str, float]:
        """Return default initial guess for each state."""
        ...

    @abstractmethod
    def descriptions(self) -> Dict[str, str]:
        """Return descriptions for states and params."""
        ...

    @abstractmethod
    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b) -> None:
        """Write the filter dynamics into ``dae.f`` (and, for a quasi-static
        realization, the residuals into ``dae.g``). The driving switching voltage
        (converter output, network frame) is read host-mediated via
        ``host.switching_voltage(dae)``.

        Args:
            host: the Inverter instance (read params via host.Lf/..., states via
                host.var_sym(dae, name), the switching voltage via
                host.switching_voltage(dae), indices via host.Vfd_ext, host.vre, ...).
            dae: the DAE system object.
            omega_ref_vec: per-bus reference-frame frequency.
            omega_b: base speed (2*pi*fn) per device.
        """
        ...

    def provides(self) -> Set[str]:
        """Plant capability tags this filter exposes (e.g. ``"shunt_capacitor"``),
        checked against the inner controller's requirements at construction. Empty
        by default."""
        return set()

    def finit_sequential(self, host, dae: Dae) -> Dict[str, np.ndarray]:
        """Steady-state init of the filter from the power-flow terminal point.
        Returns a dict with the filter states plus the switching voltage
        ``Vswd/Vswq`` and terminal current ``itd_ext/itq_ext`` consumed downstream.
        The base raises: a filter without a sequential init is only usable with the
        joint init."""
        raise NotImplementedError(
            f"{type(self).__name__} provides no sequential filter init; implement "
            f"finit_sequential() or set _init_method='joint' on the device."
        )


class LCL(Filter):
    """Dynamic LCL output filter (the framework default), with all quantities as
    differential states.

    Capacitor voltage (Vfd_ext/Vfq_ext), converter-side filter current
    (ifd_ext/ifq_ext) and grid-side / terminal current (itd_ext/itq_ext), all in
    the network (external) dq frame, with the classic series-Rf-Lf / shunt-Cf /
    series-Rt-Lt topology.
    """

    def states(self) -> List[str]:
        return [
            "Vfd_ext",
            "Vfq_ext",
            "ifd_ext",
            "ifq_ext",
            "itd_ext",
            "itq_ext",
        ]

    def units(self) -> List[str]:
        return ["p.u.", "p.u.", "p.u.", "p.u.", "p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "Rf": 0.0001,
            "Lf": 0.08,
            "Cf": 0.074,
            "Rt": 0.01,
            "Lt": 0.2,
        }

    def x0(self) -> Dict[str, float]:
        return {
            "Vfd_ext": 1.0,
            "Vfq_ext": 0,
            "ifd_ext": 0.1,
            "ifq_ext": 0,
            "itd_ext": 0,
            "itq_ext": 0,
        }

    def descriptions(self) -> Dict[str, str]:
        return {
            "Rf": "Filter resistance",
            "Lf": "Filter reactance",
            "Cf": "Filter capacitance",
            "Rt": "Resistance of the line connecting the external end of the filter to the terminal (i.e. grid)",
            "Lt": "Reactance of the line connecting the external end of the filter to the terminal (i.e. grid)",
            "Vfd_ext": "d-component of external filter voltage",
            "Vfq_ext": "q-component of external filter voltage",
            "ifd_ext": "d-component of external filter current",
            "ifq_ext": "q-component of external filter current",
            "itd_ext": "d-component of external terminal current",
            "itq_ext": "q-component of external terminal current",
        }

    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b) -> None:
        vn = dae.y
        Vswd, Vswq = host.switching_voltage(dae)

        Vfd_ext_s = host.var_sym(dae, "Vfd_ext")
        Vfq_ext_s = host.var_sym(dae, "Vfq_ext")
        ifd_ext_s = host.var_sym(dae, "ifd_ext")
        ifq_ext_s = host.var_sym(dae, "ifq_ext")
        itd_ext_s = host.var_sym(dae, "itd_ext")
        itq_ext_s = host.var_sym(dae, "itq_ext")

        dae.f[host.Vfd_ext] = (
            omega_b / host.Cf * (ifd_ext_s - itd_ext_s)
            + omega_ref_vec * omega_b * Vfq_ext_s
        )
        dae.f[host.Vfq_ext] = (
            omega_b / host.Cf * (ifq_ext_s - itq_ext_s)
            - omega_ref_vec * omega_b * Vfd_ext_s
        )

        dae.f[host.ifd_ext] = (
            omega_b / host.Lf * (Vswd - Vfd_ext_s)
            - omega_b * host.Rf / host.Lf * ifd_ext_s
            + omega_ref_vec * omega_b * ifq_ext_s
        )
        dae.f[host.ifq_ext] = (
            omega_b / host.Lf * (Vswq - Vfq_ext_s)
            - omega_b * host.Rf / host.Lf * ifq_ext_s
            - omega_ref_vec * omega_b * ifd_ext_s
        )

        dae.f[host.itd_ext] = (
            omega_b / host.Lt * (Vfd_ext_s - vn[host.vre])
            - omega_b * host.Rt / host.Lt * itd_ext_s
            + omega_ref_vec * omega_b * itq_ext_s
        )
        dae.f[host.itq_ext] = (
            omega_b / host.Lt * (Vfq_ext_s - vn[host.vim])
            - omega_b * host.Rt / host.Lt * itq_ext_s
            - omega_ref_vec * omega_b * itd_ext_s
        )

    def provides(self) -> Set[str]:
        # The LC(L) topology has a shunt capacitor whose voltage the cascaded inner
        # controller regulates (feeding Cf forward).
        return {"shunt_capacitor"}

    def finit_sequential(self, host, dae: Dae) -> Dict[str, np.ndarray]:
        """Steady-state init of the LCL filter (decoupled from the controls): given
        the power-flow terminal voltage (vre/vim) and current (itd_ext/itq_ext),
        solve the 6 filter ODEs = 0 for the capacitor voltage, filter current, and
        the switching voltage Vsw the converter must output."""
        n = host.n
        n_unknowns = 6

        Vswd = ca.SX.sym("Vswd", n)
        Vswq = ca.SX.sym("Vswq", n)
        ifd_ext = ca.SX.sym("ifd_ext", n)
        ifq_ext = ca.SX.sym("ifq_ext", n)
        Vfd_ext = ca.SX.sym("Vfd_ext", n)
        Vfq_ext = ca.SX.sym("Vfq_ext", n)

        inputs = [ca.vertcat(Vswd, Vswq, ifd_ext, ifq_ext, Vfd_ext, Vfq_ext)]
        outputs = ca.SX(np.zeros(n_unknowns * n))

        omega_b = [2 * np.pi * dae.fn] * n
        omega_net_vec = dae.omega_net * np.ones(n)  # nominal during init

        itd_ext = dae.Sb / host.Sn * dae.iinit[host.vre]
        itq_ext = dae.Sb / host.Sn * dae.iinit[host.vim]
        vre = dae.yinit[host.vre]
        vim = dae.yinit[host.vim]

        outputs[0:n] = (
            omega_b / host.Lf * (Vswd - Vfd_ext)
            - omega_b * host.Rf / host.Lf * ifd_ext
            + omega_net_vec * omega_b * ifq_ext
        )
        outputs[n : 2 * n] = (
            omega_b / host.Lf * (Vswq - Vfq_ext)
            - omega_b * host.Rf / host.Lf * ifq_ext
            - omega_net_vec * omega_b * ifd_ext
        )
        outputs[2 * n : 3 * n] = (
            omega_b / host.Cf * (ifd_ext - itd_ext) + omega_net_vec * omega_b * Vfq_ext
        )
        outputs[3 * n : 4 * n] = (
            omega_b / host.Cf * (ifq_ext - itq_ext) - omega_net_vec * omega_b * Vfd_ext
        )
        outputs[4 * n : 5 * n] = (
            omega_b / host.Lt * (Vfd_ext - vre)
            - omega_b * host.Rt / host.Lt * itd_ext
            + omega_net_vec * omega_b * itq_ext
        )
        outputs[5 * n : 6 * n] = (
            omega_b / host.Lt * (Vfq_ext - vim)
            - omega_b * host.Rt / host.Lt * itq_ext
            - omega_net_vec * omega_b * itd_ext
        )

        h = ca.Function("h", inputs, [ca.vertcat(outputs)])
        G = ca.rootfinder("G", "newton", h)
        sol = np.array(G(ca.vertcat(np.zeros(n_unknowns * n)))).flatten()

        return {
            "Vswd": sol[0:n],
            "Vswq": sol[n : 2 * n],
            "ifd_ext": sol[2 * n : 3 * n],
            "ifq_ext": sol[3 * n : 4 * n],
            "Vfd_ext": sol[4 * n : 5 * n],
            "Vfq_ext": sol[5 * n : 6 * n],
            "itd_ext": itd_ext,
            "itq_ext": itq_ext,
        }


class LCL_static(LCL):
    """Quasi-static LCL filter: same topology as :class:`LCL`, but the six filter
    quantities are device-private algebraic variables instead of differential
    states (the singular-perturbation reduction zeroing the fast LCL dynamics,
    ``d/dt -> 0``). Appropriate when the network itself is quasi-static
    (``line_dyn=False``); a dynamic filter on a static network is physically
    incoherent (the host warns but allows it).

    The ``2*pi*f`` (``omega_b``) factor common to every term of the dynamic ODE is
    dropped on the ``0 = RHS`` algebraic constraint: it is mathematically
    redundant and would inflate the finit Jacobian condition number.
    """

    # finit_sequential is inherited from LCL: the steady-state solve is identical
    # (these algebraic constraints are the dynamic filter's d/dt=0 equations, same
    # operating point). _load_finit routes the quantities to dae.yinit (they are in
    # _algebs_int) instead of dae.xinit, so both init methods are supported.

    def states(self) -> List[str]:
        return []

    def units(self) -> List[str]:
        return []

    def x0(self) -> Dict[str, float]:
        return {}

    def algebs(self) -> List[str]:
        return ["Vfd_ext", "Vfq_ext", "ifd_ext", "ifq_ext", "itd_ext", "itq_ext"]

    def algebs_units(self) -> Dict[str, str]:
        return {s: "p.u." for s in self.algebs()}

    def algebs_x0(self) -> Dict[str, float]:
        return {
            "Vfd_ext": 1.0,
            "Vfq_ext": 0,
            "ifd_ext": 0.1,
            "ifq_ext": 0,
            "itd_ext": 0,
            "itq_ext": 0,
        }

    def fgcall(self, host, dae: Dae, omega_ref_vec, omega_b) -> None:
        # Quasi-static LCL constraints: 0 = RHS, the dynamic equations with the
        # d/dt term zeroed and the common omega_b factor dropped. var_sym resolves
        # the filter quantities to dae.y (algebraic).
        vn = dae.y
        Vswd, Vswq = host.switching_voltage(dae)

        Vfd_ext_s = host.var_sym(dae, "Vfd_ext")
        Vfq_ext_s = host.var_sym(dae, "Vfq_ext")
        ifd_ext_s = host.var_sym(dae, "ifd_ext")
        ifq_ext_s = host.var_sym(dae, "ifq_ext")
        itd_ext_s = host.var_sym(dae, "itd_ext")
        itq_ext_s = host.var_sym(dae, "itq_ext")

        dae.g[host.Vfd_ext] = (
            1 / host.Cf * (ifd_ext_s - itd_ext_s) + omega_ref_vec * Vfq_ext_s
        )
        dae.g[host.Vfq_ext] = (
            1 / host.Cf * (ifq_ext_s - itq_ext_s) - omega_ref_vec * Vfd_ext_s
        )

        dae.g[host.ifd_ext] = (
            1 / host.Lf * (Vswd - Vfd_ext_s)
            - host.Rf / host.Lf * ifd_ext_s
            + omega_ref_vec * ifq_ext_s
        )
        dae.g[host.ifq_ext] = (
            1 / host.Lf * (Vswq - Vfq_ext_s)
            - host.Rf / host.Lf * ifq_ext_s
            - omega_ref_vec * ifd_ext_s
        )

        dae.g[host.itd_ext] = (
            1 / host.Lt * (Vfd_ext_s - vn[host.vre])
            - host.Rt / host.Lt * itd_ext_s
            + omega_ref_vec * itq_ext_s
        )
        dae.g[host.itq_ext] = (
            1 / host.Lt * (Vfq_ext_s - vn[host.vim])
            - host.Rt / host.Lt * itq_ext_s
            - omega_ref_vec * itd_ext_s
        )


FILTER_REGISTRY: Dict[str, type] = {
    "LCL": LCL,
    "LCL_static": LCL_static,
}
