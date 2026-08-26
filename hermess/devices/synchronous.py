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

r"""Synchronous machine models.

A machine is selected in a system file by its class name in the first column;
its controllers are pluggable strategies chosen by keyword on the same line::

   SynchronousSubtransientSP, idx = "SG1", bus = "1", Sn = 300, avr = "SEXST",
       governor = "TGOV1", pss = "PSSKundur", shaft = "SingleMass", ...

Every model documents its electromagnetic equations and a table mapping the
code parameter names to the mathematical symbols used there. The rotor-motion
(swing) equations belong to the shaft strategy (:mod:`hermess.devices.shaft`),
and the exciter, governor and stabilizer equations to their strategy classes
(:mod:`hermess.devices.avr`, :mod:`hermess.devices.governor`,
:mod:`hermess.devices.pss`).

Common conventions: quantities are in per unit on the machine base ``Sn``; the
rotor speed :math:`\omega` is the absolute per-unit speed (1 at synchronism);
:math:`\delta` is the rotor angle against the network reference frame. The
machine dq frame is obtained from the network rectangular frame by

.. math::

   v_d = v_{re}\sin\delta - v_{im}\cos\delta, \qquad
   v_q = v_{re}\cos\delta + v_{im}\sin\delta,

currents entering the machine are rescaled by :math:`S_b/S_n` and the injection
into the network current balance by :math:`S_n/S_b`.
"""

from __future__ import annotations  # Postponed type evaluation
from typing import TYPE_CHECKING, Tuple

from hermess.devices.device import DeviceRect, sin, cos
from hermess.devices.avr import AVR, IEEEDC1A
from hermess.devices.governor import Governor, TGOV1
from hermess.devices.pss import PSS
from hermess.devices.shaft import Shaft, SingleMass


if TYPE_CHECKING:
    from hermess.system import Dae
import casadi as ca
import numpy as np


class Synchronous(DeviceRect):
    r"""Base class of all synchronous machines: composition of an
    electromagnetic model (the subclass) with pluggable shaft, governor, AVR
    and PSS strategies, and the network coupling.

    The subclass provides :meth:`electromagnetic` (stator currents, rotor-flux
    dynamics, air-gap power :math:`P_e`); the base wires the shaft's swing
    equations (reading the governor port :math:`p_m` and :math:`P_e`), the
    controller couplings (:math:`E_{fd}` from the AVR, :math:`V_s` from the
    PSS), and the current injection into the network balance,

    .. math::

       0 = \dots - \frac{S_n}{S_b}
           \bigl( i_d \sin\delta + i_q \cos\delta \bigr), \qquad
       0 = \dots - \frac{S_n}{S_b}
           \bigl( -i_d \cos\delta + i_q \sin\delta \bigr)

    in the real and imaginary network equations of the machine bus. Coupling
    variables (``pm``, ``Efd``, ``Vs``) may be differential states or private
    algebraics depending on the strategy; :meth:`var_sym` resolves them either
    way.

    **Symbols** (base-machine parameters shared by every model; the strategy
    parameters are documented in the strategy classes):

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``Sn``", ":math:`S_n`", "machine MVA rating (device base) [MVA]", "100"
       "``Vn``", ":math:`V_n`", "rated voltage [kV]", "\-"
       "``fn``", ":math:`f_n`", "rated frequency [Hz]", "50"
       "``H``", ":math:`H`", "inertia constant [s]", "30"
       "``D``", ":math:`D`", "rotor damping coefficient", "0"
       "``f``", ":math:`f`", "rotor friction coefficient", "0.01"
       "``R_s``", ":math:`R_s`", "stator resistance [p.u.]", "0"
       "``x_d``", ":math:`x_d`", "d-axis synchronous reactance [p.u.]", "0.2"
       "``x_q``", ":math:`x_q`", "q-axis synchronous reactance [p.u.]", "0.2"
       "``x_l``", ":math:`x_l`", "leakage / stator-series reactance [p.u.]", "0.1"
       "``delta``", ":math:`\delta`", "rotor angle (state) [rad]", ""
       "``omega``", ":math:`\omega`", "absolute rotor speed (state) [p.u., 1 at synchronism]", ""
    """

    def __init__(
        self,
        avr: AVR = None,
        governor: Governor = None,
        pss: PSS = None,
        shaft: Shaft = None,
    ):
        super().__init__()

        # Shaft strategy. Default: a single rigid mass (the classic swing
        # equation). A multi-mass torsional shaft adds further rotor masses while
        # keeping the generator mass on the canonical 'delta'/'omega' names.
        self._shaft: Shaft = shaft or SingleMass()
        # AVR strategy (default IEEEDC1A).
        self._avr: AVR = avr or IEEEDC1A()
        # Governor strategy (default TGOV1).
        self._governor: Governor = governor or TGOV1()
        # PSS strategy. No default: when None, the machine supplies no stabilizing
        # signal to its AVR (pss_signal returns 0).
        self._pss: PSS = pss

        # --- Machine params ---
        self._params.update(
            {
                "fn": 50,
                "H": 30,
                "R_s": 0.0,
                "x_q": 0.2,
                "x_d": 0.2,
                "x_l": 0.1,
                "D": 0.0,
                "f": 0.01,
            }
        )

        # --- Shaft params (from strategy; empty for the single-mass default) ---
        self._params.update(self._shaft.params())

        # --- Governor params (from strategy) ---
        self._params.update(self._governor.params())

        # --- AVR params (from strategy) ---
        self._params.update(self._avr.params())

        # --- PSS params (from strategy, if any) ---
        if self._pss is not None:
            self._params.update(self._pss.params())

        self._descr.update(
            {
                "H": "inertia constant",
                "D": "rotor damping",
                "fn": "rated frequency",
                "bus": "bus id",
                "gen": "static generator id",
                "R_s": "stator resistance",
                "x_d": "reactance in d axis",
                "x_q": "reactance in q axis",
                "x_l": "leakage / stator-series reactance",
                "f": "rotor friction coefficient",
            }
        )
        # delta/omega (and any extra rotor masses) are described by the shaft.
        self._descr.update(self._shaft.descriptions())
        self._descr.update(self._governor.descriptions())
        self._descr.update(self._avr.descriptions())
        if self._pss is not None:
            self._descr.update(self._pss.descriptions())

        # params
        # SG
        self.fn = np.array([], dtype=float)
        self.H = np.array([], dtype=float)
        self.R_s = np.array([], dtype=float)
        self.x_d = np.array([], dtype=float)
        self.x_q = np.array([], dtype=float)
        self.x_l = np.array([], dtype=float)
        self.D = np.array([], dtype=float)
        self.f = np.array([], dtype=float)
        # Shaft param arrays (dynamic from strategy; none for the single-mass shaft)
        for param_name in self._shaft.params():
            setattr(self, param_name, np.array([], dtype=float))
        # Governor param arrays (dynamic from strategy)
        for param_name in self._governor.params():
            setattr(self, param_name, np.array([], dtype=float))
        # AVR param arrays (dynamic from strategy)
        for param_name in self._avr.params():
            setattr(self, param_name, np.array([], dtype=float))
        # PSS param arrays (dynamic from strategy, if any)
        if self._pss is not None:
            for param_name in self._pss.params():
                setattr(self, param_name, np.array([], dtype=float))

        # --- Rotor/shaft states (from strategy) ---
        # Registered first so the state vector leads with [delta, omega, ...].
        # Every shaft must expose the generator mass as the differential states
        # 'delta' and 'omega'; a multi-mass shaft adds further rotor masses
        # (delta_<name>/omega_<name>) after them.
        self.ns = 0
        shaft_states = self._shaft.states()
        assert "delta" in shaft_states and "omega" in shaft_states, (
            "Shaft must expose the generator mass as the states 'delta' and 'omega'"
        )
        self.ns += len(shaft_states)
        self.states.extend(shaft_states)
        self.units.extend(self._shaft.units())
        for state_name in shaft_states:
            setattr(self, state_name, np.array([], dtype=float))

        # --- Governor states + private algebraics (from strategy) ---
        # Registered before the AVR so the state vector reads
        # [delta, omega, <governor>, <avr>, <machine flux>]. 'pm' is the
        # mechanical-power coupling into the swing equation; it may be a state
        # (TGOV1) or a private algebraic (read via self.var_sym("pm")).
        gov_states = self._governor.states()
        gov_algebs = self._governor.algebs()
        assert "pm" in set(gov_states) | set(gov_algebs), (
            "Governor must expose 'pm' as either a state or a private algebraic"
        )
        self.ns += len(gov_states)
        self.states.extend(gov_states)
        self.units.extend(self._governor.units())
        for state_name in gov_states:
            setattr(self, state_name, np.array([], dtype=float))
        if gov_algebs:
            self._algebs_int.extend(gov_algebs)
            self._algebs_int_units.update(self._governor.algebs_units())
            self._algebs_int_x0.update(self._governor.algebs_x0())
            for algeb_name in gov_algebs:
                setattr(self, algeb_name, np.array([], dtype=float))

        # --- AVR states (from strategy) ---
        avr_states = self._avr.states()
        avr_algebs = self._avr.algebs()
        # 'Efd' is the field-voltage coupling variable; it may be a differential
        # state (pure-lag exciter, e.g. IEEEDC1A) or a device-private algebraic
        # (direct-feedthrough exciter, e.g. AVRKundur). Either is fine --
        # the machine reads it through self.var_sym("Efd").
        assert "Efd" in set(avr_states) | set(avr_algebs), (
            "AVR must expose 'Efd' as either a state or a private algebraic"
        )
        self.ns += len(avr_states)
        self.states.extend(avr_states)
        self.units.extend(self._avr.units())
        for state_name in avr_states:
            setattr(self, state_name, np.array([], dtype=float))

        # --- AVR private algebraic variables (from strategy) ---
        # Register the AVR's private algebraics on the host (_algebs_int +
        # metadata). Empty for pure-lag exciters.
        if avr_algebs:
            self._algebs_int.extend(avr_algebs)
            self._algebs_int_units.update(self._avr.algebs_units())
            self._algebs_int_x0.update(self._avr.algebs_x0())
            for algeb_name in avr_algebs:
                setattr(self, algeb_name, np.array([], dtype=float))

        # --- PSS states + private algebraics (from strategy, if any) ---
        # Registered after the AVR. 'Vs' is the stabilizing signal summed into
        # the AVR error; it may be a state or a private algebraic and is read by
        # the AVR through self.pss_signal(dae). Skipped when there is no PSS.
        if self._pss is not None:
            pss_states = self._pss.states()
            pss_algebs = self._pss.algebs()
            assert "Vs" in set(pss_states) | set(pss_algebs), (
                "PSS must expose 'Vs' as either a state or a private algebraic"
            )
            self.ns += len(pss_states)
            self.states.extend(pss_states)
            self.units.extend(self._pss.units())
            for state_name in pss_states:
                setattr(self, state_name, np.array([], dtype=float))
            if pss_algebs:
                self._algebs_int.extend(pss_algebs)
                self._algebs_int_units.update(self._pss.algebs_units())
                self._algebs_int_x0.update(self._pss.algebs_x0())
                for algeb_name in pss_algebs:
                    setattr(self, algeb_name, np.array([], dtype=float))

        self._x0.update(self._shaft.x0())
        self._x0.update(self._governor.x0())
        self._x0.update(self._avr.x0())
        if self._pss is not None:
            self._x0.update(self._pss.x0())

        # Set points (from strategies)
        self._setpoints.update(self._governor.setpoints())
        self._setpoints.update(self._avr.setpoints())
        if self._pss is not None:
            self._setpoints.update(self._pss.setpoints())
        for sp_name in self._governor.setpoints():
            setattr(self, sp_name, np.array([], dtype=float))
        for sp_name in self._avr.setpoints():
            setattr(self, sp_name, np.array([], dtype=float))
        if self._pss is not None:
            for sp_name in self._pss.setpoints():
                setattr(self, sp_name, np.array([], dtype=float))
        self.properties.update({"fplot": True})
        # Air-gap electrical power (device p.u.); set symbolically in fgcall.
        self.Pe = None

    def gcall(self, dae: Dae, i_d: ca.SX, i_q: ca.SX) -> None:
        # algebraic equations (current balance in rectangular coordinates) + scale the current back to the grid reference power

        dae.g[self.vre] -= (
            self.Sn
            / dae.Sb
            * (i_d * sin(dae.x[self.delta]) + i_q * cos(dae.x[self.delta]))
        )
        dae.g[self.vim] -= (
            self.Sn
            / dae.Sb
            * (i_d * -cos(dae.x[self.delta]) + i_q * sin(dae.x[self.delta]))
        )

    def _omega_ref(self, dae: Dae) -> ca.SX:
        """Per-machine reference-frame frequency: the nominal ``dae.omega_net``
        (= 1 p.u.) by default, or the per-bus reference frequency when
        ``dae.omega_ref_buses`` is present."""
        omega_ref_vec = ca.SX.ones(self.n, 1) * dae.omega_net
        if getattr(dae, "omega_ref_buses", None) is not None:
            omega_list = []
            for k in range(self.n):
                bus_label = str(self.bus[k])
                bus_idx = dae.grid.idx_bus[bus_label]
                omega_list.append(dae.omega_ref_buses[bus_idx])
            omega_ref_vec = ca.vertcat(*omega_list)
        return omega_ref_vec

    def rotor(self, dae: Dae, Pe: ca.SX) -> None:
        """Delegate the swing (rotor-motion) equations to the pluggable shaft
        strategy. The default :class:`SingleMass` writes the classic single-mass
        swing equation (reading the governor port ``var_sym("pm")``, the air-gap
        power ``Pe`` and the reference frequency); a multi-mass (torsional) shaft
        adds further rotor masses while keeping the generator mass on the
        ``delta`` / ``omega`` names, so the electromagnetic models, the network
        injection and the controllers are untouched."""
        self._shaft.fgcall(self, dae, Pe)

    def fgcall(self, dae: Dae) -> None:
        """Template orchestration shared by all machine models: the EM subclass
        defines stator currents + flux dynamics and returns the air-gap power;
        the base wires the rotor, the controller ports, and the network."""
        i_d, i_q, Pe = self.electromagnetic(dae)
        # Publish the air-gap electrical power (device p.u., on Sn) so it can be
        # read back after a run -- e.g. evaluated along the trajectory for plots
        # or used in an objective -- without re-deriving it from the states.
        self.Pe = Pe
        self.rotor(dae, Pe)
        self.governor_fcall(dae)
        self.avr_fcall(dae)
        self.pss_fcall(dae)
        self.gcall(dae, i_d, i_q)

    def electromagnetic(self, dae: Dae):
        """Subclass hook: define the stator currents (i_d, i_q), write the
        flux/emf differential equations, and return ``(i_d, i_q, Pe)`` where
        ``Pe`` is the air-gap power/torque consumed by :meth:`rotor`."""
        raise NotImplementedError

    def governor_fcall(self, dae: Dae) -> None:
        """Delegate the governor's equations to the strategy object. The strategy
        writes its differential equations into ``dae.f`` and, if it declares
        private algebraics (e.g. an algebraic 'pm'), their residuals into
        ``dae.g``."""
        self._governor.fgcall(self, dae)

    def tgov1(self, dae: Dae) -> None:
        """Deprecated: use governor_fcall instead."""
        self.governor_fcall(dae)

    def avr_fcall(self, dae: Dae) -> None:
        """Delegate the AVR's equations to the strategy object. The strategy
        writes its differential equations into ``dae.f`` and, if it declares
        private algebraics (e.g. an algebraic 'Efd'), their residuals into
        ``dae.g``."""
        self._avr.fgcall(self, dae)

    def var_sym(self, dae: Dae, name: str) -> ca.SX:
        """Resolve a registered variable to its symbol, wherever it lives.

        A coupling variable such as 'Efd' may be a differential state (in
        ``dae.x``) or a device-private algebraic (in ``dae.y``), depending on
        the AVR strategy. This resolver lets the machine's electromagnetic
        equations reference it without knowing which, so state-based and
        algebraic exciters are interchangeable.
        """
        if name in self._algebs_int:
            return dae.y[getattr(self, name)]
        return dae.x[getattr(self, name)]

    def pss_fcall(self, dae: Dae) -> None:
        """Delegate the PSS's equations to the strategy object (no-op if there is
        no PSS). The strategy writes its differential equations into ``dae.f`` and,
        if it declares private algebraics (e.g. an algebraic 'Vs'), their residuals
        into ``dae.g``."""
        if self._pss is not None:
            self._pss.fgcall(self, dae)

    def pss_signal(self, dae: Dae) -> ca.SX:
        """The supplementary stabilizing signal 'Vs' summed into the AVR voltage
        error (the host-mediated PSS->AVR coupling). Returns the 'Vs' symbol
        (state or private algebraic, via :meth:`var_sym`) when a PSS is present,
        else 0."""
        if self._pss is None:
            return 0
        return self.var_sym(dae, "Vs")

    def ieeedc1a(self, dae: Dae) -> None:
        """Deprecated: use avr_fcall instead."""
        self.avr_fcall(dae)


class SynchronousTransient(Synchronous):
    r"""Two-axis (transient) synchronous machine
(F. Milano, *Power System Modelling and Scripting*, 2010).

    Selected in a system file by the class name in the first column::

       SynchronousTransient, idx = "SG1", bus = "1", Sn = 300, avr = "SEXST", ...

    **Model.** Stator currents from the algebraic stator relation (per machine)

    .. math::

       \begin{bmatrix} R_s & -x'_q \\ x'_d & R_s \end{bmatrix}
       \begin{bmatrix} i_d \\ i_q \end{bmatrix}
       =
       \begin{bmatrix} e'_d - v_d \\ e'_q - v_q \end{bmatrix},

    transient EMF dynamics and air-gap power

    .. math::

       T'_d \, \dot{e}'_q &= -e'_q + E_{fd} - (x_d - x'_d)\, i_d \\
       T'_q \, \dot{e}'_d &= -e'_d + (x_q - x'_q)\, i_q \\
       P_e &= e'_d i_d + e'_q i_q + (x'_q - x'_d)\, i_d i_q .

    The rotor motion is written by the shaft strategy (default
    :class:`~hermess.devices.shaft.SingleMass`,
    :math:`\dot{\delta} = \omega_b(\omega - \omega_{ref})`,
    :math:`2H\dot{\omega} = p_m - P_e - D(\omega - \omega_{ref}) - f\omega`
    with :math:`\omega` the absolute per-unit speed); :math:`E_{fd}` comes from
    the AVR strategy and :math:`p_m` from the governor strategy.

    **Symbols** (model-specific; base-machine and strategy parameters are
    documented in :class:`Synchronous` and the strategy classes):

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``x_dprim``", ":math:`x'_d`", "d-axis transient reactance [p.u.]", "0.05"
       "``x_qprim``", ":math:`x'_q`", "q-axis transient reactance [p.u.]", "0.1"
       "``T_dprim``", ":math:`T'_d`", "d-axis transient time constant [s]", "8"
       "``T_qprim``", ":math:`T'_q`", "q-axis transient time constant [s]", "0.8"
       "``e_dprim``", ":math:`e'_d`", "d-axis EMF behind transient reactance (state) [p.u.]", ""
       "``e_qprim``", ":math:`e'_q`", "q-axis EMF behind transient reactance (state) [p.u.]", ""
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)

        self._type = "Synchronous_machine"
        self._name = "Synchronous_machine_transient_model"

        # States
        self.ns += 2
        self.states.extend(["e_dprim", "e_qprim"])
        self.units.extend(["p.u.", "p.u."])
        self.e_dprim = np.array([], dtype=float)
        self.e_qprim = np.array([], dtype=float)

        self._x0.update(
            {
                "delta": 0.0,
                "omega": 0.0,
                "e_dprim": -0.4,
                "e_qprim": 1,
                "psv": 0.5,
                "pm": 0.5,
                "Efd": 2.5,
                "Rf": 0.0,
                "Vr": 2.5,
            }
        )

        # Params
        self._params.update(
            {"x_dprim": 0.05, "x_qprim": 0.1, "T_dprim": 8.0, "T_qprim": 0.8}
        )
        self._descr.update(
            {
                "T_dprim": "d-axis transient time constant",
                "T_qprim": "q-axis transient time constant",
                "e_dprim": "d-axis voltage behind transient reactance",
                "e_qprim": "q-axis voltage behind transient reactance",
                "x_dprim": "d-axis transient reactance",
                "x_qprim": "q-axis transient reactance",
            }
        )

        # Parameters
        self.x_dprim = np.array([], dtype=float)
        self.x_qprim = np.array([], dtype=float)
        self.T_dprim = np.array([], dtype=float)
        self.T_qprim = np.array([], dtype=float)

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
                "gcall": True,
            }
        )

        self._init_data()

    def input_current(self, dae: Dae) -> Tuple[ca.SX, ca.SX]:
        # differential equations
        i_d = ca.SX.sym("id", self.n)
        i_q = ca.SX.sym("iq", self.n)
        for i in range(self.n):
            adq = ca.SX(
                [[self.R_s[i], -self.x_qprim[i]], [self.x_dprim[i], self.R_s[i]]]
            )
            vd = dae.y[self.vre[i]] * np.sin(dae.x[self.delta[i]]) + dae.y[
                self.vim[i]
            ] * -np.cos(dae.x[self.delta[i]])
            vq = dae.y[self.vre[i]] * np.cos(dae.x[self.delta[i]]) + dae.y[
                self.vim[i]
            ] * np.sin(dae.x[self.delta[i]])
            b1 = -vd + dae.x[self.e_dprim[i]]
            b2 = -vq + dae.x[self.e_qprim[i]]
            b = ca.vertcat(b1, b2)
            i_dq = (
                ca.solve(adq, b) * dae.Sb / self.Sn[i]
            )  # scale the current for the base power inside the machine
            i_d[i] = i_dq[0]
            i_q[i] = i_dq[1]
        return i_d, i_q

    def electromagnetic(self, dae: Dae):
        """Two-axis (transient) electromagnetic model: stator currents, the
        e'_d/e'_q dynamics, and the air-gap power. The swing equation and
        orchestration live in the base (rotor / fgcall template)."""
        i_d, i_q = self.input_current(dae)

        # Air-gap power consumed by the rotor swing (Pe = E'_d I_d + E'_q I_q
        # + (X'_q - X'_d) I_d I_q).
        Pe = (
            dae.x[self.e_dprim] * i_d
            + dae.x[self.e_qprim] * i_q
            + (self.x_qprim - self.x_dprim) * i_d * i_q
        )

        dae.f[self.e_qprim] = (
            1
            / self.T_dprim
            * (-dae.x[self.e_qprim] + self.var_sym(dae, "Efd") - (self.x_d - self.x_dprim) * i_d)
        )  # Eq
        dae.f[self.e_dprim] = (
            1 / self.T_qprim * (-dae.x[self.e_dprim] + (self.x_q - self.x_qprim) * i_q)
        )  # Ed

        return i_d, i_q, Pe


class SynchronousSubtransient(Synchronous):
    r"""Subtransient (Anderson-Fouad) synchronous machine
(F. Milano, *Power System Modelling and Scripting*, 2010).

    Selected in a system file by the class name in the first column::

       SynchronousSubtransient, idx = "SG1", bus = "1", Sn = 300, avr = "IEEEDC1A", ...

    **Model.** Stator currents from the algebraic stator relation with the
    subtransient EMFs,

    .. math::

       \begin{bmatrix} R_s & -x''_q \\ x''_d & R_s \end{bmatrix}
       \begin{bmatrix} i_d \\ i_q \end{bmatrix}
       =
       \begin{bmatrix} e''_d - v_d \\ e''_q - v_q \end{bmatrix},

    transient and subtransient EMF dynamics and air-gap power

    .. math::

       T'_d \, \dot{e}'_q &= -e'_q + E_{fd} - (x_d - x'_d)\, i_d \\
       T'_q \, \dot{e}'_d &= -e'_d + (x_q - x'_q)\, i_q \\
       T''_d \, \dot{e}''_q &= e'_q - e''_q - (x'_d - x''_d)\, i_d \\
       T''_q \, \dot{e}''_d &= e'_d - e''_d + (x'_q - x''_q)\, i_q \\
       P_e &= e''_d i_d + e''_q i_q + (x''_q - x''_d)\, i_d i_q .

    Rotor motion, exciter and governor as in :class:`SynchronousTransient`
    (shaft, AVR and governor strategies).

    **Symbols** (model-specific):

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``x_dprim``", ":math:`x'_d`", "d-axis transient reactance [p.u.]", "0.05"
       "``x_qprim``", ":math:`x'_q`", "q-axis transient reactance [p.u.]", "0.1"
       "``T_dprim``", ":math:`T'_d`", "d-axis transient time constant [s]", "8"
       "``T_qprim``", ":math:`T'_q`", "q-axis transient time constant [s]", "0.8"
       "``x_dsec``", ":math:`x''_d`", "d-axis subtransient reactance [p.u.]", "0.01"
       "``x_qsec``", ":math:`x''_q`", "q-axis subtransient reactance [p.u.]", "0.01"
       "``T_dsec``", ":math:`T''_d`", "d-axis subtransient time constant [s]", "0.001"
       "``T_qsec``", ":math:`T''_q`", "q-axis subtransient time constant [s]", "0.001"
       "``e_dprim``", ":math:`e'_d`", "d-axis transient EMF (state) [p.u.]", ""
       "``e_qprim``", ":math:`e'_q`", "q-axis transient EMF (state) [p.u.]", ""
       "``e_dsec``", ":math:`e''_d`", "d-axis subtransient EMF (state) [p.u.]", ""
       "``e_qsec``", ":math:`e''_q`", "q-axis subtransient EMF (state) [p.u.]", ""
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)

        # private data
        self._type = "Synchronous_machine"
        self._name = "Synchronous_machine_subtransient_model"

        # States
        self.ns += 4
        self.states.extend(["e_dprim", "e_qprim", "e_dsec", "e_qsec"])
        self.units.extend(["p.u.", "p.u.", "p.u.", "p.u."])
        self.e_dprim = np.array([], dtype=float)
        self.e_qprim = np.array([], dtype=float)
        self.e_dsec = np.array([], dtype=float)
        self.e_qsec = np.array([], dtype=float)

        self._x0.update(
            {
                "delta": 0.1,
                "omega": 0.0,
                "e_dprim": 0.0,
                "e_qprim": 1.0,
                "psv": 0.5,
                "pm": 0.5,
                "Efd": 2.3,
                "Rf": 0.0,
                "Vr": 2.3,
                "e_dsec": 0.0,
                "e_qsec": 1.0,
            }
        )

        # Params
        self._params.update(
            {
                "x_dprim": 0.05,
                "x_qprim": 0.1,
                "T_dprim": 8.0,
                "T_qprim": 0.8,
                "x_dsec": 0.01,
                "x_qsec": 0.01,
                "T_dsec": 0.001,
                "T_qsec": 0.001,
            }
        )

        self._descr.update(
            {
                "T_dprim": "d-axis transient time constant",
                "T_qprim": "q-axis transient time constant",
                "x_dprim": "d-axis transient reactance",
                "x_qprim": "q-axis transient reactance",
                "e_dprim": "d-axis voltage behind transient reactance",
                "e_qprim": "q-axis voltage behind transient reactance",
                "e_dsec": "d-axis voltage behind subtransient reactance",
                "e_qsec": "q-axis voltage behind subtransient reactance",
                "T_dsec": "d-axis subtransient time constant",
                "T_qsec": "q-axis subtransient time constant",
                "x_dsec": "d-axis subtransient reactance",
                "x_qsec": "q-axis subtransient reactance",
            }
        )

        # Parameters
        self.x_dprim = np.array([], dtype=float)
        self.x_qprim = np.array([], dtype=float)
        self.T_dprim = np.array([], dtype=float)
        self.T_qprim = np.array([], dtype=float)
        self.x_dsec = np.array([], dtype=float)
        self.x_qsec = np.array([], dtype=float)
        self.T_dsec = np.array([], dtype=float)
        self.T_qsec = np.array([], dtype=float)

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
            }
        )

        self._init_data()

    def input_current(self, dae: Dae) -> Tuple[ca.SX, ca.SX]:
        # differential equations
        i_d = ca.SX.sym("Id", self.n)
        i_q = ca.SX.sym("Iq", self.n)
        for i in range(self.n):
            adq = ca.SX([[self.R_s[i], -self.x_qsec[i]], [self.x_dsec[i], self.R_s[i]]])
            vd = dae.y[self.vre[i]] * np.sin(dae.x[self.delta[i]]) + dae.y[
                self.vim[i]
            ] * -np.cos(dae.x[self.delta[i]])
            vq = dae.y[self.vre[i]] * np.cos(dae.x[self.delta[i]]) + dae.y[
                self.vim[i]
            ] * np.sin(dae.x[self.delta[i]])
            b1 = -vd + dae.x[self.e_dsec[i]]
            b2 = -vq + dae.x[self.e_qsec[i]]
            b = ca.vertcat(b1, b2)
            i_dq = (
                ca.solve(adq, b) * dae.Sb / self.Sn[i]
            )  # scale the current for the base power inside the machine
            i_d[i] = i_dq[0]
            i_q[i] = i_dq[1]
        return i_d, i_q

    def electromagnetic(self, dae: Dae):
        """Anderson-Fouad (subtransient) electromagnetic model: stator currents,
        the e'/e'' dynamics, and the air-gap power. Swing/orchestration in base."""
        i_d, i_q = self.input_current(dae)

        # Air-gap power (subtransient emfs): Pe = E''_d I_d + E''_q I_q
        # + (X''_q - X''_d) I_d I_q.
        Pe = (
            dae.x[self.e_dsec] * i_d
            + dae.x[self.e_qsec] * i_q
            + (self.x_qsec - self.x_dsec) * i_d * i_q
        )

        dae.f[self.e_qprim] = (
            1
            / self.T_dprim
            * (-dae.x[self.e_qprim] + self.var_sym(dae, "Efd") - (self.x_d - self.x_dprim) * i_d)
        )  # Eq
        dae.f[self.e_dprim] = (
            1 / self.T_qprim * (-dae.x[self.e_dprim] + (self.x_q - self.x_qprim) * i_q)
        )  # Ed
        dae.f[self.e_qsec] = (
            1
            / self.T_dsec
            * (
                dae.x[self.e_qprim]
                - dae.x[self.e_qsec]
                - (self.x_dprim - self.x_dsec) * i_d
            )
        )
        dae.f[self.e_dsec] = (
            1
            / self.T_qsec
            * (
                dae.x[self.e_dprim]
                - dae.x[self.e_dsec]
                + (self.x_qprim - self.x_qsec) * i_q
            )
        )

        return i_d, i_q, Pe


class SynchronousSubtransientSP(Synchronous):
    r"""Subtransient Sauer-Pai synchronous machine WITH stator (electromagnetic)
    flux dynamics (P. W. Sauer and M. A. Pai, *Power System Dynamics and
    Stability*, 1998). The stator transients make this the machine to pair with
    dynamic line models (``line_dyn=True``).

    Selected in a system file by the class name in the first column::

       SynchronousSubtransientSP, idx = "SG1", bus = "1", Sn = 300, avr = "SEXST", ...

    **Model.** With the coupling coefficients

    .. math::

       g_{d1} = \frac{x''_d - x_l}{x'_d - x_l}, \quad
       g_{q1} = \frac{x''_q - x_l}{x'_q - x_l}, \quad
       g_{d2} = \frac{1 - g_{d1}}{x'_d - x_l}, \quad
       g_{q2} = \frac{1 - g_{q1}}{x'_q - x_l},

    the stator currents are explicit in the flux states,

    .. math::

       i_d &= \frac{1}{x''_d} \bigl( -\psi_d + g_{d1} e'_q + (1 - g_{d1}) \psi_{d2} \bigr) \\
       i_q &= \frac{1}{x''_q} \bigl( -\psi_q - g_{q1} e'_d + (1 - g_{q1}) \psi_{q2} \bigr),

    the rotor-circuit and stator-flux dynamics are

    .. math::

       T'_d \, \dot{e}'_q &= -e'_q - (x_d - x'_d) \bigl( g_{d1} i_d
           - g_{d2} \psi_{d2} + g_{d2} e'_q \bigr) + E_{fd} \\
       T'_q \, \dot{e}'_d &= -e'_d + (x_q - x'_q) \bigl( g_{q1} i_q
           - g_{q2} \psi_{q2} - g_{q2} e'_d \bigr) \\
       T''_d \, \dot{\psi}_{d2} &= -\psi_{d2} + e'_q - (x'_d - x_l)\, i_d \\
       T''_q \, \dot{\psi}_{q2} &= -\psi_{q2} - e'_d - (x'_q - x_l)\, i_q \\
       \dot{\psi}_d &= \omega_b \bigl( R_s i_d + \omega \psi_q + v_d \bigr) \\
       \dot{\psi}_q &= \omega_b \bigl( R_s i_q - \omega \psi_d + v_q \bigr)

    with :math:`\omega_b = 2\pi f_n`, :math:`\omega` the absolute per-unit
    rotor speed, and air-gap power :math:`P_e = \psi_d i_q - \psi_q i_d`.
    Rotor motion, exciter and governor come from the shaft, AVR and governor
    strategies.

    **Symbols** (model-specific; :math:`g_{d1}, g_{q1}, g_{d2}, g_{q2}` are
    computed from the reactances, not inputs):

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``x_l``", ":math:`x_l`", "leakage reactance [p.u.]", "0.1"
       "``x_dprim``", ":math:`x'_d`", "d-axis transient reactance [p.u.]", "0.05"
       "``x_qprim``", ":math:`x'_q`", "q-axis transient reactance [p.u.]", "0.1"
       "``T_dprim``", ":math:`T'_d`", "d-axis transient time constant [s]", "8"
       "``T_qprim``", ":math:`T'_q`", "q-axis transient time constant [s]", "0.8"
       "``x_dsec``", ":math:`x''_d`", "d-axis subtransient reactance [p.u.]", "0.01"
       "``x_qsec``", ":math:`x''_q`", "q-axis subtransient reactance [p.u.]", "0.01"
       "``T_dsec``", ":math:`T''_d`", "d-axis subtransient time constant [s]", "0.001"
       "``T_qsec``", ":math:`T''_q`", "q-axis subtransient time constant [s]", "0.001"
       "``gd1`` ``gq1`` ``gd2`` ``gq2``", ":math:`g_{d1}, g_{q1}, g_{d2}, g_{q2}`", "coupling coefficients (derived)", ""
       "``e_dprim``", ":math:`e'_d`", "d-axis transient EMF (state) [p.u.]", ""
       "``e_qprim``", ":math:`e'_q`", "q-axis transient EMF (state) [p.u.]", ""
       "``psid``", ":math:`\psi_d`", "d-axis stator flux (state) [p.u.]", ""
       "``psiq``", ":math:`\psi_q`", "q-axis stator flux (state) [p.u.]", ""
       "``psid2``", ":math:`\psi_{d2}`", "d-axis subtransient flux (state) [p.u.]", ""
       "``psiq2``", ":math:`\psi_{q2}`", "q-axis subtransient flux (state) [p.u.]", ""
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)

        # private data
        self._type = "Synchronous_machine"
        self._name = "Synchronous_machine_subtransient_model_Sauer_Pai"

        # States
        self.ns += 6
        self.states.extend(["e_dprim", "e_qprim", "psid", "psiq", "psid2", "psiq2"])
        self.units.extend(["p.u.", "p.u.", "p.u.", "p.u.", "p.u.", "p.u."])
        self.e_dprim = np.array([], dtype=float)
        self.e_qprim = np.array([], dtype=float)
        self.psid = np.array([], dtype=float)
        self.psiq = np.array([], dtype=float)
        self.psid2 = np.array([], dtype=float)
        self.psiq2 = np.array([], dtype=float)

        self._x0.update(
            {
                "delta": 0.5,
                "omega": 0.0,
                "e_dprim": 0.2,
                "e_qprim": 1.0,
                "psid": 1.0,
                "psiq": -0.5,
                "psid2": 1.0,
                "psiq2": -0.5,
                "psv": 0.5,
                "pm": 0.5,
                "Efd": 2.3,
                "Rf": 0.0,
                "Vr": 2.3,
            }
        )

        # Params
        self._params.update(
            {
                "gd1": 1.0,
                "gq1": 1.0,
                "gd2": 1.0,
                "gq2": 1.0,
                "x_l": 0.1,
                "x_dprim": 0.05,
                "x_qprim": 0.1,
                "T_dprim": 8.0,
                "T_qprim": 0.8,
                "x_dsec": 0.01,
                "x_qsec": 0.01,
                "T_dsec": 0.001,
                "T_qsec": 0.001,
            }
        )

        self._descr.update(
            {
                "T_dprim": "d-axis transient time constant",
                "T_qprim": "q-axis transient time constant",
                "x_dprim": "d-axis transient reactance",
                "x_qprim": "q-axis transient reactance",
                "e_dprim": "d-axis voltage behind transient reactance",
                "e_qprim": "q-axis voltage behind transient reactance",
                "T_dsec": "d-axis subtransient time constant",
                "T_qsec": "q-axis subtransient time constant",
                "x_dsec": "d-axis subtransient reactance",
                "x_qsec": "q-axis subtransient reactance",
                "x_l": "leakage reactance",
                "psid": "stator flux in d axis",
                "psiq": "stator flux in q axis",
                "psiq2": "subtransient stator flux in q axis",
                "psid2": "subtransient stator flux in d axis",
            }
        )

        # Parameters
        self.x_l = np.array([], dtype=float)
        self.gd1 = np.array([], dtype=float)
        self.gq1 = np.array([], dtype=float)
        self.gd2 = np.array([], dtype=float)
        self.gq2 = np.array([], dtype=float)
        self.x_dprim = np.array([], dtype=float)
        self.x_qprim = np.array([], dtype=float)
        self.T_dprim = np.array([], dtype=float)
        self.T_qprim = np.array([], dtype=float)
        self.x_dsec = np.array([], dtype=float)
        self.x_qsec = np.array([], dtype=float)
        self.T_dsec = np.array([], dtype=float)
        self.T_qsec = np.array([], dtype=float)

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
            }
        )

        self._init_data()

    def sauer_pai(self, dae: Dae, i_d: ca.SX, i_q: ca.SX):
        """
        Sauer and Pai model.
        Parameters
        ----------
        dae : DAE

        i_d : casadi.SX

        i_q : casadi.SX

        Returns
        -------

        """
        vd = dae.y[self.vre] * np.sin(dae.x[self.delta]) + dae.y[self.vim] * -np.cos(
            dae.x[self.delta]
        )
        vq = dae.y[self.vre] * np.cos(dae.x[self.delta]) + dae.y[self.vim] * np.sin(
            dae.x[self.delta]
        )

        # Air-gap power/torque consumed by the rotor swing (Pe = psi_d I_q - psi_q I_d).
        Pe = dae.x[self.psid] * i_q - dae.x[self.psiq] * i_d

        dae.f[self.e_dprim] = (
            1
            / self.T_qprim
            * (
                -dae.x[self.e_dprim]
                + (self.x_q - self.x_qprim)
                * (
                    i_q
                    - self.gq2 * dae.x[self.psiq2]
                    - (1 - self.gq1) * i_q
                    - self.gq2 * dae.x[self.e_dprim]
                )
            )
        )
        dae.f[self.e_qprim] = (
            1
            / self.T_dprim
            * (
                -dae.x[self.e_qprim]
                - (self.x_d - self.x_dprim)
                * (
                    i_d
                    - self.gd2 * dae.x[self.psid2]
                    - (1 - self.gd1) * i_d
                    + self.gd2 * dae.x[self.e_qprim]
                )
                + self.var_sym(dae, "Efd")
            )
        )
        dae.f[self.psid2] = (
            1
            / self.T_dsec
            * (
                -dae.x[self.psid2]
                + dae.x[self.e_qprim]
                - (self.x_dprim - self.x_l) * i_d
            )
        )
        dae.f[self.psiq2] = (
            1
            / self.T_qsec
            * (
                -dae.x[self.psiq2]
                - dae.x[self.e_dprim]
                - (self.x_qprim - self.x_l) * i_q
            )
        )
        omega_rh = dae.x[self.omega]

        dae.f[self.psid] = (
            2 * np.pi * dae.fn * (self.R_s * i_d + (omega_rh) * dae.x[self.psiq] + vd)
        )
        dae.f[self.psiq] = (
            2 * np.pi * dae.fn * (self.R_s * i_q - (omega_rh) * dae.x[self.psid] + vq)
        )

        return Pe

    def _gd_coeffs(self) -> None:
        """Subtransient coupling coefficients used by both the stator-current
        expressions and the flux ODEs."""
        self.gd1 = (self.x_dsec - self.x_l) / (self.x_dprim - self.x_l)
        self.gq1 = (self.x_qsec - self.x_l) / (self.x_qprim - self.x_l)
        self.gd2 = (1 - self.gd1) / (self.x_dprim - self.x_l)
        self.gq2 = (1 - self.gq1) / (self.x_qprim - self.x_l)

    def input_current(self, dae: Dae) -> Tuple[ca.SX, ca.SX]:
        """Stator currents as inlined explicit expressions of the flux states."""
        self._gd_coeffs()
        i_d = (
            1
            / self.x_dsec
            * (
                -dae.x[self.psid]
                + self.gd1 * dae.x[self.e_qprim]
                + (1 - self.gd1) * dae.x[self.psid2]
            )
        )
        i_q = (
            1
            / self.x_qsec
            * (
                -dae.x[self.psiq]
                - self.gq1 * dae.x[self.e_dprim]
                + (1 - self.gq1) * dae.x[self.psiq2]
            )
        )
        return i_d, i_q

    def electromagnetic(self, dae: Dae):
        """Sauer-Pai (subtransient, stator dynamics) electromagnetic model.
        The stator-current derivation is :meth:`input_current` (overridden by the
        _DAE variant to expose i_d/i_q as private algebraics); the shared flux/
        stator physics and the air-gap power live in :meth:`sauer_pai`."""
        i_d, i_q = self.input_current(dae)
        Pe = self.sauer_pai(dae, i_d, i_q)
        return i_d, i_q, Pe


class Marconato(Synchronous):
    r"""Marconato synchronous machine WITH stator flux dynamics: six
    electromagnetic states, with the subtransient pair kept as EMFs behind
    the subtransient reactances and an additional field-voltage feedthrough
    time constant :math:`T_{AA}` (F. Milano, *Power System Modelling and
    Scripting*, 2010, eqs. 15.16-15.18; the PSID ``MarconatoMachine``).

    Selected in a system file by the class name in the first column::

       Marconato, idx = "SG1", bus = "1", Sn = 100, avr = "AVRSimple", ...

    **Model.** With the derived coefficients

    .. math::

       \gamma_d = \frac{T''_d\, x''_d}{T'_d\, x'_d} \left( x_d - x'_d \right),
       \qquad
       \gamma_q = \frac{T''_q\, x''_q}{T'_q\, x'_q} \left( x_q - x'_q \right),

    the stator currents are explicit in the states,

    .. math::

       i_d = \frac{1}{x''_d} \left( e''_q - \psi_d \right), \qquad
       i_q = \frac{1}{x''_q} \left( -e''_d - \psi_q \right),

    and the rotor-circuit and stator-flux dynamics are

    .. math::

       T'_d \, \dot{e}'_q &= -e'_q - (x_d - x'_d - \gamma_d)\, i_d
           + \left(1 - \frac{T_{AA}}{T'_d}\right) E_{fd} \\
       T'_q \, \dot{e}'_d &= -e'_d + (x_q - x'_q - \gamma_q)\, i_q \\
       T''_d \, \dot{e}''_q &= -e''_q + e'_q - (x'_d - x''_d + \gamma_d)\, i_d
           + \frac{T_{AA}}{T'_d} E_{fd} \\
       T''_q \, \dot{e}''_d &= -e''_d + e'_d + (x'_q - x''_q + \gamma_q)\, i_q \\
       \dot{\psi}_d &= \omega_b \left( R_s i_d + \omega \psi_q + v_d \right) \\
       \dot{\psi}_q &= \omega_b \left( R_s i_q - \omega \psi_d + v_q \right)

    with :math:`\omega_b = 2\pi f_n`, :math:`\omega` the absolute per-unit
    rotor speed, and air-gap power :math:`P_e = \psi_d i_q - \psi_q i_d`.
    It is cross-validated state for state against the PSID
    ``MarconatoMachine`` (which derives the same :math:`\gamma_{d,q}`).
    Rotor motion, exciter and governor come from the shaft, AVR and governor
    strategies.

    **Symbols** (model-specific; :math:`\gamma_d, \gamma_q` are computed from
    the parameters, not inputs):

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``x_dprim``", ":math:`x'_d`", "d-axis transient reactance [p.u.]", "0.1813"
       "``x_qprim``", ":math:`x'_q`", "q-axis transient reactance [p.u.]", "0.25"
       "``x_dsec``", ":math:`x''_d`", "d-axis subtransient reactance [p.u.]", "0.14"
       "``x_qsec``", ":math:`x''_q`", "q-axis subtransient reactance [p.u.]", "0.18"
       "``T_dprim``", ":math:`T'_d`", "d-axis transient time constant [s]", "5.89"
       "``T_qprim``", ":math:`T'_q`", "q-axis transient time constant [s]", "0.6"
       "``T_dsec``", ":math:`T''_d`", "d-axis subtransient time constant [s]", "0.5"
       "``T_qsec``", ":math:`T''_q`", "q-axis subtransient time constant [s]", "0.023"
       "``T_aa``", ":math:`T_{AA}`", "field-voltage feedthrough (additional leakage) time constant [s]", "0"
       "``e_dprim`` / ``e_qprim``", ":math:`e'_d,\ e'_q`", "transient EMFs (states) [p.u.]", ""
       "``e_dsec`` / ``e_qsec``", ":math:`e''_d,\ e''_q`", "subtransient EMFs (states) [p.u.]", ""
       "``psid`` / ``psiq``", ":math:`\psi_d,\ \psi_q`", "stator fluxes (states) [p.u.]", ""
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)

        # private data
        self._type = "Synchronous_machine"
        self._name = "Synchronous_machine_Marconato"

        # States
        self.ns += 6
        self.states.extend(["e_dprim", "e_qprim", "e_dsec", "e_qsec", "psid", "psiq"])
        self.units.extend(["p.u.", "p.u.", "p.u.", "p.u.", "p.u.", "p.u."])
        self.e_dprim = np.array([], dtype=float)
        self.e_qprim = np.array([], dtype=float)
        self.e_dsec = np.array([], dtype=float)
        self.e_qsec = np.array([], dtype=float)
        self.psid = np.array([], dtype=float)
        self.psiq = np.array([], dtype=float)

        self._x0.update(
            {
                "delta": 0.5,
                "omega": 1.0,
                "e_dprim": 0.2,
                "e_qprim": 1.0,
                "e_dsec": 0.2,
                "e_qsec": 1.0,
                "psid": 1.0,
                "psiq": -0.5,
                "psv": 0.5,
                "pm": 0.5,
                "Efd": 2.0,
                "Rf": 0.0,
                "Vr": 2.0,
            }
        )

        # Params
        self._params.update(
            {
                "x_dprim": 0.1813,
                "x_qprim": 0.25,
                "x_dsec": 0.14,
                "x_qsec": 0.18,
                "T_dprim": 5.89,
                "T_qprim": 0.6,
                "T_dsec": 0.5,
                "T_qsec": 0.023,
                "T_aa": 0.0,
            }
        )

        self._descr.update(
            {
                "T_dprim": "d-axis transient time constant",
                "T_qprim": "q-axis transient time constant",
                "x_dprim": "d-axis transient reactance",
                "x_qprim": "q-axis transient reactance",
                "T_dsec": "d-axis subtransient time constant",
                "T_qsec": "q-axis subtransient time constant",
                "x_dsec": "d-axis subtransient reactance",
                "x_qsec": "q-axis subtransient reactance",
                "T_aa": "field-voltage feedthrough time constant",
                "e_dprim": "d-axis transient EMF",
                "e_qprim": "q-axis transient EMF",
                "e_dsec": "d-axis subtransient EMF",
                "e_qsec": "q-axis subtransient EMF",
                "psid": "stator flux in d axis",
                "psiq": "stator flux in q axis",
            }
        )

        # Parameters
        self.x_dprim = np.array([], dtype=float)
        self.x_qprim = np.array([], dtype=float)
        self.x_dsec = np.array([], dtype=float)
        self.x_qsec = np.array([], dtype=float)
        self.T_dprim = np.array([], dtype=float)
        self.T_qprim = np.array([], dtype=float)
        self.T_dsec = np.array([], dtype=float)
        self.T_qsec = np.array([], dtype=float)
        self.T_aa = np.array([], dtype=float)

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
            }
        )

        self._init_data()

    def _gammas(self):
        """Milano's derived coefficients (identical to the PSID constructor)."""
        gamma_d = (
            self.T_dsec
            * self.x_dsec
            / (self.T_dprim * self.x_dprim)
            * (self.x_d - self.x_dprim)
        )
        gamma_q = (
            self.T_qsec
            * self.x_qsec
            / (self.T_qprim * self.x_qprim)
            * (self.x_q - self.x_qprim)
        )
        return gamma_d, gamma_q

    def input_current(self, dae: Dae) -> Tuple[ca.SX, ca.SX]:
        """Stator currents as explicit expressions of the EMF/flux states."""
        i_d = 1 / self.x_dsec * (dae.x[self.e_qsec] - dae.x[self.psid])
        i_q = 1 / self.x_qsec * (-dae.x[self.e_dsec] - dae.x[self.psiq])
        return i_d, i_q

    def electromagnetic(self, dae: Dae):
        i_d, i_q = self.input_current(dae)
        gamma_d, gamma_q = self._gammas()

        vd = dae.y[self.vre] * np.sin(dae.x[self.delta]) + dae.y[self.vim] * -np.cos(
            dae.x[self.delta]
        )
        vq = dae.y[self.vre] * np.cos(dae.x[self.delta]) + dae.y[self.vim] * np.sin(
            dae.x[self.delta]
        )

        Pe = dae.x[self.psid] * i_q - dae.x[self.psiq] * i_d
        efd = self.var_sym(dae, "Efd")

        dae.f[self.e_qprim] = (
            1
            / self.T_dprim
            * (
                -dae.x[self.e_qprim]
                - (self.x_d - self.x_dprim - gamma_d) * i_d
                + (1 - self.T_aa / self.T_dprim) * efd
            )
        )
        dae.f[self.e_dprim] = (
            1
            / self.T_qprim
            * (-dae.x[self.e_dprim] + (self.x_q - self.x_qprim - gamma_q) * i_q)
        )
        dae.f[self.e_qsec] = (
            1
            / self.T_dsec
            * (
                -dae.x[self.e_qsec]
                + dae.x[self.e_qprim]
                - (self.x_dprim - self.x_dsec + gamma_d) * i_d
                + self.T_aa / self.T_dprim * efd
            )
        )
        dae.f[self.e_dsec] = (
            1
            / self.T_qsec
            * (
                -dae.x[self.e_dsec]
                + dae.x[self.e_dprim]
                + (self.x_qprim - self.x_qsec + gamma_q) * i_q
            )
        )
        dae.f[self.psid] = (
            2 * np.pi * dae.fn * (self.R_s * i_d + dae.x[self.omega] * dae.x[self.psiq] + vd)
        )
        dae.f[self.psiq] = (
            2 * np.pi * dae.fn * (self.R_s * i_q - dae.x[self.omega] * dae.x[self.psid] + vq)
        )

        return i_d, i_q, Pe


class SynchronousSubtransientSP6(Synchronous):
    r"""Subtransient Sauer-Pai machine with NEGLECTED stator dynamics: the
    sixth-order model, with the stator as algebraic equations
    (P. W. Sauer and M. A. Pai, *Power System Dynamics and Stability*, 1998).

    Selected in a system file by the class name in the first column::

       SynchronousSubtransientSP6, idx = "SG1", bus = "1", Sn = 300, ...

    **Model.** The rotor-circuit dynamics and the coupling coefficients
    :math:`g_{d1}, g_{q1}, g_{d2}, g_{q2}` are identical to
    :class:`SynchronousSubtransientSP`; the four stator unknowns
    :math:`(i_d, i_q, \psi_d, \psi_q)` are instead defined by the algebraic
    stator block

    .. math::

       0 &= -i_d + \frac{1}{x''_d} \bigl( -\psi_d + g_{d1} e'_q + (1 - g_{d1}) \psi_{d2} \bigr) \\
       0 &= -i_q + \frac{1}{x''_q} \bigl( -\psi_q - g_{q1} e'_d + (1 - g_{q1}) \psi_{q2} \bigr) \\
       0 &= R_s i_d + \omega \psi_q + v_d \\
       0 &= R_s i_q - \omega \psi_d + v_q

    which this class eliminates symbolically (a 4x4 linear solve per machine at
    model-build time); the explicit-DAE variant
    :class:`SynchronousSubtransientSP6DAE` hands the same block to the
    integrator as private algebraic equations instead. :math:`\omega` is the
    absolute per-unit speed, and the air-gap power is
    :math:`P_e = \psi_d i_q - \psi_q i_d`. Rotor motion, exciter and governor
    come from the shaft, AVR and governor strategies.

    **Symbols** (model-specific; :math:`g_{d1}, g_{q1}, g_{d2}, g_{q2}` are
    computed from the reactances, not inputs):

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``x_l``", ":math:`x_l`", "leakage reactance [p.u.]", "0.1"
       "``x_dprim``", ":math:`x'_d`", "d-axis transient reactance [p.u.]", "0.05"
       "``x_qprim``", ":math:`x'_q`", "q-axis transient reactance [p.u.]", "0.1"
       "``T_dprim``", ":math:`T'_d`", "d-axis transient time constant [s]", "8"
       "``T_qprim``", ":math:`T'_q`", "q-axis transient time constant [s]", "0.8"
       "``x_dsec``", ":math:`x''_d`", "d-axis subtransient reactance [p.u.]", "0.01"
       "``x_qsec``", ":math:`x''_q`", "q-axis subtransient reactance [p.u.]", "0.01"
       "``T_dsec``", ":math:`T''_d`", "d-axis subtransient time constant [s]", "0.001"
       "``T_qsec``", ":math:`T''_q`", "q-axis subtransient time constant [s]", "0.001"
       "``gd1`` ``gq1`` ``gd2`` ``gq2``", ":math:`g_{d1}, g_{q1}, g_{d2}, g_{q2}`", "coupling coefficients (derived)", ""
       "``e_dprim``", ":math:`e'_d`", "d-axis transient EMF (state) [p.u.]", ""
       "``e_qprim``", ":math:`e'_q`", "q-axis transient EMF (state) [p.u.]", ""
       "``psid2``", ":math:`\psi_{d2}`", "d-axis subtransient flux (state) [p.u.]", ""
       "``psiq2``", ":math:`\psi_{q2}`", "q-axis subtransient flux (state) [p.u.]", ""
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)

        # private data
        self._type = "Synchronous_machine"
        self._name = "Synchronous_machine_subtransient_model_Sauer_Pai_6th_order"

        # States
        self.ns += 4
        self.states.extend(["e_dprim", "e_qprim", "psid2", "psiq2"])
        self.units.extend(["p.u.", "p.u.", "p.u.", "p.u."])
        self.e_dprim = np.array([], dtype=float)
        self.e_qprim = np.array([], dtype=float)
        self.psid2 = np.array([], dtype=float)
        self.psiq2 = np.array([], dtype=float)

        # finit Newton seed. omega is ABSOLUTE p.u. speed (steady state = 1.0,
        # not 0). Equal Efd/Vr lands in the degenerate d-axis excitation/flux
        # chain (see SP_DAE below), where the per-device finit can converge to a
        # spurious root. Seed in the correct basin: true synchronous speed, delta
        # near its true value, and distinct Efd/Vr to break the symmetry.
        self._x0.update(
            {
                "delta": 0.3,
                "omega": 1.0,
                "e_dprim": 0.2,
                "e_qprim": 1.0,
                "psid2": 1.0,
                "psiq2": -0.5,
                "psv": 0.5,
                "pm": 0.5,
                "Efd": 2.3,
                "Rf": 0.0,
                "Vr": 2.0,
            }
        )

        # Params
        self._params.update(
            {
                "gd1": 1.0,
                "gq1": 1.0,
                "gd2": 1.0,
                "gq2": 1.0,
                "x_l": 0.1,
                "x_dprim": 0.05,
                "x_qprim": 0.1,
                "T_dprim": 8.0,
                "T_qprim": 0.8,
                "x_dsec": 0.01,
                "x_qsec": 0.01,
                "T_dsec": 0.001,
                "T_qsec": 0.001,
            }
        )

        self._descr.update(
            {
                "T_dprim": "d-axis transient time constant",
                "T_qprim": "q-axis transient time constant",
                "x_dprim": "d-axis transient reactance",
                "x_qprim": "q-axis transient reactance",
                "e_dprim": "d-axis voltage behind transient reactance",
                "e_qprim": "q-axis voltage behind transient reactance",
                "T_dsec": "d-axis subtransient time constant",
                "T_qsec": "q-axis subtransient time constant",
                "x_dsec": "d-axis subtransient reactance",
                "x_qsec": "q-axis subtransient reactance",
                "x_l": "leakage reactance",
                "psid2": "subtransient flux in d axis",
                "psiq2": "subtransient flux in q axis",
            }
        )

        # Parameters
        self.x_l = np.array([], dtype=float)
        self.gd1 = np.array([], dtype=float)
        self.gq1 = np.array([], dtype=float)
        self.gd2 = np.array([], dtype=float)
        self.gq2 = np.array([], dtype=float)
        self.x_dprim = np.array([], dtype=float)
        self.x_qprim = np.array([], dtype=float)
        self.T_dprim = np.array([], dtype=float)
        self.T_qprim = np.array([], dtype=float)
        self.x_dsec = np.array([], dtype=float)
        self.x_qsec = np.array([], dtype=float)
        self.T_dsec = np.array([], dtype=float)
        self.T_qsec = np.array([], dtype=float)

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
            }
        )

        self._init_data()

    def sauer_pai_6(self, dae: Dae, i_d: ca.SX, i_q: ca.SX, psid: ca.SX, psiq: ca.SX):
        r"""
        Sauer and Pai model.
        Parameters
        ----------
        dae : DAE

        i_d : casadi.SX

        i_q : casadi.SX

        psid : casadi.SX

        psiq : casadi.SX

        Returns
        -------

        Args:
            psid ():
            psiq ():

        """
        # Air-gap power/torque consumed by the rotor swing (Pe = psi_d I_q - psi_q I_d).
        Pe = psid * i_q - psiq * i_d

        dae.f[self.e_dprim] = (
            1
            / self.T_qprim
            * (
                -dae.x[self.e_dprim]
                + (self.x_q - self.x_qprim)
                * (
                    i_q
                    - self.gq2 * dae.x[self.psiq2]
                    - (1 - self.gq1) * i_q
                    - self.gq2 * dae.x[self.e_dprim]
                )
            )
        )
        dae.f[self.e_qprim] = (
            1
            / self.T_dprim
            * (
                -dae.x[self.e_qprim]
                - (self.x_d - self.x_dprim)
                * (
                    i_d
                    - self.gd2 * dae.x[self.psid2]
                    - (1 - self.gd1) * i_d
                    + self.gd2 * dae.x[self.e_qprim]
                )
                + self.var_sym(dae, "Efd")
            )
        )
        dae.f[self.psid2] = (
            1
            / self.T_dsec
            * (
                -dae.x[self.psid2]
                + dae.x[self.e_qprim]
                - (self.x_dprim - self.x_l) * i_d
            )
        )
        dae.f[self.psiq2] = (
            1
            / self.T_qsec
            * (
                -dae.x[self.psiq2]
                - dae.x[self.e_dprim]
                - (self.x_qprim - self.x_l) * i_q
            )
        )

        return Pe

    def stator_solve(self, dae: Dae):
        """Eliminate the four algebraic stator unknowns (i_d, i_q, psi_d, psi_q)
        by a symbolic 4x4 solve per machine. Returns (i_d, i_q, psid, psiq).
        The _DAE variant overrides this to expose them as private algebraics."""
        self.gd1 = (self.x_dsec - self.x_l) / (self.x_dprim - self.x_l)
        self.gq1 = (self.x_qsec - self.x_l) / (self.x_qprim - self.x_l)
        self.gd2 = (1 - self.gd1) / (self.x_dprim - self.x_l)
        self.gq2 = (1 - self.gq1) / (self.x_qprim - self.x_l)
        i_d = ca.SX.sym("i_d", self.n)
        i_q = ca.SX.sym("i_q", self.n)
        psid = ca.SX.sym("psid", self.n)
        psiq = ca.SX.sym("psiq", self.n)

        for i in range(self.n):
            # Symbolic variables for unknowns
            algs = ca.SX.sym("algs", 4)  # symbolic unknowns

            # Define vd and vq in terms of symbolic variables (using symbolic dae.x and dae.y)
            vd = dae.y[self.vre][i] * ca.sin(dae.x[self.delta][i]) + dae.y[self.vim][
                i
            ] * -ca.cos(dae.x[self.delta][i])
            vq = dae.y[self.vre][i] * ca.cos(dae.x[self.delta][i]) + dae.y[self.vim][
                i
            ] * ca.sin(dae.x[self.delta][i])

            # Define g as a symbolic vector in terms of algs, dae.x, and dae.y
            g = ca.SX(4, 1)
            g[0] = -algs[0] + (1 / self.x_dsec[i]) * (
                -algs[2]
                + self.gd1[i] * dae.x[self.e_qprim][i]
                + (1 - self.gd1[i]) * dae.x[self.psid2][i]
            )
            g[1] = -algs[1] + (1 / self.x_qsec[i]) * (
                -algs[3]
                - self.gq1[i] * dae.x[self.e_dprim][i]
                + (1 - self.gq1[i]) * dae.x[self.psiq2][i]
            )
            # Algebraic stator (neglected stator transients): 0 = R_s*i + ...
            # No 2*pi*f_n factor: for an algebraic constraint (= 0) it is
            # mathematically redundant (ca.solve scales J and g together) and
            # only inflates the per-device finit Jacobian condition number. Uses
            # omega, not 1+omega.
            g[2] = self.R_s[i] * algs[0] + (dae.x[self.omega][i]) * algs[3] + vd
            g[3] = self.R_s[i] * algs[1] - (dae.x[self.omega][i]) * algs[2] + vq

            # Calculate the Jacobian of g with respect to algs
            J = ca.jacobian(g, algs)

            g_eval = ca.substitute(g, algs, ca.DM.zeros(4))

            # Solve J * x = -g symbolically
            sol = ca.solve(J, -g_eval)

            # Assign solutions to variables
            i_d[i] = sol[0]
            i_q[i] = sol[1]
            psid[i] = sol[2]
            psiq[i] = sol[3]

        return i_d, i_q, psid, psiq

    def electromagnetic(self, dae: Dae):
        """Sauer-Pai 6th-order (algebraic stator) electromagnetic model. The four
        stator unknowns come from :meth:`stator_solve` (overridden by the _DAE
        variant to expose them as private algebraics); the shared flux physics and
        the air-gap power live in :meth:`sauer_pai_6`."""
        i_d, i_q, psid, psiq = self.stator_solve(dae)
        Pe = self.sauer_pai_6(dae, i_d, i_q, psid, psiq)
        return i_d, i_q, Pe


class SynchronousSubtransientSP6DAE(SynchronousSubtransientSP6):
    r"""Subtransient Sauer-Pai 6th-order machine expressed as an explicit DAE.

    Identical physics to :class:`SynchronousSubtransientSP6`, but the four stator
    unknowns (``i_d, i_q, psi_d, psi_q``) are declared as device-private
    algebraic variables/equations (``_algebs_int``) and handed to the DAE solver
    rather than symbolically eliminated with a per-instance ``ca.solve``. Serves
    as a parity vehicle for the private-algebraic mechanism: it reproduces
    :class:`SynchronousSubtransientSP6` to integrator tolerance.

    The stator block is *linear* in the unknowns, so the parent's ``ca.solve``
    is the exact solution of ``g = 0``; the DAE integrator converges to the same
    values via a numerical Newton solve per step instead of a closed-form
    expression built once.

    Selected in a system file by the class name in the first column::

       SynchronousSubtransientSP6DAE, idx = "SG1", bus = "1", ...

    **Symbols.** As in :class:`SynchronousSubtransientSP6`, plus the private
    algebraics ``id_alg`` (:math:`i_d`), ``iq_alg`` (:math:`i_q`),
    ``psid_alg`` (:math:`\psi_d`) and ``psiq_alg`` (:math:`\psi_q`).
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)
        self._name = "Synchronous_machine_subtransient_model_Sauer_Pai_6th_order_DAE"

        # Declare the stator currents/fluxes as private algebraic variables.
        # id_alg/iq_alg correspond to the parent's algs[0]/algs[1] and
        # psid_alg/psiq_alg to algs[2]/algs[3]. Extend/update (not assign) so
        # these compose with any AVR-declared privates already registered by
        # Synchronous.__init__.
        machine_privs = ["id_alg", "iq_alg", "psid_alg", "psiq_alg"]
        self._algebs_int.extend(machine_privs)
        self._algebs_int_x0.update(
            {
                "id_alg": 0.5,
                "iq_alg": 0.5,
                "psid_alg": 1.0,
                "psiq_alg": -0.5,
            }
        )
        self._algebs_int_units.update({name: "p.u." for name in machine_privs})
        for name in machine_privs:
            setattr(self, name, np.array([], dtype=float))
        self._descr.update(
            {
                "id_alg": "stator d-axis current (algebraic)",
                "iq_alg": "stator q-axis current (algebraic)",
                "psid_alg": "stator d-axis flux (algebraic)",
                "psiq_alg": "stator q-axis flux (algebraic)",
            }
        )

    def stator_solve(self, dae: Dae):
        """The four stator unknowns are device-private algebraic variables in
        dae.y; write their defining equations and return them, so the integrator
        solves the 4x4 block instead of ca.solve. Inherits SP6's
        :meth:`electromagnetic` and the base orchestration."""
        self.gd1 = (self.x_dsec - self.x_l) / (self.x_dprim - self.x_l)
        self.gq1 = (self.x_qsec - self.x_l) / (self.x_qprim - self.x_l)
        self.gd2 = (1 - self.gd1) / (self.x_dprim - self.x_l)
        self.gq2 = (1 - self.gq1) / (self.x_qprim - self.x_l)

        i_d = dae.y[self.id_alg]
        i_q = dae.y[self.iq_alg]
        psid = dae.y[self.psid_alg]
        psiq = dae.y[self.psiq_alg]

        vd = dae.y[self.vre] * np.sin(dae.x[self.delta]) + dae.y[self.vim] * -np.cos(
            dae.x[self.delta]
        )
        vq = dae.y[self.vre] * np.cos(dae.x[self.delta]) + dae.y[self.vim] * np.sin(
            dae.x[self.delta]
        )

        # The four stator defining equations (cf. SynchronousSubtransientSP6
        # g[0..3]), written into each private's own dae.g slot so the integrator
        # solves the 4x4 block. The flux equations use dae.x[omega], NOT
        # (1 + omega), and carry no 2*pi*f_n factor: for an algebraic constraint
        # (= 0) it is redundant and only inflates the Jacobian condition number.
        dae.g[self.id_alg] = -i_d + (1 / self.x_dsec) * (
            -psid + self.gd1 * dae.x[self.e_qprim] + (1 - self.gd1) * dae.x[self.psid2]
        )
        dae.g[self.iq_alg] = -i_q + (1 / self.x_qsec) * (
            -psiq - self.gq1 * dae.x[self.e_dprim] + (1 - self.gq1) * dae.x[self.psiq2]
        )
        dae.g[self.psid_alg] = self.R_s * i_d + dae.x[self.omega] * psiq + vd
        dae.g[self.psiq_alg] = self.R_s * i_q - dae.x[self.omega] * psid + vq

        return i_d, i_q, psid, psiq


class SynchronousSubtransientSP_DAE(SynchronousSubtransientSP):
    r"""Subtransient Sauer-Pai machine (with stator dynamics) with the stator
    currents exposed as explicit device-private algebraic variables.

    Identical physics to :class:`SynchronousSubtransientSP`, but the stator
    currents ``i_d, i_q`` are declared as private algebraic variables
    (``_algebs_int``) with their defining equations ``0 = -i + <expr>`` handed to
    the DAE solver, rather than inlined as explicit expressions of the flux
    states. Reproduces :class:`SynchronousSubtransientSP` to integrator
    tolerance.

    A parity vehicle for the private-algebraic mechanism: the parent model
    initialises robustly and the defining equations are linear with a trivially
    non-singular Jacobian (index-1).

    Selected in a system file by the class name in the first column::

       SynchronousSubtransientSP_DAE, idx = "SG1", bus = "1", ...

    **Symbols.** As in :class:`SynchronousSubtransientSP`, plus the private
    algebraics ``id_alg`` (:math:`i_d`) and ``iq_alg`` (:math:`i_q`).
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)
        self._name = "Synchronous_machine_subtransient_model_Sauer_Pai_DAE"

        # Extend/update (not assign) so these compose with any AVR-declared
        # privates already registered by Synchronous.__init__.
        machine_privs = ["id_alg", "iq_alg"]
        self._algebs_int.extend(machine_privs)
        self._algebs_int_x0.update({"id_alg": 0.0, "iq_alg": 0.6})
        self._algebs_int_units.update({name: "p.u." for name in machine_privs})

        # The stock SP _x0 sits near a singular point of the per-device finit
        # Jacobian (the d-axis excitation/flux chain Efd-Vr-e_qprim-psid2-psid is
        # degenerate there), which the larger DAE init system cannot tolerate.
        # Break the symmetry with distinct guesses in the same solution basin.
        self._x0.update(
            {
                "delta": 0.3,
                "omega": 0.0,
                "e_dprim": 0.25,
                "e_qprim": 1.1,
                "psid": 0.95,
                "psiq": -0.45,
                "psid2": 0.9,
                "psiq2": -0.4,
                "psv": 0.5,
                "pm": 0.5,
                "Efd": 2.5,
                "Rf": 0.05,
                "Vr": 2.4,
            }
        )
        for name in machine_privs:
            setattr(self, name, np.array([], dtype=float))
        self._descr.update(
            {
                "id_alg": "stator d-axis current (algebraic)",
                "iq_alg": "stator q-axis current (algebraic)",
            }
        )

    def input_current(self, dae: Dae) -> Tuple[ca.SX, ca.SX]:
        """Stator currents as device-private algebraic variables in dae.y, defined
        by 0 = -i + <explicit expression> (the same expression the parent inlines).
        The defining Jacobian dg/di = -1 is trivially non-singular (index-1).
        Inherits SP's :meth:`electromagnetic` and the base orchestration."""
        self._gd_coeffs()

        i_d = dae.y[self.id_alg]
        i_q = dae.y[self.iq_alg]

        dae.g[self.id_alg] = -i_d + (1 / self.x_dsec) * (
            -dae.x[self.psid]
            + self.gd1 * dae.x[self.e_qprim]
            + (1 - self.gd1) * dae.x[self.psid2]
        )
        dae.g[self.iq_alg] = -i_q + (1 / self.x_qsec) * (
            -dae.x[self.psiq]
            - self.gq1 * dae.x[self.e_dprim]
            + (1 - self.gq1) * dae.x[self.psiq2]
        )

        return i_d, i_q


class GENROU(Synchronous):
    r"""Sixth-order round-rotor synchronous machine (PSS/E GENROU): two rotor
    windings per axis, in the K-coefficient form of Gibbard & Vowles 2014,
    Appendix I.5.1, eqs. (11)-(24). A general-purpose machine model (the SEA
    benchmark is one user). States: :math:`\delta, \omega, E'_q, \psi_{kd},
    E'_d, \psi_{kq}`; the stator is algebraic with the transformer voltages and
    the speed dependency of the rotational voltages neglected, and magnetic
    saturation disabled:

    .. math::

        T'_{d0}\dot{E}'_q &= E_{fd} - [K_{1d}E'_q + K_{2d}\psi_{kd} + K_{3d}I_d] \\
        T''_{d0}\dot{\psi}_{kd} &= E'_q - \psi_{kd} - (X'_d - X_a) I_d \\
        T'_{q0}\dot{E}'_d &= K_{1q}E'_d + K_{2q}\psi_{kq} + K_{3q}I_q \\
        T''_{q0}\dot{\psi}_{kq} &= E'_d - \psi_{kq} + (X'_q - X_a) I_q

    with the stator equations
    :math:`v_d = -R_s I_d + X''_q I_q + \psi''_q`,
    :math:`v_q = -R_s I_q - X''_d I_d + \psi''_d`, the subtransient flux
    linkages (19)-(20) and the coupling coefficients (22)/(24). The air-gap
    power follows from the stator equations as
    :math:`P_e = \psi''_d I_q + \psi''_q I_d + (X''_q - X''_d) I_d I_q`.
    The ``+(X'_q - X_a) I_q`` sign in the last differential equation is
    deliberate (see the sign note in :meth:`electromagnetic`): with the stator
    convention above, the q-axis steady state must reproduce ``v_d = X_q I_q``.
    It is independently cross-validated against the PSID GENROU reference
    equations. All reactances/time constants in per unit on the machine MVA
    rating. Rotor motion, exciter and governor come from the shaft, AVR and
    governor strategies; :math:`\omega` is the absolute per-unit speed.

    Selected in a system file by the class name in the first column::

       GENROU, idx = "BPS_2", bus = "201", avr = "AVRST1A", governor = "GOVCONST", pss = "PSSSEA", ...

    **Symbols** (model-specific; base-machine and strategy parameters are
    documented in :class:`Synchronous` and the strategy classes):

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``x_a``", ":math:`X_a`", "stator leakage reactance [p.u.]", "0.15"
       "``x_dprim``", ":math:`X'_d`", "d-axis transient reactance [p.u.]", "0.30"
       "``x_qprim``", ":math:`X'_q`", "q-axis transient reactance [p.u.]", "0.50"
       "``x_dsec``", ":math:`X''_d`", "d-axis subtransient reactance [p.u.]", "0.20"
       "``x_qsec``", ":math:`X''_q`", "q-axis subtransient reactance [p.u.]", "0.20"
       "``T_d0prim``", ":math:`T'_{d0}`", "d-axis transient open-circuit time constant [s]", "8"
       "``T_q0prim``", ":math:`T'_{q0}`", "q-axis transient open-circuit time constant [s]", "1"
       "``T_d0sec``", ":math:`T''_{d0}`", "d-axis subtransient open-circuit time constant [s]", "0.04"
       "``T_q0sec``", ":math:`T''_{q0}`", "q-axis subtransient open-circuit time constant [s]", "0.10"
       "``e_qprim``", ":math:`E'_q`", "q-axis transient EMF (state) [p.u.]", ""
       "``psi_kd``", ":math:`\psi_{kd}`", "d-axis damper-winding flux linkage (state) [p.u.]", ""
       "``e_dprim``", ":math:`E'_d`", "d-axis transient EMF (state) [p.u.]", ""
       "``psi_kq``", ":math:`\psi_{kq}`", "q-axis damper-winding flux linkage (state) [p.u.]", ""
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)

        self._type = "Synchronous_machine"
        self._name = "Synchronous_machine_GENROU"

        self.ns += 4
        self.states.extend(["e_qprim", "psi_kd", "e_dprim", "psi_kq"])
        self.units.extend(["p.u.", "p.u.", "p.u.", "p.u."])
        self.e_qprim = np.array([], dtype=float)
        self.psi_kd = np.array([], dtype=float)
        self.e_dprim = np.array([], dtype=float)
        self.psi_kq = np.array([], dtype=float)

        self._x0.update(
            {
                "delta": 0.1,
                "omega": 1.0,
                "e_qprim": 1.0,
                "psi_kd": 1.0,
                "e_dprim": 0.0,
                "psi_kq": 0.0,
            }
        )

        self._params.update(
            {
                "x_a": 0.15,
                "x_dprim": 0.30,
                "x_qprim": 0.50,
                "x_dsec": 0.20,
                "x_qsec": 0.20,
                "T_d0prim": 8.0,
                "T_q0prim": 1.0,
                "T_d0sec": 0.04,
                "T_q0sec": 0.10,
            }
        )
        self._descr.update(
            {
                "x_a": "stator leakage reactance",
                "x_dprim": "d-axis transient reactance",
                "x_qprim": "q-axis transient reactance",
                "x_dsec": "d-axis subtransient reactance",
                "x_qsec": "q-axis subtransient reactance",
                "T_d0prim": "d-axis transient open-circuit time constant",
                "T_q0prim": "q-axis transient open-circuit time constant",
                "T_d0sec": "d-axis subtransient open-circuit time constant",
                "T_q0sec": "q-axis subtransient open-circuit time constant",
                "e_qprim": "q-axis voltage behind transient reactance",
                "e_dprim": "d-axis voltage behind transient reactance",
                "psi_kd": "d-axis damper winding flux linkage",
                "psi_kq": "q-axis damper winding flux linkage",
            }
        )

        self.x_a = np.array([], dtype=float)
        self.x_dprim = np.array([], dtype=float)
        self.x_qprim = np.array([], dtype=float)
        self.x_dsec = np.array([], dtype=float)
        self.x_qsec = np.array([], dtype=float)
        self.T_d0prim = np.array([], dtype=float)
        self.T_q0prim = np.array([], dtype=float)
        self.T_d0sec = np.array([], dtype=float)
        self.T_q0sec = np.array([], dtype=float)

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
            }
        )

        self._init_data()

    def finit_guess(self, dae: Dae):
        """Operating-point-aware Newton seeds from the power-flow phasors.

        The machine equations have a mirror (saddle) equilibrium at
        delta − π with all EMFs negated; with a uniform delta guess, Newton
        lands in the wrong basin for machines at buses with large voltage
        angles. Seed each instance from the standard phasor construction
        E_q = V + (R_s + j·x_q)·I instead (and the exact steady-state chain
        for the rotor states), which puts the guess next to the physical
        root.
        """
        guesses = []
        for i in range(self.n):
            bus = dae.grid.idx_bus[self.bus[i]]
            v = dae.yinit[2 * bus] + 1j * dae.yinit[2 * bus + 1]
            i_inj = dae.iinit[2 * bus] + 1j * dae.iinit[2 * bus + 1]
            # generator current in machine pu (Sn = Sb convention)
            eq_ph = v + (self.R_s[i] + 1j * self.x_q[i]) * i_inj
            delta = float(np.angle(eq_ph))

            rot = np.exp(-1j * (delta - np.pi / 2))
            v_dq = v * rot
            i_dq = i_inj * rot
            vd, vq = float(v_dq.real), float(v_dq.imag)
            id_, iq = float(i_dq.real), float(i_dq.imag)

            eq1 = vq + self.x_dprim[i] * id_ + self.R_s[i] * iq
            psikd = eq1 - (self.x_dprim[i] - self.x_a[i]) * id_

            k2q = (
                (self.x_q[i] - self.x_qprim[i])
                * (self.x_qprim[i] - self.x_qsec[i])
                / (self.x_qprim[i] - self.x_a[i]) ** 2
            )
            k3q = (
                (self.x_q[i] - self.x_qprim[i])
                * (self.x_qsec[i] - self.x_a[i])
                / (self.x_qprim[i] - self.x_a[i])
            )
            ed1 = (k2q * (self.x_qprim[i] - self.x_a[i]) + k3q) * iq
            psikq = ed1 + (self.x_qprim[i] - self.x_a[i]) * iq

            k1d = 1 + (self.x_d[i] - self.x_dprim[i]) * (
                self.x_dprim[i] - self.x_dsec[i]
            ) / (self.x_dprim[i] - self.x_a[i]) ** 2
            k3d = (
                (self.x_d[i] - self.x_dprim[i])
                * (self.x_dsec[i] - self.x_a[i])
                / (self.x_dprim[i] - self.x_a[i])
            )
            efd = k1d * eq1 + (1 - k1d) * psikd + k3d * id_
            v_t = abs(v)
            p_e = (v * np.conj(i_inj)).real

            seeds = self._seed_values(
                dae, i, delta=delta, eq1=eq1, psikd=psikd, ed1=ed1,
                psikq=psikq, iq=iq, efd=efd, v_t=v_t,
            )
            # Setpoint guesses (consumed by the joint solve).
            self.Pref[i] = p_e
            if hasattr(self, "Vf_ref"):
                self.Vf_ref[i] = v_t + efd / self.KA[i] if hasattr(
                    self, "KA"
                ) else v_t
            guesses.extend(seeds[s] for s in self.states)
        return np.array(guesses, dtype=float)

    def _seed_values(self, dae, i, *, delta, eq1, psikd, ed1, psikq, iq,
                     efd, v_t) -> dict:
        """Map the phasor-derived quantities onto this class's state names;
        AVR/PSS/governor states default to their steady-state values."""
        seeds = {s: self._x0.get(s, 0.0) for s in self.states}
        seeds.update(
            {
                "delta": delta,
                "omega": 1.0,
                "e_qprim": eq1,
                "psi_kd": psikd,
            }
        )
        if "e_dprim" in seeds:
            seeds["e_dprim"] = ed1
            seeds["psi_kq"] = psikq
        if "psi_qsec" in seeds:
            seeds["psi_qsec"] = (self.x_q[i] - self.x_qsec[i]) * iq
        # Exciter chains at their equilibria.
        if "Efd" in seeds:
            seeds["Efd"] = efd
        if "Vtr" in seeds:  # AVRST1A
            seeds["Vtr"] = v_t
            u0 = efd / self.KA[i]
            seeds["Vll1"] = u0
            seeds["Vll2"] = u0
        if "Vr" in seeds and hasattr(self, "KE"):  # AVRAC1A
            seeds["Vr"] = self.KE[i] * efd
            seeds["Vfb"] = self.KF[i] / self.TF[i] * efd
        # PSS states are zero at equilibrium except the washout tracker.
        if "vw" in seeds:
            seeds["vw"] = 0.0
        return seeds

    def _subtransient_flux(self, dae: Dae):
        """psi''_d, psi''_q from eqs. (19)-(20)."""
        c1d = (self.x_dsec - self.x_a) / (self.x_dprim - self.x_a)
        c2d = (self.x_dprim - self.x_dsec) / (self.x_dprim - self.x_a)
        psi2d = c1d * dae.x[self.e_qprim] + c2d * dae.x[self.psi_kd]

        c1q = (self.x_qsec - self.x_a) / (self.x_qprim - self.x_a)
        c2q = (self.x_qprim - self.x_qsec) / (self.x_qprim - self.x_a)
        psi2q = c1q * dae.x[self.e_dprim] + c2q * dae.x[self.psi_kq]
        return psi2d, psi2q

    def input_current(self, dae: Dae) -> Tuple[ca.SX, ca.SX]:
        psi2d, psi2q = self._subtransient_flux(dae)
        i_d = ca.SX.sym("Id", self.n)
        i_q = ca.SX.sym("Iq", self.n)
        for i in range(self.n):
            vd = dae.y[self.vre[i]] * np.sin(dae.x[self.delta[i]]) + dae.y[
                self.vim[i]
            ] * -np.cos(dae.x[self.delta[i]])
            vq = dae.y[self.vre[i]] * np.cos(dae.x[self.delta[i]]) + dae.y[
                self.vim[i]
            ] * np.sin(dae.x[self.delta[i]])
            # Stator eqs. (17)-(18): R_s*Id - X''q*Iq = psi''q - vd
            #                        X''d*Id + R_s*Iq = psi''d - vq
            adq = ca.SX(
                [[self.R_s[i], -self.x_qsec[i]], [self.x_dsec[i], self.R_s[i]]]
            )
            b = ca.vertcat(psi2q[i] - vd, psi2d[i] - vq)
            i_dq = ca.solve(adq, b) * dae.Sb / self.Sn[i]
            i_d[i] = i_dq[0]
            i_q[i] = i_dq[1]
        return i_d, i_q

    def electromagnetic(self, dae: Dae):
        # The rotor-circuit equations consume input_current's output directly;
        # with parameters on the system base (Sn = Sb, the convention used by the
        # shipped systems incl. the SEA benchmark) all base factors are unity.
        i_d, i_q = self.input_current(dae)
        i_d_m, i_q_m = i_d, i_q

        psi2d, psi2q = self._subtransient_flux(dae)

        # Field current, eq. (21)-(22).
        k1d = 1 + (self.x_d - self.x_dprim) * (self.x_dprim - self.x_dsec) / (
            self.x_dprim - self.x_a
        ) ** 2
        k2d = 1 - k1d
        k3d = (self.x_d - self.x_dprim) * (self.x_dsec - self.x_a) / (
            self.x_dprim - self.x_a
        )
        xad_ifd = (
            k1d * dae.x[self.e_qprim] + k2d * dae.x[self.psi_kd] + k3d * i_d_m
        )

        # q-axis excitation, eq. (23)-(24).
        k1q = -(
            1
            + (self.x_q - self.x_qprim)
            * (self.x_qprim - self.x_qsec)
            / (self.x_qprim - self.x_a) ** 2
        )
        k2q = -(1 + k1q)
        k3q = (self.x_q - self.x_qprim) * (self.x_qsec - self.x_a) / (
            self.x_qprim - self.x_a
        )
        xaq_ikq = (
            k1q * dae.x[self.e_dprim] + k2q * dae.x[self.psi_kq] + k3q * i_q_m
        )

        dae.f[self.e_qprim] = (
            self.var_sym(dae, "Efd") - xad_ifd
        ) / self.T_d0prim
        dae.f[self.psi_kd] = (
            dae.x[self.e_qprim]
            - dae.x[self.psi_kd]
            - (self.x_dprim - self.x_a) * i_d_m
        ) / self.T_d0sec
        dae.f[self.e_dprim] = xaq_ikq / self.T_q0prim
        # Sign note: +(X'q − Xa)·iq, NOT the minus suggested by a literal
        # reading of eq. (16). With the stator convention of eq. (17)
        # (vd = +X''q·iq + ψ''q) the q-axis steady state must reproduce
        # vd = Xq·iq; chasing the equilibrium through (20)/(23) forces the
        # plus sign here (the d-axis (14) keeps its minus — its stator
        # equation (18) carries the opposite current sign).
        dae.f[self.psi_kq] = (
            dae.x[self.e_dprim]
            - dae.x[self.psi_kq]
            + (self.x_qprim - self.x_a) * i_q_m
        ) / self.T_q0sec

        # Air-gap power (machine base): from eqs. (12)/(17)-(18).
        Pe = (
            psi2d * i_q_m
            + psi2q * i_d_m
            + (self.x_qsec - self.x_dsec) * i_d_m * i_q_m
        )

        return i_d, i_q, Pe


class GENSAL(GENROU):
    r"""Fifth-order salient-pole synchronous machine (PSS/E GENSAL): two rotor
    windings on the d-axis, one on the q-axis. The d-axis circuits and the
    equations of motion are those of :class:`GENROU`; the q-axis transient pair
    :math:`(E'_d, \psi_{kq})` is replaced by the single subtransient flux
    state :math:`\psi''_q`, in the K-coefficient form of Gibbard & Vowles 2014,
    Appendix I.5.2, eqs. (25)-(26):

    .. math::

        T''_{q0}\,\dot{\psi}''_q = -\psi''_q + (X_q - X''_q) I_q .

    The ``+(X_q - X''_q) I_q`` sign is deliberate (the q-axis steady state must
    give :math:`\psi''_q = (X_q - X''_q) I_q` so that ``v_d = X_q I_q``); it is
    cross-validated against the PSID GENSAL reference equations, which define
    their ``psi_q''`` state with the opposite sign.

    Selected in a system file by the class name in the first column::

       GENSAL, idx = "HPS_1", bus = "101", avr = "AVRST1A", governor = "GOVCONST", ...

    **Symbols.** As in :class:`GENROU`, with the q-axis transient pair
    replaced by:

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``psi_qsec``", ":math:`\psi''_q`", "q-axis subtransient flux linkage (state) [p.u.]", ""
    """

    def __init__(self, avr=None, governor=None, pss=None, shaft=None) -> None:
        super().__init__(avr=avr, governor=governor, pss=pss, shaft=shaft)
        self._name = "Synchronous_machine_GENSAL"

        # Replace the q-axis transient pair by a single psi''_q state.
        for name in ("e_dprim", "psi_kq"):
            idx = self.states.index(name)
            del self.states[idx]
            del self.units[idx]
        self.ns -= 2
        self.ns += 1
        self.states.append("psi_qsec")
        self.units.append("p.u.")
        self.psi_qsec = np.array([], dtype=float)
        self._x0.update({"psi_qsec": 0.0})
        self._descr.update(
            {"psi_qsec": "q-axis subtransient flux linkage (5th-order model)"}
        )

        self._init_data()

    def _subtransient_flux(self, dae: Dae):
        c1d = (self.x_dsec - self.x_a) / (self.x_dprim - self.x_a)
        c2d = (self.x_dprim - self.x_dsec) / (self.x_dprim - self.x_a)
        psi2d = c1d * dae.x[self.e_qprim] + c2d * dae.x[self.psi_kd]
        psi2q = dae.x[self.psi_qsec]
        return psi2d, psi2q

    def electromagnetic(self, dae: Dae):
        # See GENROU.electromagnetic: parameters on system base.
        i_d, i_q = self.input_current(dae)
        i_d_m, i_q_m = i_d, i_q

        psi2d, psi2q = self._subtransient_flux(dae)

        k1d = 1 + (self.x_d - self.x_dprim) * (self.x_dprim - self.x_dsec) / (
            self.x_dprim - self.x_a
        ) ** 2
        k2d = 1 - k1d
        k3d = (self.x_d - self.x_dprim) * (self.x_dsec - self.x_a) / (
            self.x_dprim - self.x_a
        )
        xad_ifd = (
            k1d * dae.x[self.e_qprim] + k2d * dae.x[self.psi_kd] + k3d * i_d_m
        )

        dae.f[self.e_qprim] = (
            self.var_sym(dae, "Efd") - xad_ifd
        ) / self.T_d0prim
        dae.f[self.psi_kd] = (
            dae.x[self.e_qprim]
            - dae.x[self.psi_kd]
            - (self.x_dprim - self.x_a) * i_d_m
        ) / self.T_d0sec
        # Same q-axis sign note as in GENROU: the steady state must
        # give ψ''q = (Xq − X''q)·iq so that vd = Xq·iq.
        dae.f[self.psi_qsec] = (
            -dae.x[self.psi_qsec] + (self.x_q - self.x_qsec) * i_q_m
        ) / self.T_q0sec

        Pe = (
            psi2d * i_q_m
            + psi2q * i_d_m
            + (self.x_qsec - self.x_dsec) * i_d_m * i_q_m
        )

        return i_d, i_q, Pe
