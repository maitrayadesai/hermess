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

r"""Rotor-shaft (swing dynamics) strategies for synchronous machines.

A shaft is selected on the machine line of a system file, e.g.
``shaft = "Shaft4Mass"``; the names accepted at any moment are returned by
``hermess.registered("shaft")``. The shaft owns the rotor angle and speed
states and writes the swing equations; a multi-mass (torsional) shaft adds
further rotor masses while the generator mass keeps the canonical state names
``delta`` / ``omega``.

Common to all models: :math:`\omega_b = 2 \pi f_n` is the base angular
frequency, :math:`\omega_{ref}` the per-machine reference frequency (1 p.u.),
:math:`\omega` the absolute per-unit speed (1.0 at synchronism), :math:`p_m`
the governor's mechanical power and :math:`P_e` the electromagnetic air-gap
power.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List, Tuple
from abc import ABC, abstractmethod
import numpy as np

if TYPE_CHECKING:
    from hermess.system import Dae


class Shaft(ABC):
    """Abstract base class for the rotor-shaft mechanics (pluggable strategy).

    The shaft owns the rotor angle/speed states and writes the swing (rotor
    motion) equations. Every shaft must expose the **generator mass** as the two
    differential states ``delta`` (rotor angle wrt the synchronous frame) and
    ``omega`` (the ABSOLUTE per-unit speed, = 1.0 at synchronism, NOT the
    deviation). Those are the names the electromagnetic model, the network
    current injection (``gcall``), the governor, the PSS and the initialisation
    all read, so a multi-mass (torsional) shaft adds *further* rotor masses
    (``delta_<name>`` / ``omega_<name>``) while keeping the generator mass on the
    canonical names -- nothing downstream changes.

    Coupling ports the shaft consumes:

    * ``pm`` -- the governor's mechanical-power output, read via
      ``host.var_sym(dae, "pm")`` and distributed across the turbine masses;
    * ``Pe`` -- the electromagnetic air-gap power, passed into :meth:`fgcall` and
      applied to the generator mass only.

    It reads the per-machine reference-frame frequency via ``host._omega_ref(dae)``
    (= 1 p.u.).

    Symmetric to :class:`~hermess.devices.avr.AVR`,
    :class:`~hermess.devices.governor.Governor` and
    :class:`~hermess.devices.pss.PSS`: the shaft does NOT own state
    arrays or DAE indices. It declares what states / parameters / noise values it
    needs and the host :class:`Synchronous` machine registers them on itself.

    Rotor angles and speeds are inherently *differential* states, so -- unlike the
    AVR/governor/PSS -- a shaft declares no private algebraic variables.
    """

    @abstractmethod
    def states(self) -> List[str]:
        """Return ordered differential-state names. MUST contain 'delta' and
        'omega' (the generator mass)."""
        ...

    @abstractmethod
    def units(self) -> List[str]:
        """Return units for each state, same length as :meth:`states`."""
        ...

    @abstractmethod
    def params(self) -> Dict[str, float]:
        """Return dict of parameter names -> default values (empty for the
        single-mass shaft, which reuses the machine's own H, D, f)."""
        ...

    @abstractmethod
    def x0(self) -> Dict[str, float]:
        """Return default initial guess for each state."""
        ...

    @abstractmethod
    def descriptions(self) -> Dict[str, str]:
        """Return descriptions for states and params."""
        ...

    def setpoints(self) -> Dict[str, float]:
        """Return setpoint names -> defaults. The shaft mechanics have none."""
        return {}

    @abstractmethod
    def fgcall(self, host, dae: Dae, Pe) -> None:
        """Write the rotor-motion (swing) differential equations into ``dae.f``.

        Args:
            host: The Synchronous machine instance. Access state indices via
                  host.delta, host.omega (generator mass) and, for a multi-mass
                  shaft, host.delta_<name>/host.omega_<name>; inertia/damping via
                  host.H, host.D, host.f (generator mass) and host.H_<name>, ...;
                  the governor port via host.var_sym(dae, "pm") and the reference
                  frequency via host._omega_ref(dae).
            dae: The DAE system object.
            Pe: The electromagnetic air-gap power (CasADi SX, one entry per
                machine), applied to the generator mass.
        """
        ...


class SingleMass(Shaft):
    r"""Single rigid rotor mass: the classic swing equation. The framework
    default.

    Selected on a machine line with ``shaft = "SingleMass"``.

    **Model.**

    .. math::

       \dot{\delta} &= \omega_b \, (\omega - \omega_{ref}) \\
       2 H \, \dot{\omega} &= p_m - P_e
           - D \, (\omega - \omega_{ref}) - f \, \omega

    with :math:`\omega_b = 2 \pi f_n` the base angular frequency,
    :math:`\omega_{ref}` the per-machine reference frequency (1 p.u.),
    :math:`p_m` the governor's mechanical power and :math:`P_e` the
    electromagnetic air-gap power. The shaft reuses the machine's own inertia
    :math:`H`, damping :math:`D` and rotor friction :math:`f`, so it declares
    no parameters of its own.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``delta``", ":math:`\delta`", "rotor angle wrt the synchronous frame (state) [rad]", ""
       "``omega``", ":math:`\omega`", "absolute per-unit rotor speed, 1.0 at synchronism (state) [p.u.]", ""
       "(machine)", ":math:`H, D, f`", "inertia [s], damping and rotor friction of the host machine", ""
    """

    def states(self) -> List[str]:
        return ["delta", "omega"]

    def units(self) -> List[str]:
        return ["rad", "p.u."]

    def params(self) -> Dict[str, float]:
        return {}

    def x0(self) -> Dict[str, float]:
        return {"delta": 0.1, "omega": 0.0}

    def descriptions(self) -> Dict[str, str]:
        return {
            "delta": "mechanical rotor angle with respect to fictitious synchronous frame",
            "omega": "absolute per unit mechanical speed (1.0 at synchronism; i.e. 1 + deviation, NOT the deviation itself)",
        }

    def fgcall(self, host, dae: Dae, Pe) -> None:
        # Swing of a single rigid mass: reads the governor port pm (var_sym), the
        # air-gap power Pe, and the reference frequency.
        omega_b = [2 * np.pi * dae.fn]
        omega_ref_vec = host._omega_ref(dae)
        dae.f[host.delta] = omega_b * (dae.x[host.omega] - omega_ref_vec)
        dae.f[host.omega] = (
            1
            / (2 * host.H)
            * (
                host.var_sym(dae, "pm")
                - Pe
                - host.D * (dae.x[host.omega] - omega_ref_vec)
                - host.f * (dae.x[host.omega])
            )
        )


class MultiMassShaft(Shaft):
    r"""Generic multi-mass (torsional) turbine-generator shaft: a linear chain of
    lumped rotor masses connected by elastic shaft sections.

    Each mass :math:`i` carries an angle :math:`\delta_i` and an absolute p.u.
    speed :math:`\omega_i`. With ``omega_b`` :math:`= 2\pi f_n` and the reference
    speed :math:`\omega_{\text{ref}}` (= 1 p.u.):

    .. math::

        \dot{\delta}_i &= \omega_b (\omega_i - \omega_{\text{ref}}) \\
        2 H_i \dot{\omega}_i &= T_{m,i} - T_{e,i}
            - \!\!\sum_{j \sim i}\! K_{ij}(\delta_i - \delta_j)
            - D_i (\omega_i - \omega_{\text{ref}})
            - \!\!\sum_{j \sim i}\! D_{ij}(\omega_i - \omega_j)

    where the sums run over the adjacent masses :math:`j`. The mechanical power
    :math:`T_{m,i} = F_i P_m` is applied only to the turbine masses (fractions
    :math:`F_i` summing to 1), and the electromagnetic air-gap power
    :math:`T_{e,i} = P_e` only to the generator mass. The generator mass also
    carries the machine's rotor friction :math:`f\,\omega`.

    The **generator mass keeps the canonical names ``delta`` / ``omega``** and
    reuses the machine's own ``H`` / ``D`` / ``f``; every other mass ``<name>``
    contributes states ``delta_<name>`` / ``omega_<name>`` and parameters
    ``H_<name>`` (inertia) and ``D_<name>`` (self damping). Each shaft section
    between adjacent masses ``a`` and ``b`` contributes a stiffness ``K_<a>_<b>``
    and an optional mutual damping ``Dm_<a>_<b>`` (default 0). Each turbine mass
    contributes a mechanical fraction ``F_<name>``.

    This base is configured by the class attributes below; concrete shafts
    (:class:`Shaft4Mass`, :class:`Shaft5Mass`) just set them. With a single mass
    and no sections it reduces exactly to :class:`SingleMass`.
    """

    # ---- configured by concrete subclasses ----
    _masses: List[str] = []  # ordered chain; adjacency = consecutive entries
    _gen: str = "gen"  # which mass is the generator (carries Pe)
    _turbines: List[str] = []  # masses receiving a fraction of the mechanical power
    _H_def: Dict[str, float] = {}  # default inertia per non-generator mass
    _D_def: Dict[str, float] = {}  # default self damping per non-generator mass
    _K_def: Dict[str, float] = {}  # default stiffness per section "a_b"
    _Dm_def: Dict[str, float] = {}  # default mutual damping per section "a_b"
    _F_def: Dict[str, float] = {}  # default mechanical fraction per turbine mass

    # ---- naming helpers ----
    def _angle(self, m: str) -> str:
        return "delta" if m == self._gen else f"delta_{m}"

    def _speed(self, m: str) -> str:
        return "omega" if m == self._gen else f"omega_{m}"

    def _others(self) -> List[str]:
        return [m for m in self._masses if m != self._gen]

    def _sections(self) -> List[Tuple[str, str]]:
        return [
            (self._masses[i], self._masses[i + 1])
            for i in range(len(self._masses) - 1)
        ]

    # ---- strategy interface ----
    def states(self) -> List[str]:
        # Generator mass first (canonical delta/omega), then the other masses in
        # chain order. The first two states therefore stay 'delta'/'omega', as in
        # the single-mass model.
        s = ["delta", "omega"]
        for m in self._others():
            s += [f"delta_{m}", f"omega_{m}"]
        return s

    def units(self) -> List[str]:
        return ["rad", "p.u."] * len(self._masses)

    def params(self) -> Dict[str, float]:
        p: Dict[str, float] = {}
        for m in self._others():
            p[f"H_{m}"] = self._H_def.get(m, 1.0)
            p[f"D_{m}"] = self._D_def.get(m, 0.0)
        for a, b in self._sections():
            p[f"K_{a}_{b}"] = self._K_def.get(f"{a}_{b}", 30.0)
            p[f"Dm_{a}_{b}"] = self._Dm_def.get(f"{a}_{b}", 0.0)
        for m in self._turbines:
            p[f"F_{m}"] = self._F_def.get(m, 0.0)
        return p

    def x0(self) -> Dict[str, float]:
        # All masses are synchronous at steady state (omega -> omega_ref); the
        # finite-difference twist between adjacent masses is small, so guessing
        # the generator-mass angle for every mass starts Newton near the solution.
        d = {"delta": 0.1, "omega": 0.0}
        for m in self._others():
            d[f"delta_{m}"] = 0.1
            d[f"omega_{m}"] = 0.0
        return d

    def descriptions(self) -> Dict[str, str]:
        d = {
            "delta": "generator-mass rotor angle wrt fictitious synchronous frame",
            "omega": "absolute per unit generator-mass speed (1.0 at synchronism; NOT the deviation)",
        }
        for m in self._others():
            d[f"delta_{m}"] = f"{m.upper()} mass rotor angle wrt synchronous frame"
            d[f"omega_{m}"] = (
                f"absolute per unit {m.upper()} mass speed (1.0 at synchronism)"
            )
            d[f"H_{m}"] = f"{m.upper()} mass inertia constant"
            d[f"D_{m}"] = f"{m.upper()} mass self (absolute) damping"
        for a, b in self._sections():
            d[f"K_{a}_{b}"] = f"shaft stiffness between {a.upper()} and {b.upper()} masses"
            d[f"Dm_{a}_{b}"] = (
                f"mutual (shaft) damping between {a.upper()} and {b.upper()} masses"
            )
        for m in self._turbines:
            d[f"F_{m}"] = f"fraction of the mechanical power applied to the {m.upper()} mass"
        return d

    def fgcall(self, host, dae: Dae, Pe) -> None:
        omega_b = 2 * np.pi * dae.fn
        omega_ref = host._omega_ref(dae)
        pm = host.var_sym(dae, "pm")
        sections = self._sections()

        def ang(m: str):
            return dae.x[getattr(host, self._angle(m))]

        def spd(m: str):
            return dae.x[getattr(host, self._speed(m))]

        for m in self._masses:
            di = getattr(host, self._angle(m))
            oi = getattr(host, self._speed(m))
            H_m = host.H if m == self._gen else getattr(host, f"H_{m}")
            D_m = host.D if m == self._gen else getattr(host, f"D_{m}")

            # Rotor angle
            dae.f[di] = omega_b * (spd(m) - omega_ref)

            # Net accelerating torque/power on this mass
            torque = -D_m * (spd(m) - omega_ref)
            if m in self._turbines:
                torque = torque + getattr(host, f"F_{m}") * pm
            if m == self._gen:
                torque = torque - Pe - host.f * spd(m)
            for a, b in sections:
                if m == a:
                    nb = b
                elif m == b:
                    nb = a
                else:
                    continue
                K = getattr(host, f"K_{a}_{b}")
                Dm = getattr(host, f"Dm_{a}_{b}")
                torque = torque - K * (ang(m) - ang(nb)) - Dm * (spd(m) - spd(nb))

            dae.f[oi] = 1 / (2 * H_m) * torque


class Shaft4Mass(MultiMassShaft):
    r"""Four-mass torsional shaft: HP -- IP -- LP -- GEN in a linear chain.

    Selected on a machine line with ``shaft = "Shaft4Mass"``.

    **Model.** Each mass :math:`i` carries an angle and an absolute per-unit
    speed; adjacent masses are coupled by elastic shaft sections
    (see :class:`MultiMassShaft` for the general form):

    .. math::

       \dot{\delta}_i &= \omega_b \, (\omega_i - \omega_{ref}) \\
       2 H_i \, \dot{\omega}_i &= T_{m,i} - T_{e,i}
           - \sum_{j \sim i} K_{ij} (\delta_i - \delta_j)
           - D_i (\omega_i - \omega_{ref})
           - \sum_{j \sim i} D_{m,ij} (\omega_i - \omega_j)

    The turbine masses HP, IP and LP receive the fractions
    :math:`F_{hp}, F_{ip}, F_{lp}` of the governor's mechanical power
    (:math:`T_{m,i} = F_i \, p_m`, fractions summing to 1); the generator mass
    alone carries the air-gap power (:math:`T_{e,gen} = P_e`), the machine's
    own :math:`H, D` and the rotor friction :math:`f \omega`. The generator
    mass keeps the canonical state names ``delta`` / ``omega``, so nothing
    downstream changes with respect to :class:`SingleMass`.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 18, 14, 54, 10

       "``H_hp`` / ``H_ip`` / ``H_lp``", ":math:`H_i`", "turbine mass inertia constants [s]", "0.5 / 1 / 4"
       "``D_hp`` / ``D_ip`` / ``D_lp``", ":math:`D_i`", "turbine mass self damping", "0"
       "``K_hp_ip`` / ``K_ip_lp`` / ``K_lp_gen``", ":math:`K_{ij}`", "shaft section stiffness [p.u. torque/rad]", "30 / 40 / 60"
       "``Dm_hp_ip`` / ``Dm_ip_lp`` / ``Dm_lp_gen``", ":math:`D_{m,ij}`", "shaft section mutual damping", "0"
       "``F_hp`` / ``F_ip`` / ``F_lp``", ":math:`F_i`", "mechanical-power fractions (sum to 1)", "0.3 / 0.3 / 0.4"
       "``delta`` / ``omega``", ":math:`\delta, \omega`", "generator-mass angle [rad] and absolute speed [p.u.] (states)", ""
       "``delta_hp`` / ``omega_hp``", ":math:`\delta_{hp}, \omega_{hp}`", "HP mass angle and speed (states)", ""
       "``delta_ip`` / ``omega_ip``", ":math:`\delta_{ip}, \omega_{ip}`", "IP mass angle and speed (states)", ""
       "``delta_lp`` / ``omega_lp``", ":math:`\delta_{lp}, \omega_{lp}`", "LP mass angle and speed (states)", ""
    """

    _masses = ["hp", "ip", "lp", "gen"]
    _gen = "gen"
    _turbines = ["hp", "ip", "lp"]
    _H_def = {"hp": 0.5, "ip": 1.0, "lp": 4.0}
    _K_def = {"hp_ip": 30.0, "ip_lp": 40.0, "lp_gen": 60.0}
    _F_def = {"hp": 0.3, "ip": 0.3, "lp": 0.4}


class Shaft5Mass(MultiMassShaft):
    r"""Five-mass torsional shaft: HP -- IP -- LP -- GEN -- EXC in a linear
    chain.

    Selected on a machine line with ``shaft = "Shaft5Mass"``.

    **Model.** As :class:`Shaft4Mass`, with an additional exciter mass EXC on
    the far side of the generator; for each mass :math:`i` of the chain
    (see :class:`MultiMassShaft` for the general form):

    .. math::

       \dot{\delta}_i &= \omega_b \, (\omega_i - \omega_{ref}) \\
       2 H_i \, \dot{\omega}_i &= T_{m,i} - T_{e,i}
           - \sum_{j \sim i} K_{ij} (\delta_i - \delta_j)
           - D_i (\omega_i - \omega_{ref})
           - \sum_{j \sim i} D_{m,ij} (\omega_i - \omega_j)

    EXC carries no mechanical and no electrical power; it is a passive inertia
    coupled through the GEN--EXC shaft section, relevant for the higher
    torsional modes.

    **Symbols.** As :class:`Shaft4Mass`, plus:

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 18, 14, 54, 10

       "``H_hp`` / ``H_ip`` / ``H_lp`` / ``H_exc``", ":math:`H_i`", "non-generator mass inertia constants [s]", "0.5 / 1 / 4 / 0.1"
       "``D_hp`` / ``D_ip`` / ``D_lp`` / ``D_exc``", ":math:`D_i`", "non-generator mass self damping", "0"
       "``K_hp_ip`` / ``K_ip_lp`` / ``K_lp_gen`` / ``K_gen_exc``", ":math:`K_{ij}`", "shaft section stiffness [p.u. torque/rad]", "30 / 40 / 60 / 20"
       "``Dm_hp_ip`` / ``Dm_ip_lp`` / ``Dm_lp_gen`` / ``Dm_gen_exc``", ":math:`D_{m,ij}`", "shaft section mutual damping", "0"
       "``F_hp`` / ``F_ip`` / ``F_lp``", ":math:`F_i`", "mechanical-power fractions (sum to 1)", "0.3 / 0.3 / 0.4"
       "``delta`` / ``omega``", ":math:`\delta, \omega`", "generator-mass angle [rad] and absolute speed [p.u.] (states)", ""
       "``delta_hp`` / ``omega_hp``", ":math:`\delta_{hp}, \omega_{hp}`", "HP mass angle and speed (states)", ""
       "``delta_ip`` / ``omega_ip``", ":math:`\delta_{ip}, \omega_{ip}`", "IP mass angle and speed (states)", ""
       "``delta_lp`` / ``omega_lp``", ":math:`\delta_{lp}, \omega_{lp}`", "LP mass angle and speed (states)", ""
       "``delta_exc`` / ``omega_exc``", ":math:`\delta_{exc}, \omega_{exc}`", "EXC mass angle and speed (states)", ""
    """

    _masses = ["hp", "ip", "lp", "gen", "exc"]
    _gen = "gen"
    _turbines = ["hp", "ip", "lp"]
    _H_def = {"hp": 0.5, "ip": 1.0, "lp": 4.0, "exc": 0.1}
    _K_def = {"hp_ip": 30.0, "ip_lp": 40.0, "lp_gen": 60.0, "gen_exc": 20.0}
    _F_def = {"hp": 0.3, "ip": 0.3, "lp": 0.4}


SHAFT_REGISTRY: Dict[str, type] = {
    "SingleMass": SingleMass,
    "Shaft4Mass": Shaft4Mass,
    "Shaft5Mass": Shaft5Mass,
}
