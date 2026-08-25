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

r"""Power-system-stabilizer strategies for synchronous machines.

A PSS is selected on the machine line of a system file, e.g.
``pss = "PSSKundur"``; the names accepted at any moment are returned by
``hermess.registered("pss")``. There is no default PSS: a machine without one
supplies no stabilizing signal to its AVR.

Common to all models: the input is the speed deviation
:math:`\Delta\omega = \omega - \omega_{net}` (:math:`\omega` the absolute
per-unit rotor speed, :math:`\omega_{net} = 1` p.u.), and the output
:math:`V_s` is summed into the AVR's voltage error at its summing junction.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from hermess.system import Dae


class PSS(ABC):
    """Abstract base class for Power System Stabilizer models (pluggable strategy).

    A PSS adds a supplementary stabilizing signal 'Vs' to the AVR's voltage
    summing junction (the regulator error becomes ``Vf_ref - Vt + Vs``). Unlike
    the AVR and governor, whose outputs couple directly into the machine, the PSS
    couples into *another strategy* (the AVR). This is kept **host-mediated**: the
    PSS declares 'Vs' as its coupling variable, the host exposes it via
    ``Synchronous.pss_signal`` (which returns 0 when no PSS is present), and each
    AVR reads ``host.pss_signal(dae)`` at its summing junction. The PSS never
    references the AVR directly -- the host is the wiring hub.

    'Vs' may be a differential state or, more typically, a device-private
    algebraic (a washout + lead-lag chain has direct feedthrough on the input, so
    its output is algebraic). Symmetric to :class:`~hermess.devices.avr.AVR`
    and :class:`~hermess.devices.governor.Governor`: the PSS declares
    what states / private algebraics / parameters it needs and the host registers
    them on itself. It reads the machine's **absolute** per-unit speed via
    ``host.omega`` (1.0 at synchronism) and forms the deviation from nominal
    (``dae.omega_net`` = 1 p.u.) itself.

    There is NO default PSS: a machine without one supplies no signal to its AVR.
    """

    @abstractmethod
    def states(self) -> List[str]:
        """Return ordered list of differential-state names."""
        ...

    def algebs(self) -> List[str]:
        """Return ordered list of device-private *algebraic* variable names.

        A washout + lead-lag PSS returns ['Vs'] here (its output has direct
        feedthrough on the speed deviation, hence is algebraic) and writes the
        defining residual ``0 = -Vs + <expr>`` into ``dae.g`` in :meth:`fgcall`.
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

    def setpoints(self) -> Dict[str, float]:
        """Return setpoint names -> defaults. A speed-input PSS has none."""
        return {}

    @abstractmethod
    def fgcall(self, host, dae: Dae) -> None:
        """Write the PSS's differential equations into ``dae.f`` and, if it
        declares private algebraics (e.g. an algebraic 'Vs'), their defining
        residuals into ``dae.g``.

        Args:
            host: The Synchronous machine instance. Access state/algebraic
                  indices via host.vw, host.Vs, etc., parameters via host.K_stab,
                  host.Tw, ..., and the absolute per-unit speed via host.omega
                  (form the deviation as host.omega - dae.omega_net).
            dae: The DAE system object.
        """
        ...


class PSSKundur(PSS):
    r"""Single-input (speed) power system stabilizer: gain, washout, and two
    lead-lag stages (Kundur, *Power System Stability and Control*, 1994).

    Selected on a machine line with ``pss = "PSSKundur"``.

    **Model.** Transfer function
    :math:`V_s = K_{stab} \frac{s T_w}{1 + s T_w} \frac{1 + s T_1}{1 + s T_2}
    \frac{1 + s T_3}{1 + s T_4} \, \Delta\omega` with
    :math:`\Delta\omega = \omega - \omega_{net}`, realized as three lag-pole
    states plus feedthrough:

    .. math::

       u &= K_{stab} \, \Delta\omega \\
       T_w \, \dot{v}_w &= u - v_w, \qquad w = u - v_w \\
       T_2 \, \dot{v}_{l1} &= w - v_{l1}, \qquad
           y_1 = \Bigl(1 - \frac{T_1}{T_2}\Bigr) v_{l1} + \frac{T_1}{T_2} w \\
       T_4 \, \dot{v}_{l2} &= y_1 - v_{l2}, \qquad
           0 = -V_s + \Bigl(1 - \frac{T_3}{T_4}\Bigr) v_{l2} + \frac{T_3}{T_4} y_1

    The washout blocks DC, so at equilibrium
    :math:`v_w = v_{l1} = v_{l2} = V_s = 0` and the PSS does not shift the
    operating point. The output :math:`V_s` has direct feedthrough on
    :math:`\Delta\omega` and is therefore a device-private algebraic variable,
    summed into the AVR voltage error via ``Synchronous.pss_signal``. This
    model has no output limit (compare :class:`PSSSEA`).

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``K_stab``", ":math:`K_{stab}`", "stabilizer gain", "10"
       "``Tw``", ":math:`T_w`", "washout time constant [s]", "10"
       "``T1``", ":math:`T_1`", "lead-lag 1 lead time constant [s]", "0.05"
       "``T2``", ":math:`T_2`", "lead-lag 1 lag time constant [s]", "0.02"
       "``T3``", ":math:`T_3`", "lead-lag 2 lead time constant [s]", "0.05"
       "``T4``", ":math:`T_4`", "lead-lag 2 lag time constant [s]", "0.02"
       "``vw``", ":math:`v_w`", "washout low-pass state [p.u.]", ""
       "``vl1``", ":math:`v_{l1}`", "lead-lag 1 lag state [p.u.]", ""
       "``vl2``", ":math:`v_{l2}`", "lead-lag 2 lag state [p.u.]", ""
       "``Vs``", ":math:`V_s`", "stabilizing signal to the AVR (private algebraic) [p.u.]", ""
    """

    def states(self) -> List[str]:
        return ["vw", "vl1", "vl2"]  # washout + two lead-lag lag-pole states

    def units(self) -> List[str]:
        return ["p.u.", "p.u.", "p.u."]

    def algebs(self) -> List[str]:
        return ["Vs"]  # stabilizing signal = washout/lead-lag feedthrough output

    def algebs_units(self) -> Dict[str, str]:
        return {"Vs": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"Vs": 0.0}

    def params(self) -> Dict[str, float]:
        return {
            "K_stab": 10.0,
            "Tw": 10.0,
            "T1": 0.05,
            "T2": 0.02,
            "T3": 0.05,
            "T4": 0.02,
        }

    def x0(self) -> Dict[str, float]:
        return {"vw": 0.0, "vl1": 0.0, "vl2": 0.0}

    def descriptions(self) -> Dict[str, str]:
        return {
            "K_stab": "stabilizer gain",
            "Tw": "washout time constant",
            "T1": "lead-lag 1 lead time constant",
            "T2": "lead-lag 1 lag time constant",
            "T3": "lead-lag 2 lead time constant",
            "T4": "lead-lag 2 lag time constant",
            "vw": "washout internal (low-pass) state",
            "vl1": "lead-lag 1 lag state",
            "vl2": "lead-lag 2 lag state",
            "Vs": "stabilizing signal to the AVR (algebraic)",
        }

    def fgcall(self, host, dae: Dae) -> None:
        # host.omega is the ABSOLUTE per-unit speed (1.0 at synchronism); the PSS
        # input is the deviation from nominal, omega - omega_net (omega_net = 1).
        u = host.K_stab * (dae.x[host.omega] - dae.omega_net)

        # Washout (high-pass): internal low-pass state vw, output w = u - vw
        dae.f[host.vw] = (u - dae.x[host.vw]) / host.Tw
        w = u - dae.x[host.vw]

        # Lead-lag 1: lag-pole state vl1, output y1 = vl1(1-T1/T2) + (T1/T2) w
        dae.f[host.vl1] = (w - dae.x[host.vl1]) / host.T2
        y1 = dae.x[host.vl1] * (1 - host.T1 / host.T2) + (host.T1 / host.T2) * w

        # Lead-lag 2: lag-pole state vl2, output Vs (algebraic feedthrough)
        dae.f[host.vl2] = (y1 - dae.x[host.vl2]) / host.T4
        dae.g[host.Vs] = (
            -dae.y[host.Vs]
            + dae.x[host.vl2] * (1 - host.T3 / host.T4)
            + (host.T3 / host.T4) * y1
        )


class PSSSEA(PSS):
    r"""Speed-input PSS of the 14-generator South East Australian benchmark
    (Gibbard and Vowles 2014, Fig. 23 and eqs. (7)-(10)).

    Selected on a machine line with ``pss = "PSSSEA"``.

    **Model.** Transfer function

    .. math::

       V_s = \mathrm{sgn} \cdot K_{stab} \cdot \frac{s T_w}{1 + s T_w}
             \cdot \prod_{i=1}^{4} \frac{1 + s T_{z,i}}{1 + s T_{p,i}}
             \cdot \frac{1 + a_q s + b_q s^2}{(1 + s T_{p5})(1 + s T_{p6})}
             \cdot (\omega - \omega_{net})

    with overall gain :math:`K_{stab} = D_e K_c` (:math:`D_e` = 20 p.u.
    damping gain on machine MVA base, :math:`K_c` from Tables 17-20). The four
    first-order sections cover the real zero/pole chains of eqs. (7)-(9); the
    quadratic section carries the complex-zero pair of eqs. (8) and (10).
    Unused first-order slots are exactly unity with
    :math:`T_{z,i} = T_{p,i}`; an unused quadratic section is exactly unity
    with :math:`a_q = T_{p5} + T_{p6}`, :math:`b_q = T_{p5} T_{p6}`.
    :math:`\mathrm{sgn} = -1` for a hydro machine operating in pumping mode.

    Realization: washout and first-order sections as lag state plus
    feedthrough (as in :class:`PSSKundur`; :math:`T_{p,i} > 0` required); the
    quadratic section in controllable canonical form with feedthrough
    :math:`c = b_q/(T_{p5} T_{p6})`:

    .. math::

       \dot{v}_{q1} &= v_{q2}, \qquad
       T_{p5} T_{p6} \, \dot{v}_{q2} = -v_{q1} - (T_{p5} + T_{p6}) v_{q2} + u \\
       y &= c \, u + (1 - c) \, v_{q1} + \bigl(a_q - c \,(T_{p5} + T_{p6})\bigr) v_{q2}

    The output is hard-clipped at the published limit
    :math:`\pm V_s^{max}` (always active, not gated by ``incl_lim``); the
    operating point sits at :math:`V_s = 0` with unit slope, so the
    small-signal behavior is unchanged.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``K_stab``", ":math:`K_{stab}`", "overall gain (:math:`D_e K_c`, machine base)", "10"
       "``Tw``", ":math:`T_w`", "washout time constant [s]", "7.5"
       "``Tz1`` / ``Tp1``", ":math:`T_{z,1}, T_{p,1}`", "section 1 lead / lag time constants [s]", "1e-3"
       "``Tz2`` / ``Tp2``", ":math:`T_{z,2}, T_{p,2}`", "section 2 lead / lag time constants [s]", "1e-3"
       "``Tz3`` / ``Tp3``", ":math:`T_{z,3}, T_{p,3}`", "section 3 lead / lag time constants [s]", "1e-3"
       "``Tz4`` / ``Tp4``", ":math:`T_{z,4}, T_{p,4}`", "section 4 lead / lag time constants [s]", "1e-3"
       "``a_q``", ":math:`a_q`", "quadratic numerator s-coefficient", "2e-4"
       "``b_q``", ":math:`b_q`", "quadratic numerator s^2-coefficient", "1e-8"
       "``Tp5`` / ``Tp6``", ":math:`T_{p5}, T_{p6}`", "quadratic denominator time constants [s]", "1e-4"
       "``sgn``", ":math:`\mathrm{sgn}`", "output sign (-1 when pumping)", "1"
       "``Vs_max``", ":math:`V_s^{max}`", "output limit (hard clip, always active)", "0.1"
       "``vw``", ":math:`v_w`", "washout low-pass state [p.u.]", ""
       "``v1`` / ``v2`` / ``v3`` / ``v4``", ":math:`v_1 \dots v_4`", "first-order section lag states [p.u.]", ""
       "``vq1`` / ``vq2``", ":math:`v_{q1}, v_{q2}`", "quadratic section states [p.u.]", ""
       "``Vs``", ":math:`V_s`", "stabilizing signal to the AVR (private algebraic) [p.u.]", ""
    """

    def states(self) -> List[str]:
        return ["vw", "v1", "v2", "v3", "v4", "vq1", "vq2"]

    def units(self) -> List[str]:
        return ["p.u."] * 7

    def algebs(self) -> List[str]:
        return ["Vs"]

    def algebs_units(self) -> Dict[str, str]:
        return {"Vs": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"Vs": 0.0}

    def params(self) -> Dict[str, float]:
        return {
            "K_stab": 10.0,
            "Tw": 7.5,
            "Tz1": 1e-3, "Tp1": 1e-3,
            "Tz2": 1e-3, "Tp2": 1e-3,
            "Tz3": 1e-3, "Tp3": 1e-3,
            "Tz4": 1e-3, "Tp4": 1e-3,
            "a_q": 2e-4, "b_q": 1e-8,
            "Tp5": 1e-4, "Tp6": 1e-4,
            "sgn": 1.0,
            "Vs_max": 0.1,
        }

    def x0(self) -> Dict[str, float]:
        return {s: 0.0 for s in self.states()}

    def descriptions(self) -> Dict[str, str]:
        return {
            "K_stab": "overall PSS gain De*Kc (machine base)",
            "Tw": "washout time constant",
            "a_q": "quadratic numerator s-coefficient",
            "b_q": "quadratic numerator s^2-coefficient",
            "sgn": "output sign (-1 when pumping)",
            "Vs": "stabilising signal into the AVR",
        }

    def setpoints(self) -> Dict[str, float]:
        return {}

    def fgcall(self, host, dae: Dae) -> None:
        u = host.sgn * host.K_stab * (dae.x[host.omega] - dae.omega_net)

        # Washout sTw/(1+sTw): vw tracks u through the lag; w is the deviation.
        dae.f[host.vw] = (u - dae.x[host.vw]) / host.Tw
        w = u - dae.x[host.vw]

        # Four first-order lead-lag sections (lag state + feedthrough).
        for state, tz, tp in (
            (host.v1, host.Tz1, host.Tp1),
            (host.v2, host.Tz2, host.Tp2),
            (host.v3, host.Tz3, host.Tp3),
            (host.v4, host.Tz4, host.Tp4),
        ):
            dae.f[state] = (w - dae.x[state]) / tp
            w = dae.x[state] * (1 - tz / tp) + (tz / tp) * w

        # Quadratic section (1 + a·s + b·s²)/((1+s·Tp5)(1+s·Tp6)).
        t56 = host.Tp5 * host.Tp6
        c = host.b_q / t56
        dae.f[host.vq1] = dae.x[host.vq2]
        dae.f[host.vq2] = (
            -dae.x[host.vq1] - (host.Tp5 + host.Tp6) * dae.x[host.vq2] + w
        ) / t56
        y = (
            c * w
            + (1 - c) * dae.x[host.vq1]
            + (host.a_q - c * (host.Tp5 + host.Tp6)) * dae.x[host.vq2]
        )

        # Published output limit (+/-0.1 pu in the SEA benchmark), hard-clipped.
        # The operating point sits at Vs = 0 with unit slope, so the small-signal
        # behaviour is unchanged while the time-domain signal stays bounded.
        import casadi as ca

        y = ca.fmax(ca.fmin(y, host.Vs_max), -host.Vs_max)
        dae.g[host.Vs] = -dae.y[host.Vs] + y


PSS_REGISTRY: Dict[str, type] = {
    "PSSKundur": PSSKundur,
    "PSSSEA": PSSSEA,
}
