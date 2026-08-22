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
    lead-lag stages, as in Kundur (Power System Stability and Control, 1994).

        Vs(s) = K_stab * [ s*Tw / (1 + s*Tw) ]            # washout (DC block)
                       * [ (1 + s*T1) / (1 + s*T2) ]       # lead-lag 1
                       * [ (1 + s*T3) / (1 + s*T4) ]       # lead-lag 2
                       * domega                            # input: SPEED DEVIATION

    ``host.omega`` is the absolute per-unit rotor speed (= 1.0 at synchronism),
    NOT the deviation. The PSS input is the deviation from nominal,
    ``domega = omega - omega_net`` with ``omega_net = 1`` p.u. (``dae.omega_net``),
    formed explicitly here rather than relying on the washout to subtract the DC
    offset.

    The output 'Vs' is summed into the AVR voltage error. Each block contributes
    one lag-pole state; the two lead-lags (and the washout's high-pass) give the
    output a direct feedthrough on ``domega``, so 'Vs' is declared as a private
    ALGEBRAIC variable (read by the AVR via ``Synchronous.pss_signal`` ->
    ``var_sym('Vs')``).

    Realization (vw, vl1, vl2 are the three lag-pole states):

        domega  = omega - omega_net             ; speed deviation (omega_net = 1 p.u.)
        u       = K_stab * domega
        vw_dot  = (u - vw) / Tw                 ; washout output  w  = u - vw
        vl1_dot = (w - vl1) / T2                ; lead-lag 1 out  y1 = vl1(1-T1/T2) + (T1/T2) w
        vl2_dot = (y1 - vl2) / T4
        0       = -Vs + vl2(1-T3/T4) + (T3/T4) y1

    At equilibrium ``omega = omega_net`` so ``domega = 0`` and
    ``vw = vl1 = vl2 = Vs = 0``: the washout blocks DC, hence the PSS does not
    shift the operating point.
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
    (Gibbard & Vowles 2014, Fig. 23 and eqs. (7)-(10)):

        Vs = sgn·K · [s·Tw/(1+s·Tw)] · Π_{i=1..4} (1+s·Tz_i)/(1+s·Tp_i)
                   · (1 + a·s + b·s²)/((1+s·Tp5)(1+s·Tp6)) · (ω − ω_net)

    with K = De·Kc (De = 20 pu damping gain on machine MVA base, Kc from
    Tables 17-20). The four first-order sections cover the real zero/pole
    chains of eqs. (7)-(9); the quadratic section carries the complex-zero
    pair of eqs. (8) and (10). Unused first-order slots are made exactly
    unity by setting Tz_i = Tp_i; an unused quadratic section is exactly
    unity with a = Tp5+Tp6, b = Tp5·Tp6 (pole-zero cancellation). ``sgn``
    is −1 for a hydro machine operating in pumping mode (HPS_1, Case 5).

    First-order sections are realized as lag state + feedthrough (Tp_i > 0
    required); the quadratic section in controllable canonical form with
    feedthrough c = b/(Tp5·Tp6):

        ẋ1 = x2 ,  Tp5·Tp6·ẋ2 = −x1 − (Tp5+Tp6)·x2 + u
        y  = c·u + (1−c)·x1 + (a − c·(Tp5+Tp6))·x2
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
