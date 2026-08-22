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


class AVR(ABC):
    """Abstract base class for Automatic Voltage Regulator models.

    Every AVR must expose 'Efd' -- the field-voltage coupling variable consumed
    by the electromagnetic equations of the synchronous machine. 'Efd' may be
    declared either as a differential ``state`` (when the exciter is a pure lag,
    e.g. IEEEDC1A) or as a device-private ``algeb`` (when the exciter has a
    direct-feedthrough block such as a lead-lag, so its output is algebraic; see
    AVRKundur). The host resolves 'Efd' wherever it lives via
    ``Synchronous.var_sym`` -- the machine equations are agnostic to the choice.

    The AVR does NOT own state arrays or DAE indices. It declares what states,
    private algebraics, parameters, noise values, etc. it needs, and the host
    Synchronous machine registers them on itself.
    """

    @abstractmethod
    def states(self) -> List[str]:
        """Return ordered list of differential-state names."""
        ...

    def algebs(self) -> List[str]:
        """Return ordered list of device-private *algebraic* variable names.

        Default empty: most AVRs are pure-lag exciters whose output 'Efd' is a
        state. An exciter with a direct-feedthrough (lead-lag) block returns
        ['Efd'] here instead of listing it in :meth:`states`, and writes its
        defining residual ``0 = -Efd + <expr>`` into ``dae.g`` in :meth:`fgcall`.
        These ride the device-private-algebraic mechanism (``_algebs_int``).
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
        """Return setpoint names -> defaults (e.g., Vf_ref)."""
        ...

    @abstractmethod
    def fgcall(self, host, dae: Dae) -> None:
        """Write the AVR's differential equations into ``dae.f`` and, if the AVR
        declares private algebraics, their defining residuals into ``dae.g``.

        Args:
            host: The Synchronous machine instance. Access state/algebraic
                  indices via host.Efd, host.Rf, etc. and parameters via
                  host.KA, etc.
            dae: The DAE system object.
        """
        ...


class IEEEDC1A(AVR):
    """IEEEDC1A exciter and AVR model as presented in Power System Dynamics
    and Stability by P.W. Sauer and M.A. Pai, 2006. (page 100)

    States: Efd, Rf, Vr  (3 states)
    """

    def states(self) -> List[str]:
        return ["Efd", "Rf", "Vr"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "KA": 200.0,
            "TA": 0.015,
            "KF": 1.0,
            "TF": 0.1,
            "KE": 1.0,
            "TE": 0.04,
            "Vr_max": 5.0,
            "Vr_min": 0.0,
        }

    def x0(self) -> Dict[str, float]:
        return {"Efd": 1.5, "Rf": 0.2, "Vr": 1.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "voltage regulator gain",
            "TA": "voltage regulator time constant",
            "KF": "stabilizer gain",
            "TF": "stabilizer time constant",
            "KE": "exciter field constant without saturation",
            "TE": "exciter time constant",
            "Efd": "internal field voltage",
            "Rf": "feedback rate",
            "Vr": "pilot exciter voltage",
            "Vf_ref": "exciter set point voltage",
            "Vr_min": "Exciter minimal voltage",
            "Vr_max": "Exciter maximal voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        dae.f[host.Efd] = 1 / host.TE * (-(host.KE) * dae.x[host.Efd] + dae.x[host.Vr])
        dae.f[host.Rf] = (
            1 / host.TF * (-dae.x[host.Rf] + host.KF / host.TF * dae.x[host.Efd])
        )
        dae.f[host.Vr] = (
            dae.s[host.Vr]
            * 1
            / host.TA
            * (
                -dae.x[host.Vr]
                + host.KA * dae.x[host.Rf]
                - host.KA * host.KF / host.TF * dae.x[host.Efd]
                + host.KA
                * (
                    host.Vf_ref
                    - sqrt((dae.y[host.vre]) ** 2 + (dae.y[host.vim]) ** 2)
                    + host.pss_signal(dae)
                )
            )
        )


class AVRKundur_Filter(AVR):
    """AVR model used in Kundur's book (Power System Stability and Control, 1994)
    for the 2-area system. A filter is added to the AVR output to prevent unrealistic fast dynamics and improve numerical stability.
    """

    def states(self) -> List[str]:
        return ["Efd", "Vl", "Vtr"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "KA": 200.0,
            "TA": 1,
            "TB": 10,
            "TR": 0.01,
            "Tfd": 0.01,
            "Efd_max": 5.0,
            "Efd_min": 0.0,
        }

    def x0(self) -> Dict[str, float]:
        return {"Efd": 1.5, "Vl": 1.5, "Vtr": 1.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "voltage regulator gain",
            "TA": "AVR lead time constant",
            "TB": "AVR lag time constant",
            "TR": "Transducer time constant",
            "Tfd": "exciter field filter time constant",
            "Efd_max": "Maximum field voltage",
            "Efd_min": "Minimum field voltage",
            "Efd": "internal field voltage",
            "Vl": "Lead lag voltage state",
            "Vtr": "Transducer voltage state",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        # Lead-lag block
        dae.f[host.Vtr] = (
            1
            / host.TR
            * (-dae.x[host.Vtr] + sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2))
        )

        dae.f[host.Vl] = (
            1
            / host.TB
            * (
                -dae.x[host.Vl]
                + host.KA
                * (host.Vf_ref - dae.x[host.Vtr] + host.pss_signal(dae))
            )
        )
        dae.f[host.Efd] = (
            1
            / host.Tfd
            * (
                -dae.x[host.Efd]
                + dae.x[host.Vl]
                + host.TA
                / host.TB
                * (
                    host.KA
                    * (-dae.x[host.Vtr] + host.Vf_ref + host.pss_signal(dae))
                )
                - host.TA / host.TB * (dae.x[host.Vl])
            )
        )


class AVRKundur(AVR):
    r"""Kundur 2-area AVR as a transducer + lead-lag, with the field voltage
    'Efd' declared as a device-private ALGEBRAIC variable.

    The lead-lag

        Efd = KA * (1 + s*TA) / (1 + s*TB) * (Vf_ref - Vtr)

    is proper but not strictly proper, so its output has a direct feedthrough
    and is genuinely algebraic. It is realized as one lag-pole state ``Vl`` plus
    the algebraic output:

        Vtr_dot = (1/TR) (-Vtr + |V|)                            # transducer
        Vl_dot  = (1/TB) (-Vl + KA (Vf_ref - Vtr))               # lag pole state
        0       = -Efd + Vl (1 - TA/TB) + (TA/TB) KA (Vf_ref - Vtr)   # Efd algebraic

    The third line is the lead feedthrough ``D = TA/TB``;
    ``Vl(1-TA/TB) + (TA/TB)KA(Vf_ref-Vtr) = KA(1+sTA)/(1+sTB)(Vf_ref-Vtr)``.

    'Efd' is exposed via :meth:`algebs` (not :meth:`states`) and rides the
    device-private-algebraic mechanism; the host reads it through
    ``Synchronous.var_sym('Efd')``.
    """

    def states(self) -> List[str]:
        return ["Vl", "Vtr"]  # lag pole state + transducer state (no Efd)

    def units(self) -> List[str]:
        return ["p.u.", "p.u."]

    def algebs(self) -> List[str]:
        return ["Efd"]  # field voltage = lead-lag algebraic output (feedthrough)

    def algebs_units(self) -> Dict[str, str]:
        return {"Efd": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"Efd": 1.5}

    def params(self) -> Dict[str, float]:
        return {
            "KA": 200.0,
            "TA": 1,
            "TB": 10,
            "TR": 0.01,
            "Efd_max": 5.0,
            "Efd_min": 0.0,
        }

    def x0(self) -> Dict[str, float]:
        return {"Vl": 1.5, "Vtr": 1.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "voltage regulator gain",
            "TA": "AVR lead time constant",
            "TB": "AVR lag time constant",
            "TR": "Transducer time constant",
            "Efd_max": "Maximum field voltage",
            "Efd_min": "Minimum field voltage",
            "Efd": "internal field voltage (algebraic lead-lag output)",
            "Vl": "lag pole state",
            "Vtr": "Transducer voltage state",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        Vt = sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2)

        # Transducer lag (differential)
        dae.f[host.Vtr] = 1 / host.TR * (-dae.x[host.Vtr] + Vt)

        # Lag pole state of the lead-lag (differential)
        dae.f[host.Vl] = (
            1 / host.TB * (-dae.x[host.Vl] + host.KA * (host.Vf_ref - dae.x[host.Vtr] + host.pss_signal(dae)))
        )

        # Field voltage: algebraic lead-lag output (lead feedthrough TA/TB),
        # residual 0 = -Efd + <expr>.
        dae.g[host.Efd] = (
            -dae.y[host.Efd]
            + dae.x[host.Vl] * (1 - host.TA / host.TB)
            + (host.TA / host.TB) * host.KA * (host.Vf_ref - dae.x[host.Vtr] + host.pss_signal(dae))
        )


class AVRKundur_NoTGR(AVR):
    r"""AVRKundur with the transient gain reduction (the lead-lag
    ``(1+sTA)/(1+sTB)``) removed: a plain high-gain static exciter with only a
    terminal-voltage transducer.

        Efd = KA * (Vf_ref - Vtr),   Vtr = Vt / (1 + s*TR)

    States: ``Vtr`` (transducer). ``Efd`` is the algebraic output
    ``KA*(Vf_ref - Vtr)``, an instantaneous gain on the transduced error, so it
    is declared as a private algebraic (read by the machine via
    ``Synchronous.var_sym('Efd')``). Parameters: ``KA``, ``TR``.

    With a high ``KA`` and no TGR this exciter reduces the damping of the
    electromechanical modes, the classic setting in which a power system
    stabilizer (PSS) is needed to restore damping. The PSS signal enters at the
    summing junction via ``host.pss_signal(dae)`` (0 when no PSS is attached).
    """

    def states(self) -> List[str]:
        return ["Vtr"]  # terminal-voltage transducer state

    def units(self) -> List[str]:
        return ["p.u."]

    def algebs(self) -> List[str]:
        return ["Efd"]  # field voltage = static gain on the transduced error

    def algebs_units(self) -> Dict[str, str]:
        return {"Efd": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"Efd": 1.5}

    def params(self) -> Dict[str, float]:
        return {
            "KA": 200.0,
            "TR": 0.02,
            "Efd_max": 5.0,
            "Efd_min": 0.0,
        }

    def x0(self) -> Dict[str, float]:
        return {"Vtr": 1.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "voltage regulator gain",
            "TR": "Transducer time constant",
            "Efd_max": "Maximum field voltage",
            "Efd_min": "Minimum field voltage",
            "Efd": "internal field voltage (algebraic static-gain output)",
            "Vtr": "Transducer voltage state",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        Vt = sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2)

        # Transducer lag (differential)
        dae.f[host.Vtr] = 1 / host.TR * (-dae.x[host.Vtr] + Vt)

        # Field voltage: static gain on the transduced error (algebraic).
        dae.g[host.Efd] = -dae.y[host.Efd] + host.KA * (
            host.Vf_ref - dae.x[host.Vtr] + host.pss_signal(dae)
        )


class AVRKundur_ODE(AVR):
    r"""AVR model used in Kundur's book (Power System Stability and Control, 1994)
    for the 2-area system example with transient gain reduction.

    All-ODE realization of the transducer + lead-lag controller: loop transfer
    function ``KA (1+sTA)/(1+sTB)`` on the error ``e = Vf_ref - Vtr`` with DC gain
    ``KA``, realizing the lead as a derivative of the measurement. States are
    ``Efd, Vtr`` (``Efd`` is a differential state via the ``TB`` lag). The
    setpoint-derivative term ``KA*TA*dVf_ref/dt`` is omitted; it is zero for a
    constant ``Vf_ref``.
    """

    def states(self) -> List[str]:
        return ["Efd", "Vtr"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "KA": 200.0,
            "TA": 0.015,
            "TB": 0.02,
            "TR": 0.01,
            "Efd_max": 5.0,
            "Efd_min": 0.0,
        }

    def x0(self) -> Dict[str, float]:
        return {"Efd": 1.5, "Vtr": 1.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "voltage regulator gain",
            "TA": "AVR lead time constant",
            "TB": "AVR lag time constant",
            "TR": "Transducer time constant",
            "Efd_max": "Maximum field voltage",
            "Efd_min": "Minimum field voltage",
            "Efd": "internal field voltage",
            "Vl": "Lead lag voltage state",
            "Vtr": "Transducer voltage state",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        # Lead-lag block
        dae.f[host.Vtr] = (
            1
            / host.TR
            * (-dae.x[host.Vtr] + sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2))
        )

        dae.f[host.Efd] = (
            1
            / host.TB
            * (
                -dae.x[host.Efd]
                + (
                    host.KA
                    * (-dae.x[host.Vtr] + host.Vf_ref + host.pss_signal(dae))
                )
                - (host.TA * host.KA)
                / host.TR
                * (-dae.x[host.Vtr] + sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2))
            )
        )


class SEXST(AVR):
    """AVR model used in Kundur's book (Power System Stability and Control, 1994)
    for the 2-area system example with transient gain reduction.
    """

    def states(self) -> List[str]:
        return ["Efd"]

    def units(self) -> List[str]:
        return ["p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "KA": 200.0,
            "TE": 0.1,
            "Efd_max": 5.0,
            "Efd_min": 0.0,
        }

    def x0(self) -> Dict[str, float]:
        return {"Efd": 1.5}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "voltage regulator gain",
            "TE": "Exciter time constant",
            "Efd_max": "Maximum field voltage",
            "Efd_min": "Minimum field voltage",
            "Efd": "internal field voltage",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        dae.f[host.Efd] = (
            1
            / host.TE
            * (
                -dae.x[host.Efd]
                + host.KA
                * (
                    host.Vf_ref
                    - sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2)
                    + host.pss_signal(dae)
                )
            )
        )


class AVRST1A(AVR):
    """IEEE Std 421.5 ST1A static exciter (small-signal form, no limits).

    As used by the 14-generator South East Australian benchmark
    (Gibbard & Vowles 2014, Fig. 20 / Tables 16 and 26):

        Vc   = Vt / (1 + s·Tr)                     (transducer)
        y1   = (1 + s·TC)/(1 + s·TB)  · (Vf_ref − Vc + Vs)
        y2   = (1 + s·TC1)/(1 + s·TB1) · y1        (second lead-lag)
        Efd  = KA/(1 + s·TA) · y2

    Lead-lags are realized as a lag state plus direct feedthrough, so TB and
    TB1 must be > 0; a unity block is obtained exactly with TC == TB (and the
    SEA build uses a tiny equal pair when the data gives 0/0). Tr = 0 in the
    data is approximated by a small transducer lag (1e-4 s, a parasitic pole
    at 10⁴ rad/s, far above the rotor-mode range).
    """

    def states(self) -> List[str]:
        return ["Vtr", "Vll1", "Vll2", "Efd"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u.", "p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "KA": 300.0,
            "TA": 0.05,
            "Tr": 1e-4,
            "TB": 1.0,
            "TC": 1.0,
            "TB1": 1e-4,
            "TC1": 1e-4,
        }

    def x0(self) -> Dict[str, float]:
        return {"Vtr": 1.0, "Vll1": 0.01, "Vll2": 0.01, "Efd": 2.0}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "regulator gain",
            "TA": "regulator time constant",
            "Tr": "voltage transducer time constant",
            "TB": "first lead-lag denominator time constant",
            "TC": "first lead-lag numerator time constant",
            "TB1": "second lead-lag denominator time constant",
            "TC1": "second lead-lag numerator time constant",
            "Vtr": "transducer output",
            "Vll1": "first lead-lag lag state",
            "Vll2": "second lead-lag lag state",
            "Efd": "field voltage",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        v_t = sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2)
        dae.f[host.Vtr] = (v_t - dae.x[host.Vtr]) / host.Tr

        u0 = host.Vf_ref - dae.x[host.Vtr] + host.pss_signal(dae)

        dae.f[host.Vll1] = (u0 - dae.x[host.Vll1]) / host.TB
        y1 = dae.x[host.Vll1] * (1 - host.TC / host.TB) + (host.TC / host.TB) * u0

        dae.f[host.Vll2] = (y1 - dae.x[host.Vll2]) / host.TB1
        y2 = dae.x[host.Vll2] * (1 - host.TC1 / host.TB1) + (host.TC1 / host.TB1) * y1

        dae.f[host.Efd] = (host.KA * y2 - dae.x[host.Efd]) / host.TA


class AVRAC1A(AVR):
    """IEEE Std 421.5 AC1A exciter (small-signal form, no limits/saturation).

    As used by the 14-generator South East Australian benchmark
    (Gibbard & Vowles 2014, Fig. 21 / Tables 16 and 27); exciter saturation,
    armature reaction and rectifier regulation are neglected (KC = KD = 0),
    and the lead-lag is unity (TB = TC = 0 in the data):

        Vf   = s·KF/(1 + s·TF) · Efd               (rate feedback)
        Vr   = KA/(1 + s·TA) · (Vf_ref − Vt + Vs − Vf)
        TE · dEfd/dt = Vr − KE·Efd                 (rotating exciter)

    The data has Tr = 0, so the terminal voltage is used unfiltered.
    """

    def states(self) -> List[str]:
        return ["Vr", "Efd", "Vfb"]

    def units(self) -> List[str]:
        return ["p.u.", "p.u.", "p.u."]

    def params(self) -> Dict[str, float]:
        return {
            "KA": 400.0,
            "TA": 0.02,
            "KE": 1.0,
            "TE": 1.0,
            "KF": 0.03,
            "TF": 1.0,
        }

    def x0(self) -> Dict[str, float]:
        return {"Vr": 2.0, "Efd": 2.0, "Vfb": 0.05}

    def descriptions(self) -> Dict[str, str]:
        return {
            "KA": "regulator gain",
            "TA": "regulator time constant",
            "KE": "exciter constant",
            "TE": "exciter time constant",
            "KF": "rate feedback gain",
            "TF": "rate feedback time constant",
            "Vr": "regulator output",
            "Efd": "field voltage",
            "Vfb": "rate feedback filter state",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 2.0}

    def fgcall(self, host, dae: Dae) -> None:
        from hermess.devices.device import sqrt

        v_t = sqrt(dae.y[host.vre] ** 2 + dae.y[host.vim] ** 2)

        # Washout realization of the rate feedback s·KF/(1+s·TF):
        # Vf = KF/TF·Efd − Vfb with Vfb tracking KF/TF·Efd through lag TF.
        v_f = host.KF / host.TF * dae.x[host.Efd] - dae.x[host.Vfb]
        dae.f[host.Vfb] = v_f / host.TF

        u0 = host.Vf_ref - v_t + host.pss_signal(dae) - v_f
        dae.f[host.Vr] = (host.KA * u0 - dae.x[host.Vr]) / host.TA
        dae.f[host.Efd] = (dae.x[host.Vr] - host.KE * dae.x[host.Efd]) / host.TE


AVR_REGISTRY: Dict[str, type] = {
    "IEEEDC1A": IEEEDC1A,
    "AVRKundur_Filter": AVRKundur_Filter,
    "AVRKundur": AVRKundur,
    "AVRKundur_NoTGR": AVRKundur_NoTGR,
    "AVRKundur_ODE": AVRKundur_ODE,
    "SEXST": SEXST,
    "AVRST1A": AVRST1A,
    "AVRAC1A": AVRAC1A,
}
