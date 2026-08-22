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

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from hermess.system import Dae


class Governor(ABC):
    """Abstract base class for turbine-governor models (pluggable strategy).

    Every governor must expose 'pm' -- the mechanical-power coupling variable
    consumed by the synchronous machine's swing equation. 'pm' may be declared
    either as a differential ``state`` (when the turbine has lag dynamics, e.g.
    TGOV1) or as a device-private ``algeb`` (when mechanical power is an
    instantaneous / algebraic function of the inputs, e.g. a pure-droop or
    constant-power model). The host resolves 'pm' wherever it lives via
    ``Synchronous.var_sym`` -- the swing equation is agnostic to the choice.

    Symmetric to :class:`~hermess.devices.avr.AVR`: the governor does
    NOT own state arrays or DAE indices. It declares what states, private
    algebraics, parameters, noise values, etc. it needs, and the host Synchronous
    machine registers them on itself. It reads the machine's **absolute** per-unit
    speed via ``host.omega`` (1.0 at synchronism, NOT the deviation) and its
    setpoint via ``host.Pref``.
    """

    @abstractmethod
    def states(self) -> List[str]:
        """Return ordered list of differential-state names."""
        ...

    def algebs(self) -> List[str]:
        """Return ordered list of device-private *algebraic* variable names.

        Default empty: most governors have turbine lag dynamics whose output
        'pm' is a state. A governor whose mechanical power is an instantaneous
        function of its inputs returns ['pm'] here instead of listing it in
        :meth:`states`, and writes its defining residual ``0 = -pm + <expr>``
        into ``dae.g`` in :meth:`fgcall`.
        """
        return []

    def algebs_units(self) -> Dict[str, str]:
        """Units for each private algebraic (mirrors :meth:`units`)."""
        return {}

    def algebs_x0(self) -> Dict[str, float]:
        """Initial guess for each private algebraic (Newton guess in finit)."""
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
    def setpoints(self) -> Dict[str, float]:
        """Return setpoint names -> defaults (e.g., Pref)."""
        ...

    @abstractmethod
    def fgcall(self, host, dae: Dae) -> None:
        """Write the governor's differential equations into ``dae.f`` and, if it
        declares private algebraics, their defining residuals into ``dae.g``.

        Args:
            host: The Synchronous machine instance. Access state/algebraic
                  indices via host.psv, host.pm, etc., parameters via host.Rd,
                  host.Tch, ..., the absolute per-unit speed via host.omega and
                  the setpoint via host.Pref.
            dae: The DAE system object.
        """
        ...


class TGOV1(Governor):
    """TGOV1 turbine-governor model as presented in Power System Dynamics and
    Stability by P.W. Sauer and M.A. Pai, 2006. (page 100)

    States: psv (steam valve position), pm (mechanical power). 'pm' is the
    coupling output to the swing equation. This is the framework default.

    The droop acts on the speed deviation ``omega - omega_net`` (omega_net = 1
    p.u.); ``host.omega`` is the ABSOLUTE per-unit speed. ``Pref`` is the
    mechanical-power setpoint, so ``psv = pm = Pref`` at steady state.
    """

    def states(self) -> List[str]:
        return ["psv", "pm"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "Rd": 0.05,
            "Tch": 0.05,
            "Tsv": 1.5,
            "psv_min": -10,
            "psv_max": 10,
        }

    def x0(self) -> Dict[str, float]:
        return {"psv": 0.5, "pm": 0.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Rd": "droop constant",
            "Tch": "steam chest time constant",
            "Tsv": "steam valve time constant",
            "psv": "steam valve position",
            "pm": "mechanical power",
            "Pref": "generator mechanical power set point",
            "psv_min": "Governor minimal set point",
            "psv_max": "Governor maximal set point",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Pref": 0.1}

    def fgcall(self, host, dae: Dae) -> None:
        # host.omega is the ABSOLUTE per-unit speed (1.0 at synchronism); the
        # droop acts on the deviation from nominal, omega - omega_net (= omega-1),
        # so at steady state psv = pm = Pref (Pref is the mechanical-power setpoint).
        dae.f[host.pm] = 1 / host.Tch * (dae.x[host.psv] - dae.x[host.pm])
        dae.f[host.psv] = (
            dae.s[host.psv]
            * 1
            / host.Tsv
            * (
                -(dae.x[host.omega] - dae.omega_net) / host.Rd
                - dae.x[host.psv]
                + host.Pref
            )
        )


class Droop(Governor):
    r"""Pure speed-droop governor with the mechanical power 'pm' declared as a
    device-private ALGEBRAIC variable.

    Primary frequency response without turbine lag dynamics: the mechanical power
    follows the speed deviation instantaneously (omega is the ABSOLUTE per-unit
    speed; the droop acts on omega - omega_net with omega_net = 1 p.u.),

        0 = -pm + Pref - (omega - omega_net) / Rd     # pm algebraic (no states)

    so at steady state pm = Pref. This is the ``Tch, Tsv -> 0`` (quasi-steady-state)
    limit of :class:`TGOV1`: at ``Tsv -> 0`` the valve gives
    ``psv = Pref - (omega-omega_net)/Rd`` and at ``Tch -> 0`` the chest gives
    ``pm = psv``. 'pm' rides the device-private-algebraic mechanism and the swing
    equation reads it through ``Synchronous.var_sym('pm')``, as for a state-valued
    'pm'.
    """

    def states(self) -> List[str]:
        return []

    def units(self) -> List[str]:
        return []

    def algebs(self) -> List[str]:
        return ["pm"]  # mechanical power = instantaneous droop output

    def algebs_units(self) -> Dict[str, str]:
        return {"pm": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"pm": 0.5}

    def params(self) -> Dict[str, float]:
        return {"Rd": 0.05}

    def x0(self) -> Dict[str, float]:
        return {}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Rd": "droop constant",
            "pm": "mechanical power (algebraic droop output)",
            "Pref": "generator mechanical power set point",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Pref": 0.1}

    def fgcall(self, host, dae: Dae) -> None:
        # Mechanical power: algebraic droop output (residual 0 = -pm + <expr>,
        # matching the device-private mechanism). host.omega is the ABSOLUTE
        # per-unit speed, so the droop acts on the deviation omega - omega_net
        # (= omega - 1); at steady state pm = Pref.
        dae.g[host.pm] = (
            -dae.y[host.pm]
            + host.Pref
            - (dae.x[host.omega] - dae.omega_net) / host.Rd
        )


class GOVCONST(Governor):
    r"""Constant mechanical power (no turbine/governor dynamics).

    The mechanical power is pinned to the finit-solved setpoint,

        0 = -pm + Pref ,

    i.e. the zero-response limit of :class:`Droop` (Rd → ∞). Used by models
    that deliberately exclude prime-mover dynamics, such as the 14-generator
    South East Australian benchmark (Gibbard & Vowles 2014), whose small- and
    large-signal models have no turbine/governor representation.
    """

    def states(self) -> List[str]:
        return []

    def units(self) -> List[str]:
        return []

    def algebs(self) -> List[str]:
        return ["pm"]

    def algebs_units(self) -> Dict[str, str]:
        return {"pm": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"pm": 0.5}

    def params(self) -> Dict[str, float]:
        return {}

    def x0(self) -> Dict[str, float]:
        return {}

    def descriptions(self) -> Dict[str, str]:
        return {
            "pm": "mechanical power (constant)",
            "Pref": "generator mechanical power set point",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Pref": 0.1}

    def fgcall(self, host, dae: Dae) -> None:
        dae.g[host.pm] = -dae.y[host.pm] + host.Pref


GOVERNOR_REGISTRY: Dict[str, type] = {
    "TGOV1": TGOV1,
    "Droop": Droop,
    "GOVCONST": GOVCONST,
}
