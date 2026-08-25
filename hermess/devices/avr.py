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

"""Automatic voltage regulator (exciter) strategies for synchronous machines.

An AVR is selected on the machine line of a system file, e.g.
``avr = "SEXST"``; the names accepted at any moment are returned by
``hermess.registered("avr")``. Every model below documents its differential
(and, where applicable, algebraic) equations and a table mapping the code
parameter names to the mathematical symbols used in those equations.

Common to all models: :math:`V_t = |\bar{v}_n|` is the machine
terminal-voltage magnitude, :math:`V_s` the power-system-stabilizer signal
(0 when no PSS is attached), :math:`V_{ref}` the voltage setpoint computed by
the initialization, and :math:`E_{fd}` the field voltage consumed by the
machine's electromagnetic equations.
"""

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
    r"""IEEE DC1A rotating exciter with stabilizing rate feedback
    (P. W. Sauer and M. A. Pai, *Power System Dynamics and Stability*, p. 100).

    Selected on a machine line with ``avr = "IEEEDC1A"``.

    **Model.**

    .. math::

       T_E \, \dot{E}_{fd} &= -K_E \, E_{fd} + V_r \\
       T_F \, \dot{R}_f &= -R_f + \frac{K_F}{T_F} E_{fd} \\
       T_A \, \dot{V}_r &= -V_r + K_A \Bigl( R_f - \frac{K_F}{T_F} E_{fd}
                            + V_{ref} - V_t + V_s \Bigr)

    with :math:`V_t = |\bar{v}_n|` and :math:`V_s` the stabilizer signal. With
    ``incl_lim`` the :math:`V_r` equation is multiplied by the anti-windup
    switch that freezes the regulator at :math:`V_r^{max,min}`.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "voltage regulator gain", "200"
       "``TA``", ":math:`T_A`", "voltage regulator time constant [s]", "0.015"
       "``KF``", ":math:`K_F`", "rate-feedback (stabilizer) gain", "1"
       "``TF``", ":math:`T_F`", "rate-feedback time constant [s]", "0.1"
       "``KE``", ":math:`K_E`", "exciter field constant (no saturation)", "1"
       "``TE``", ":math:`T_E`", "exciter time constant [s]", "0.04"
       "``Vr_max`` / ``Vr_min``", ":math:`V_r^{max,min}`", "regulator limits (with ``incl_lim``)", "5 / 0"
       "``Efd``", ":math:`E_{fd}`", "field voltage (state) [p.u.]", ""
       "``Rf``", ":math:`R_f`", "rate-feedback state [p.u.]", ""
       "``Vr``", ":math:`V_r`", "pilot-exciter (regulator) voltage (state) [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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
    r""":class:`AVRKundur` with an additional first-order filter on the exciter
    output, which removes the algebraic feedthrough (all states differential)
    and damps unrealistically fast dynamics.

    Selected on a machine line with ``avr = "AVRKundur_Filter"``.

    **Model.**

    .. math::

       T_R \, \dot{V}_{tr} &= -V_{tr} + V_t \\
       T_B \, \dot{V}_l &= -V_l + K_A \, e \\
       T_{fd} \, \dot{E}_{fd} &= -E_{fd} + V_l
            + \frac{T_A}{T_B} \left( K_A \, e - V_l \right)

    with the error :math:`e = V_{ref} - V_{tr} + V_s`,
    :math:`V_t = |\bar{v}_n|`, and :math:`V_s` the stabilizer signal. The
    first two lines are the transducer and the lag pole of the lead-lag; the
    third passes the lead-lag output (lag state plus feedthrough
    :math:`T_A/T_B`) through the output filter :math:`T_{fd}`.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "voltage regulator gain", "200"
       "``TA``", ":math:`T_A`", "lead time constant [s]", "1"
       "``TB``", ":math:`T_B`", "lag time constant [s]", "10"
       "``TR``", ":math:`T_R`", "transducer time constant [s]", "0.01"
       "``Tfd``", ":math:`T_{fd}`", "exciter output filter time constant [s]", "0.01"
       "``Efd_max`` / ``Efd_min``", ":math:`E_{fd}^{max,min}`", "field-voltage limits (with ``incl_lim``)", "5 / 0"
       "``Efd``", ":math:`E_{fd}`", "field voltage (state) [p.u.]", ""
       "``Vl``", ":math:`V_l`", "lag-pole state [p.u.]", ""
       "``Vtr``", ":math:`V_{tr}`", "transducer state [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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
    r"""Kundur two-area AVR: transducer plus lead-lag (transient gain
    reduction), with the field voltage as an algebraic output
    (Kundur, *Power System Stability and Control*, 1994, two-area example).

    Selected on a machine line with ``avr = "AVRKundur"``.

    **Model.** The lead-lag
    :math:`E_{fd} = K_A \frac{1 + s T_A}{1 + s T_B} (V_{ref} - V_{tr} + V_s)`
    is proper but not strictly proper, so its output has a direct feedthrough
    and is genuinely algebraic. It is realized as one lag-pole state
    :math:`V_l` plus the algebraic output:

    .. math::

       T_R \, \dot{V}_{tr} &= -V_{tr} + V_t \\
       T_B \, \dot{V}_l &= -V_l + K_A \left( V_{ref} - V_{tr} + V_s \right) \\
       0 &= -E_{fd} + \Bigl(1 - \frac{T_A}{T_B}\Bigr) V_l
            + \frac{T_A}{T_B} K_A \left( V_{ref} - V_{tr} + V_s \right)

    with :math:`V_t = |\bar{v}_n|` and :math:`V_s` the stabilizer signal. The
    third line is the lead feedthrough :math:`D = T_A/T_B`. ``Efd`` is exposed
    via :meth:`algebs` (not :meth:`states`) and rides the
    device-private-algebraic mechanism; the host machine reads it through
    ``Synchronous.var_sym('Efd')``.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "voltage regulator gain", "200"
       "``TA``", ":math:`T_A`", "lead time constant [s]", "1"
       "``TB``", ":math:`T_B`", "lag time constant [s]", "10"
       "``TR``", ":math:`T_R`", "transducer time constant [s]", "0.01"
       "``Efd_max`` / ``Efd_min``", ":math:`E_{fd}^{max,min}`", "field-voltage limits (with ``incl_lim``)", "5 / 0"
       "``Vl``", ":math:`V_l`", "lag-pole state [p.u.]", ""
       "``Vtr``", ":math:`V_{tr}`", "transducer state [p.u.]", ""
       "``Efd``", ":math:`E_{fd}`", "field voltage (private algebraic) [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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
    r""":class:`AVRKundur` with the transient gain reduction removed: a plain
    high-gain static exciter with only a terminal-voltage transducer.

    Selected on a machine line with ``avr = "AVRKundur_NoTGR"``.

    **Model.**

    .. math::

       T_R \, \dot{V}_{tr} &= -V_{tr} + V_t \\
       0 &= -E_{fd} + K_A \left( V_{ref} - V_{tr} + V_s \right)

    with :math:`V_t = |\bar{v}_n|` and :math:`V_s` the stabilizer signal.
    :math:`E_{fd}` is an instantaneous gain on the transduced error, hence a
    private algebraic (read by the machine via ``Synchronous.var_sym('Efd')``).
    With a high :math:`K_A` and no transient gain reduction this exciter
    reduces the damping of the electromechanical modes, the classic setting in
    which a power system stabilizer is needed to restore damping.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "voltage regulator gain", "200"
       "``TR``", ":math:`T_R`", "transducer time constant [s]", "0.02"
       "``Efd_max`` / ``Efd_min``", ":math:`E_{fd}^{max,min}`", "field-voltage limits (with ``incl_lim``)", "5 / 0"
       "``Vtr``", ":math:`V_{tr}`", "transducer state [p.u.]", ""
       "``Efd``", ":math:`E_{fd}`", "field voltage (private algebraic) [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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
    r"""All-ODE realization of the Kundur two-area AVR (transducer plus
    lead-lag with transient gain reduction), with the lead realized through the
    derivative of the measurement so that :math:`E_{fd}` stays a differential
    state.

    Selected on a machine line with ``avr = "AVRKundur_ODE"``.

    **Model.**

    .. math::

       T_R \, \dot{V}_{tr} &= -V_{tr} + V_t \\
       T_B \, \dot{E}_{fd} &= -E_{fd}
          + K_A \left( V_{ref} - V_{tr} + V_s \right)
          - K_A T_A \, \dot{V}_{tr}

    with :math:`V_t = |\bar{v}_n|`, :math:`V_s` the stabilizer signal, and
    :math:`\dot{V}_{tr} = (V_t - V_{tr})/T_R` substituted symbolically. The
    setpoint-derivative term :math:`K_A T_A \dot{V}_{ref}` is omitted; it is
    zero for a constant setpoint.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "voltage regulator gain", "200"
       "``TA``", ":math:`T_A`", "lead time constant [s]", "0.015"
       "``TB``", ":math:`T_B`", "lag time constant [s]", "0.02"
       "``TR``", ":math:`T_R`", "transducer time constant [s]", "0.01"
       "``Efd_max`` / ``Efd_min``", ":math:`E_{fd}^{max,min}`", "field-voltage limits (with ``incl_lim``)", "5 / 0"
       "``Efd``", ":math:`E_{fd}`", "field voltage (state) [p.u.]", ""
       "``Vtr``", ":math:`V_{tr}`", "transducer state [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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
    r"""Simplified static exciter: a single first-order lag on the voltage error.

    Selected on a machine line with ``avr = "SEXST"``.

    **Model.**

    .. math::

       T_E \, \dot{E}_{fd} = -E_{fd} + K_A \left( V_{ref} - V_t + V_s \right)

    with :math:`V_t = |\bar{v}_n|` the terminal-voltage magnitude and
    :math:`V_s` the stabilizer signal (0 when no PSS is attached).

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "voltage regulator gain", "200"
       "``TE``", ":math:`T_E`", "exciter time constant [s]", "0.1"
       "``Efd_max`` / ``Efd_min``", ":math:`E_{fd}^{max,min}`", "field-voltage limits (with ``incl_lim``)", "5 / 0"
       "``Efd``", ":math:`E_{fd}`", "field voltage (state) [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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
    r"""IEEE Std 421.5 ST1A static exciter (small-signal form, no limits), as
    used by the 14-generator South East Australian benchmark
    (Gibbard and Vowles 2014, Fig. 20, Tables 16 and 26).

    Selected on a machine line with ``avr = "AVRST1A"``.

    **Model.** Transducer, two lead-lags (each realized as a lag state plus
    direct feedthrough), and the regulator lag:

    .. math::

       T_r \, \dot{V}_{tr} &= V_t - V_{tr}, \qquad
           e = V_{ref} - V_{tr} + V_s \\
       T_B \, \dot{V}_{ll1} &= e - V_{ll1}, \qquad
           y_1 = \Bigl(1 - \frac{T_C}{T_B}\Bigr) V_{ll1} + \frac{T_C}{T_B}\, e \\
       T_{B1} \, \dot{V}_{ll2} &= y_1 - V_{ll2}, \qquad
           y_2 = \Bigl(1 - \frac{T_{C1}}{T_{B1}}\Bigr) V_{ll2} + \frac{T_{C1}}{T_{B1}}\, y_1 \\
       T_A \, \dot{E}_{fd} &= K_A \, y_2 - E_{fd}

    with :math:`V_t = |\bar{v}_n|` and :math:`V_s` the stabilizer signal.
    :math:`T_B` and :math:`T_{B1}` must be positive; a unity block is obtained
    exactly with :math:`T_C = T_B`, and a transducer given as :math:`T_r = 0`
    in the data is approximated by a small lag (:math:`10^{-4}` s, a parasitic
    pole far above the rotor-mode range).

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "regulator gain", "300"
       "``TA``", ":math:`T_A`", "regulator time constant [s]", "0.05"
       "``Tr``", ":math:`T_r`", "voltage transducer time constant [s]", "1e-4"
       "``TB``", ":math:`T_B`", "first lead-lag denominator time constant [s]", "1"
       "``TC``", ":math:`T_C`", "first lead-lag numerator time constant [s]", "1"
       "``TB1``", ":math:`T_{B1}`", "second lead-lag denominator time constant [s]", "1e-4"
       "``TC1``", ":math:`T_{C1}`", "second lead-lag numerator time constant [s]", "1e-4"
       "``Vtr``", ":math:`V_{tr}`", "transducer state [p.u.]", ""
       "``Vll1``", ":math:`V_{ll1}`", "first lead-lag lag state [p.u.]", ""
       "``Vll2``", ":math:`V_{ll2}`", "second lead-lag lag state [p.u.]", ""
       "``Efd``", ":math:`E_{fd}`", "field voltage (state) [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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
    r"""IEEE Std 421.5 AC1A exciter (small-signal form, no limits or
    saturation), as used by the 14-generator South East Australian benchmark
    (Gibbard and Vowles 2014, Fig. 21, Tables 16 and 27). Exciter saturation,
    armature reaction and rectifier regulation are neglected
    (:math:`K_C = K_D = 0`), and the lead-lag is unity.

    Selected on a machine line with ``avr = "AVRAC1A"``.

    **Model.** Washout realization of the rate feedback
    :math:`s K_F/(1 + s T_F)`, regulator lag, and rotating exciter:

    .. math::

       V_f &= \frac{K_F}{T_F} E_{fd} - V_{fb}, \qquad
           T_F \, \dot{V}_{fb} = V_f \\
       T_A \, \dot{V}_r &= K_A \left( V_{ref} - V_t + V_s - V_f \right) - V_r \\
       T_E \, \dot{E}_{fd} &= V_r - K_E \, E_{fd}

    with :math:`V_t = |\bar{v}_n|` (unfiltered; the benchmark data has
    :math:`T_r = 0`) and :math:`V_s` the stabilizer signal.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "regulator gain", "400"
       "``TA``", ":math:`T_A`", "regulator time constant [s]", "0.02"
       "``KE``", ":math:`K_E`", "exciter constant", "1"
       "``TE``", ":math:`T_E`", "exciter time constant [s]", "1"
       "``KF``", ":math:`K_F`", "rate feedback gain", "0.03"
       "``TF``", ":math:`T_F`", "rate feedback time constant [s]", "1"
       "``Vr``", ":math:`V_r`", "regulator output (state) [p.u.]", ""
       "``Efd``", ":math:`E_{fd}`", "field voltage (state) [p.u.]", ""
       "``Vfb``", ":math:`V_{fb}`", "rate-feedback filter state [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "voltage setpoint (set by the initialization)", ""
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


class AVRCONST(AVR):
    r"""Constant field voltage: no excitation dynamics, the zero-response limit
    of any exciter (:math:`K_A \to 0` with the operating point held). The
    excitation-system counterpart of the constant-power governor
    :class:`~hermess.devices.governor.GOVCONST`.

    Selected on a machine line with ``avr = "AVRCONST"``.

    **Model.**

    .. math::

       0 = -E_{fd} + V_{ref}

    :math:`V_{ref}` is solved by the initialization to the field voltage that
    holds the power-flow operating point, and stays frozen afterwards. Used by
    validation cases that deliberately exclude excitation dynamics, e.g. the
    cross-tool machine benchmarks against ANDES, whose machines hold
    :math:`v_f` constant when no exciter is attached.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``Efd``", ":math:`E_{fd}`", "field voltage (private algebraic) [p.u.]", ""
       "``Vf_ref``", ":math:`V_{ref}`", "field-voltage setpoint (set by the initialization)", ""
    """

    def states(self) -> List[str]:
        return []

    def units(self) -> List[str]:
        return []

    def algebs(self) -> List[str]:
        return ["Efd"]

    def algebs_units(self) -> Dict[str, str]:
        return {"Efd": "p.u."}

    def algebs_x0(self) -> Dict[str, float]:
        return {"Efd": 1.5}

    def params(self) -> Dict[str, float]:
        return {}

    def x0(self) -> Dict[str, float]:
        return {}

    def descriptions(self) -> Dict[str, str]:
        return {
            "Efd": "internal field voltage (constant)",
            "Vf_ref": "exciter set point voltage",
        }

    def setpoints(self) -> Dict[str, float]:
        return {"Vf_ref": 1.5}

    def fgcall(self, host, dae: Dae) -> None:
        dae.g[host.Efd] = -dae.y[host.Efd] + host.Vf_ref


AVR_REGISTRY: Dict[str, type] = {
    "IEEEDC1A": IEEEDC1A,
    "AVRKundur_Filter": AVRKundur_Filter,
    "AVRKundur": AVRKundur,
    "AVRKundur_NoTGR": AVRKundur_NoTGR,
    "AVRKundur_ODE": AVRKundur_ODE,
    "SEXST": SEXST,
    "AVRST1A": AVRST1A,
    "AVRAC1A": AVRAC1A,
    "AVRCONST": AVRCONST,
}
