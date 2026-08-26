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

r"""Turbine-governor strategies for synchronous machines.

A governor is selected on the machine line of a system file, e.g.
``governor = "TGOV1"``; the names accepted at any moment are returned by
``hermess.registered("governor")``. Every model below documents its
differential (and, where applicable, algebraic) equations and a table mapping
the code parameter names to the mathematical symbols used in those equations.

Common to all models: :math:`\omega` is the machine's absolute per-unit rotor
speed (1.0 at synchronism), :math:`\omega_{net} = 1` p.u. the nominal speed,
:math:`P_{ref}` the mechanical-power setpoint computed by the initialization,
and :math:`p_m` the mechanical power consumed by the machine's swing equation.
"""

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
    r"""TGOV1 steam turbine-governor: droop-controlled valve and steam-chest
    lag (P. W. Sauer and M. A. Pai, *Power System Dynamics and Stability*,
    p. 100). The framework default.

    Selected on a machine line with ``governor = "TGOV1"``.

    **Model.**

    .. math::

       T_{sv} \, \dot{p}_{sv} &= -p_{sv} + P_{ref}
           - \frac{\omega - \omega_{net}}{R_d} \\
       T_{ch} \, \dot{p}_m &= p_{sv} - p_m

    with :math:`\omega` the absolute per-unit rotor speed and
    :math:`\omega_{net} = 1` p.u., so that :math:`p_{sv} = p_m = P_{ref}` at
    steady state. With ``incl_lim`` the valve equation is multiplied by the
    anti-windup switch that freezes the valve at :math:`p_{sv}^{max,min}`.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``Rd``", ":math:`R_d`", "speed droop constant", "0.05"
       "``Tch``", ":math:`T_{ch}`", "steam chest time constant [s]", "0.05"
       "``Tsv``", ":math:`T_{sv}`", "steam valve time constant [s]", "1.5"
       "``psv_max`` / ``psv_min``", ":math:`p_{sv}^{max,min}`", "valve limits (with ``incl_lim``)", "10 / -10"
       "``psv``", ":math:`p_{sv}`", "steam valve position (state) [p.u.]", ""
       "``pm``", ":math:`p_m`", "mechanical power (state) [p.u.]", ""
       "``Pref``", ":math:`P_{ref}`", "mechanical-power setpoint (set by the initialization)", ""
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
    r"""Pure speed-droop governor: primary frequency response with no turbine
    lag dynamics, the :math:`T_{ch}, T_{sv} \to 0` limit of :class:`TGOV1`.

    Selected on a machine line with ``governor = "Droop"``.

    **Model.** The mechanical power follows the speed deviation
    instantaneously and is therefore a device-private algebraic variable
    (no states):

    .. math::

       0 = -p_m + P_{ref} - \frac{\omega - \omega_{net}}{R_d}

    with :math:`\omega` the absolute per-unit rotor speed and
    :math:`\omega_{net} = 1` p.u., so that :math:`p_m = P_{ref}` at steady
    state. ``pm`` rides the device-private-algebraic mechanism and the swing
    equation reads it through ``Synchronous.var_sym('pm')``.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``Rd``", ":math:`R_d`", "speed droop constant", "0.05"
       "``pm``", ":math:`p_m`", "mechanical power (private algebraic) [p.u.]", ""
       "``Pref``", ":math:`P_{ref}`", "mechanical-power setpoint (set by the initialization)", ""
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
    r"""Constant mechanical power: no turbine or governor dynamics, the
    zero-response limit of :class:`Droop` (:math:`R_d \to \infty`).

    Selected on a machine line with ``governor = "GOVCONST"``.

    **Model.**

    .. math::

       0 = -p_m + P_{ref}

    Used by benchmarks that deliberately exclude prime-mover dynamics, such as
    the 14-generator South East Australian system (Gibbard and Vowles 2014),
    whose small- and large-signal models have no turbine or governor
    representation.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``pm``", ":math:`p_m`", "mechanical power (private algebraic) [p.u.]", ""
       "``Pref``", ":math:`P_{ref}`", "mechanical-power setpoint (set by the initialization)", ""
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


class TGTypeII(Governor):
    r"""Type II speed governor: a droop on the frequency deviation through
    one lead-lag, added to the constant reference power (F. Milano, *Power
    System Modelling and Scripting*, 2010; the PSID ``TGTypeII``).

    Selected on a machine line with ``governor = "TGTypeII"``.

    **Model.** The lead-lag is realized as one lag state plus feedthrough,
    so the mechanical power is a device-private algebraic:

    .. math::

       u &= \frac{1}{R_d} \left( \omega_{net} - \omega \right) \\
       T_2 \, \dot{x}_g &= u - x_g \\
       0 &= -p_m + \frac{T_1}{T_2} \left( u - x_g \right) + x_g + P_{ref}

    with :math:`\omega` the absolute per-unit rotor speed. At steady state
    :math:`x_g = u = 0` and :math:`p_m = P_{ref}`. Like the PSID reference
    (which publishes this output as the mechanical torque without a
    :math:`1/\omega` factor), the output feeds the swing equation unmodified.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``Rd``", ":math:`R_d`", "speed droop constant", "0.05"
       "``T1``", ":math:`T_1`", "lead (transient droop) time constant [s]", "1"
       "``T2``", ":math:`T_2`", "lag time constant [s]", "2"
       "``xg``", ":math:`x_g`", "lead-lag lag state [p.u.]", ""
       "``pm``", ":math:`p_m`", "mechanical power (private algebraic) [p.u.]", ""
       "``Pref``", ":math:`P_{ref}`", "mechanical-power setpoint (set by the initialization)", ""
    """

    def states(self) -> List[str]:
        return ["xg"]

    def units(self) -> List[str]:
        return ["p.u."]

    def algebs(self) -> List[str]:
        return ["pm"]  # direct feedthrough of the speed deviation

    def algebs_units(self) -> Dict[str, str]:
        return {"pm": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"pm": 0.5}

    def params(self) -> Dict[str, float]:
        return {"Rd": 0.05, "T1": 1.0, "T2": 2.0}

    def x0(self) -> Dict[str, float]:
        return {"xg": 0.0}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Rd": "droop constant",
            "T1": "lead (transient droop) time constant",
            "T2": "lag time constant",
            "xg": "lead-lag lag state",
            "pm": "mechanical power (lead-lag output plus reference)",
            "Pref": "generator mechanical power set point",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Pref": 0.1}

    def fgcall(self, host, dae: Dae) -> None:
        u = (dae.omega_net - dae.x[host.omega]) / host.Rd
        dae.f[host.xg] = (u - dae.x[host.xg]) / host.T2
        dae.g[host.pm] = (
            -dae.y[host.pm]
            + host.T1 / host.T2 * (u - dae.x[host.xg])
            + dae.x[host.xg]
            + host.Pref
        )


GOVERNOR_REGISTRY: Dict[str, type] = {
    "TGOV1": TGOV1,
    "Droop": Droop,
    "GOVCONST": GOVCONST,
    "TGTypeII": TGTypeII,
}
