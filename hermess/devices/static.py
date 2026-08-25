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

"""Static (state-free) load and source models.

A static model is selected in a system file by its class name in the first
column, e.g. ``StaticZIP, bus = "2", z_share = 1.0``. It contributes no
differential states; it only adds its consumed current to the algebraic nodal
current balance, in rectangular network coordinates
:math:`\\bar{v} = v_{re} + j v_{im}`, :math:`\\bar{i} = i_{re} + j i_{im}`.
Positive contributed current corresponds to consumption: the consumed complex
power is :math:`S = \\bar{v} \\, \\bar{i}^{*}`, so positive :math:`P` and
:math:`Q` mean active and reactive consumption.

The power values given in the system file are treated as initial guesses: the
initialization overwrites every setpoint below (marked "set by the
initialization") with the value that reproduces the initial power flow of the
``BusInit`` data, so the simulation starts in steady state at t = 0 s.
"""

from __future__ import annotations  # Postponed type evaluation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermess.system import Dae
from hermess.devices.device import DeviceRect
import numpy as np
import casadi as ca
import logging


class StaticLoadPower(DeviceRect):  # Not finished
    r"""Constant-power (PQ) load.

    Selected in a system file by the class name in the first column, e.g.
    ``StaticLoadPower, bus = "2"``.

    **Model.** The consumed current keeps :math:`P` and :math:`Q` constant
    regardless of the bus voltage:

    .. math::

       i_{re} &= \frac{(P/S_b) \, v_{re} + (Q/S_b) \, v_{im}}{v_{re}^2 + v_{im}^2} \\
       i_{im} &= \frac{(P/S_b) \, v_{im} - (Q/S_b) \, v_{re}}{v_{re}^2 + v_{im}^2}

    so that :math:`\bar{v}\,\bar{i}^{*} = (P + jQ)/S_b` exactly.
    Behaviorally this is :class:`StaticZIP` with ``p_share = 1``; unlike the
    ZIP setpoints, :math:`P` and :math:`Q` are handled here in the units of the
    system base ``Sb`` (MW / MVAr by default).

    A constant-power load has no equilibrium below the nose of the network's
    PV curve; if the initialization fails at a heavily loaded bus, use
    :class:`StaticZIP` with an impedance share instead.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``p``", ":math:`P`", "consumed active power [MW] (set by the initialization)", "0"
       "``q``", ":math:`Q`", "consumed reactive power [MVAr] (set by the initialization)", "0"
       "``Sn``", ":math:`S_n`", "rated power [MVA]", "100"
       "``Vn``", ":math:`V_n`", "rated voltage [kV]", "220"
       "``fn``", ":math:`f_n`", "nominal frequency [Hz]", "50"
    """

    def __init__(self) -> None:
        super().__init__()
        self._type = "Static_load_power"
        self._name = "Static_load_power"
        self._setpoints.update({"p": 0.0, "q": 0.0})
        self._descr.update(
            {
                "p": "Active power value",
                "q": "Reactive power value",
            }
        )
        self.p = np.array([], dtype=float)
        self.q = np.array([], dtype=float)
        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": False,
            }
        )

    def gcall(self, dae: Dae) -> None:

        dae.g[self.vre] += (
            self.p / dae.Sb * dae.y[self.vre] + self.q / dae.Sb * dae.y[self.vim]
        ) / (dae.y[self.vre] ** 2 + dae.y[self.vim] ** 2)
        dae.g[self.vim] += (
            self.p / dae.Sb * dae.y[self.vim] - self.q / dae.Sb * dae.y[self.vre]
        ) / (dae.y[self.vre] ** 2 + dae.y[self.vim] ** 2)

    def fgcall(self, dae: Dae) -> None:
        self.gcall(dae)


class StaticLoadImpedance(DeviceRect):
    r"""Constant-impedance (constant-admittance) load.

    Selected in a system file by the class name in the first column, e.g.
    ``StaticLoadImpedance, bus = "2"``.

    **Model.** The consumed current is proportional to the bus voltage through
    the constant admittance :math:`g + jb`:

    .. math::

       i_{re} &= g \, v_{re} - b \, v_{im} \\
       i_{im} &= b \, v_{re} + g \, v_{im}

    The consumed power is :math:`S = |\bar{v}|^2 (g - jb)`: positive :math:`g`
    consumes active power, and a load that consumes reactive power (inductive)
    has *negative* :math:`b` in this convention. Behaviorally this is
    :class:`StaticZIP` with ``z_share = 1``.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``g``", ":math:`g`", "conductance [p.u.] (set by the initialization)", "1"
       "``b``", ":math:`b`", "susceptance [p.u.] (set by the initialization)", "1"
       "``Sn``", ":math:`S_n`", "rated power [MVA]", "100"
       "``Vn``", ":math:`V_n`", "rated voltage [kV]", "220"
       "``fn``", ":math:`f_n`", "nominal frequency [Hz]", "50"
    """

    def __init__(self) -> None:
        super().__init__()
        self._type = "Static_load_impedance"
        self._name = "Static_load_impedance"
        self._setpoints.update({"g": 1.0, "b": 1.0})
        self._descr.update(
            {
                "g": "Conductance",
                "b": "Susceptance",
            }
        )
        self.g = np.array([], dtype=float)
        self.b = np.array([], dtype=float)
        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": False,
            }
        )

    def gcall(self, dae: Dae):

        dae.g[self.vre] += self.g * dae.y[self.vre] - self.b * dae.y[self.vim]
        dae.g[self.vim] += self.b * dae.y[self.vre] + self.g * dae.y[self.vim]

    def fgcall(self, dae: Dae) -> None:
        self.gcall(dae)

    def finit(self, dae: Dae) -> None:
        super().finit(dae)


class StaticInfiniteBus(DeviceRect):
    r"""Infinite bus: an ideal voltage source behind a series impedance.

    Selected in a system file by the class name in the first column, e.g.
    ``StaticInfiniteBus, bus = "9"``. The internal voltage is computed by the
    initialization; resistance and reactance are given in the system file.

    **Model.** The current drawn from the bus (consumption convention, like the
    loads) flows through the internal impedance :math:`r + jx` toward the
    internal EMF :math:`\bar{v}^{int} = v_{re}^{int} + j v_{im}^{int}`:

    .. math::

       \bar{i} = \frac{\bar{v} - \bar{v}^{int}}{r + jx},

    in rectangular components exactly as coded:

    .. math::

       i_{re} &= \frac{1}{r^2 + x^2}
           \left( (v_{re} - v_{re}^{int})\, r + (v_{im} - v_{im}^{int})\, x \right) \\
       i_{im} &= \frac{1}{r^2 + x^2}
           \left( -(v_{re} - v_{re}^{int})\, x + (v_{im} - v_{im}^{int})\, r \right)

    The bus therefore injects power into the network whenever
    :math:`\bar{v}^{int}` leads :math:`\bar{v}`; the fixed internal voltage
    makes it an ideal source of both voltage and frequency.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``r``", ":math:`r`", "internal resistance [p.u.]", "0.001"
       "``x``", ":math:`x`", "internal reactance [p.u.]", "0.001"
       "``vre_int``", ":math:`v_{re}^{int}`", "internal voltage, real part [p.u.] (set by the initialization)", "1"
       "``vim_int``", ":math:`v_{im}^{int}`", "internal voltage, imaginary part [p.u.] (set by the initialization)", "0"
       "``Sn``", ":math:`S_n`", "rated power [MVA]", "100"
       "``Vn``", ":math:`V_n`", "rated voltage [kV]", "220"
       "``fn``", ":math:`f_n`", "nominal frequency [Hz]", "50"
    """

    def __init__(self) -> None:
        super().__init__()
        self._type = "Infinite_bus"
        self._name = "Infinite_bus"
        self._setpoints.update({"vre_int": 1.0, "vim_int": 0.0})
        self._descr.update(
            {
                "vre_int": "Voltage value in real axis",
                "vim_int": "Voltage value in imaginary axis",
            }
        )
        self.vre_int = np.array([], dtype=float)
        self.vim_int = np.array([], dtype=float)
        self._params.update({"r": 0.001, "x": 0.001})
        self.r = np.array([], dtype=float)  # internal resistance
        self.x = np.array([], dtype=float)  # internal reactance
        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": False,
            }
        )

    def gcall(self, dae: Dae):

        dae.g[self.vre] += (
            1
            / (self.r**2 + self.x**2)
            * (
                (dae.y[self.vre] - self.vre_int) * self.r
                + (dae.y[self.vim] - self.vim_int) * self.x
            )
        )
        dae.g[self.vim] += (
            1
            / (self.r**2 + self.x**2)
            * (
                (dae.y[self.vre] - self.vre_int) * -self.x
                + (dae.y[self.vim] - self.vim_int) * self.r
            )
        )

    def fgcall(self, dae: Dae) -> None:
        self.gcall(dae)


class StaticZIP(DeviceRect):
    r"""ZIP load: constant-impedance (Z), constant-current (I) and
    constant-power (P) branches in parallel, with independently chosen shares.

    Selected in a system file by the class name in the first column, e.g.
    ``StaticZIP, bus = "2", z_share = 0.4, i_share = 0.3, p_share = 0.3``. The
    shares of each branch on the active-power side must sum to one; the
    reactive-power side has its own shares (``*_share_q``) that default to the
    active-power values when not given.

    **Model.** The consumed current is the sum of the three branches, with
    :math:`\theta = \operatorname{atan2}(v_{im}, v_{re})` the voltage angle:

    .. math::

       i_{re} &= \underbrace{\frac{p \, v_{re} + q \, v_{im}}{v_{re}^2 + v_{im}^2}}_{P}
          \; + \; \underbrace{g \, v_{re} - b \, v_{im}}_{Z}
          \; + \; \underbrace{\cos\theta \, i_d + \sin\theta \, i_q}_{I} \\
       i_{im} &= \underbrace{\frac{p \, v_{im} - q \, v_{re}}{v_{re}^2 + v_{im}^2}}_{P}
          \; + \; \underbrace{b \, v_{re} + g \, v_{im}}_{Z}
          \; + \; \underbrace{\sin\theta \, i_d - \cos\theta \, i_q}_{I}

    The consumed powers of the branches are :math:`S_P = p + jq` (constant),
    :math:`S_Z = |\bar{v}|^2 (g - jb)` (quadratic in voltage), and
    :math:`S_I = |\bar{v}| (i_d + j i_q)` (linear in voltage). Positive
    :math:`q` and :math:`i_q` mean reactive consumption.

    **Initialization.** The per-bus current demanded by the power flow is
    decomposed into a P-only and a Q-only component,

    .. math::

       P_0 &= v_{re} i_{re}^{0} + v_{im} i_{im}^{0}, \qquad
       Q_0 = v_{im} i_{re}^{0} - v_{re} i_{im}^{0}, \\
       \bar{i}^{P} &= \frac{P_0}{|\bar{v}|^2} (v_{re} + j v_{im}), \qquad
       \bar{i}^{Q} = \frac{Q_0}{|\bar{v}|^2} (v_{im} - j v_{re}),

    and each branch's setpoint pair (:math:`(g, b)`, :math:`(i_d, i_q)` or
    :math:`(p, q)`) is solved by Newton iteration so that the branch consumes
    exactly its share-weighted portion
    :math:`s^{P} \bar{i}^{P} + s^{Q} \bar{i}^{Q}` of that current. Shares that
    do not sum to one per axis are reported as a warning: the load then
    under- or over-delivers.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 16, 12, 56, 10

       "``z_share``", ":math:`s_Z^{P}`", "impedance share of the active-power demand", "1"
       "``i_share``", ":math:`s_I^{P}`", "current share of the active-power demand", "0"
       "``p_share``", ":math:`s_P^{P}`", "power share of the active-power demand", "0"
       "``z_share_q``", ":math:`s_Z^{Q}`", "impedance share of the reactive-power demand (default: follows ``z_share``)", "NaN"
       "``i_share_q``", ":math:`s_I^{Q}`", "current share of the reactive-power demand (default: follows ``i_share``)", "NaN"
       "``p_share_q``", ":math:`s_P^{Q}`", "power share of the reactive-power demand (default: follows ``p_share``)", "NaN"
       "``g``", ":math:`g`", "Z-branch conductance [p.u.] (set by the initialization)", "1"
       "``b``", ":math:`b`", "Z-branch susceptance [p.u.] (set by the initialization)", "1"
       "``id``", ":math:`i_d`", "I-branch active current [p.u.] (set by the initialization)", "1"
       "``iq``", ":math:`i_q`", "I-branch reactive current [p.u.] (set by the initialization)", "1"
       "``p``", ":math:`p`", "P-branch active power [p.u.] (set by the initialization)", "1"
       "``q``", ":math:`q`", "P-branch reactive power [p.u.] (set by the initialization)", "1"
       "``Sn``", ":math:`S_n`", "rated power [MVA]", "100"
       "``Vn``", ":math:`V_n`", "rated voltage [kV]", "220"
       "``fn``", ":math:`f_n`", "nominal frequency [Hz]", "50"
    """

    def __init__(self) -> None:
        super().__init__()
        self._type = "Static_load_ZIP"
        self._name = "Static_load_ZIP"
        self._setpoints_z = {"g": 1.0, "b": 1.0}
        self._setpoints_i = {"id": 1.0, "iq": 1.0}
        self._setpoints_p = {"p": 1.0, "q": 1.0}
        self._setpoints.update(
            {"g": 1.0, "b": 1.0, "p": 1.0, "q": 1.0, "id": 1.0, "iq": 1.0}
        )
        self._params.update(
            {
                "p_share": 0.0, "i_share": 0.0, "z_share": 1.0,
                # Q-side shares; default NaN means "fall back to the matching
                # P-side share at use time".
                "p_share_q": float("nan"),
                "i_share_q": float("nan"),
                "z_share_q": float("nan"),
            }
        )
        self._descr.update(
            {
                "p_share": "Fraction of the load constant power (P side)",
                "i_share": "Fraction of the load constant current (P side)",
                "z_share": "Fraction of the load constant impedance (P side)",
                "p_share_q": "Fraction of the load constant power for Q (default: matches p_share)",
                "i_share_q": "Fraction of the load constant current for Q (default: matches i_share)",
                "z_share_q": "Fraction of the load constant impedance for Q (default: matches z_share)",
                "g": "Conductance",
                "b": "Susceptance",
                "id": "Active current value",
                "iq": "Reactive current value",
                "p": "Active power value",
                "q": "Reactive power value",
            }
        )
        self.g = np.array([], dtype=float)
        self.b = np.array([], dtype=float)
        self.p = np.array([], dtype=float)
        self.q = np.array([], dtype=float)
        self.id = np.array([], dtype=float)
        self.iq = np.array([], dtype=float)
        self.p_share = np.array([], dtype=float)
        self.i_share = np.array([], dtype=float)
        self.z_share = np.array([], dtype=float)
        self.p_share_q = np.array([], dtype=float)
        self.i_share_q = np.array([], dtype=float)
        self.z_share_q = np.array([], dtype=float)
        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": False,
            }
        )

    def gcall_i(self, dae: Dae):
        theta = np.arctan2(dae.y[self.vim], dae.y[self.vre])
        i_re = np.cos(theta) * self.id + np.sin(theta) * self.iq
        i_im = np.sin(theta) * self.id - np.cos(theta) * self.iq
        dae.g[self.vre] += i_re
        dae.g[self.vim] += i_im

    def gcall_p(self, dae: Dae):

        dae.g[self.vre] += (self.p * dae.y[self.vre] + self.q * dae.y[self.vim]) / (
            dae.y[self.vre] ** 2 + dae.y[self.vim] ** 2
        )
        dae.g[self.vim] += (self.p * dae.y[self.vim] - self.q * dae.y[self.vre]) / (
            dae.y[self.vre] ** 2 + dae.y[self.vim] ** 2
        )

    def gcall_z(self, dae: Dae):

        dae.g[self.vre] += self.g * dae.y[self.vre] - self.b * dae.y[self.vim]
        dae.g[self.vim] += self.b * dae.y[self.vre] + self.g * dae.y[self.vim]

    def fgcall(self, dae: Dae) -> None:
        self.gcall_i(dae)
        self.gcall_z(dae)
        self.gcall_p(dae)

    def q_share(self, branch: str, k: int) -> float:
        """Q-side share for ``branch`` ∈ {'z','i','p'} at entry ``k``.

        Falls back to the matching P-side share when the Q-side is unset
        (NaN sentinel). This is the single source of truth for the
        P-side / Q-side fallback used by both ``finit_sub`` (vectorised
        via :func:`numpy.where`) and ``Dae.dist_load`` (scalar per
        entry).
        """
        q_val = float(getattr(self, f"{branch}_share_q")[k])
        if np.isnan(q_val):
            return float(getattr(self, f"{branch}_share")[k])
        return q_val

    def finit_sub(self, dae: Dae, sub: str) -> None:
        _setpoints = self.__getattribute__(f"_setpoints_{sub}")
        u = ca.SX.sym("", 0)
        u0 = []
        for item in _setpoints:
            # Set the initial guess for the setpoint
            u0.append(self.__dict__[item])
            # Reset it to be a variable
            self.__dict__[item] = ca.SX.sym(item, self.n)
            # Stack the variable to a single vector
            u = ca.vertcat(u, self.__dict__[item])
        u0 = [item for sublist in u0 for item in sublist]

        # Decompose the per-bus init current into a P-only and a Q-only piece,
        # then weight each by its independent share. With share_P == share_Q
        # (every entry that doesn't declare a *_share_q field) this collapses to
        # dae.iinit * share.
        V_re = dae.yinit[self.vre]
        V_im = dae.yinit[self.vim]
        V_sq = V_re ** 2 + V_im ** 2
        I_re = dae.iinit[self.vre]
        I_im = dae.iinit[self.vim]
        # Back out (P, Q) per entry from S = V·I*
        P_entry = V_re * I_re + V_im * I_im
        Q_entry = V_im * I_re - V_re * I_im
        # Per-axis P-only and Q-only currents
        iinit_P_re = P_entry * V_re / V_sq
        iinit_P_im = P_entry * V_im / V_sq
        iinit_Q_re = Q_entry * V_im / V_sq
        iinit_Q_im = -Q_entry * V_re / V_sq

        share_P = self.__dict__[f"{sub}_share"]
        share_Q_raw = self.__dict__[f"{sub}_share_q"]
        share_Q = np.where(np.isnan(share_Q_raw), share_P, share_Q_raw)

        dae.g[self.vre] += iinit_P_re * share_P + iinit_Q_re * share_Q
        dae.g[self.vim] += iinit_P_im * share_P + iinit_Q_im * share_Q

        # Algebraic variables are now not symbolic but their init values
        dae.y = dae.yinit.copy()
        dae.s = np.ones(dae.nx)
        dae.s = np.ones(dae.nx)
        gcall = self.__getattribute__(f"gcall_{sub}")
        gcall(dae)

        inputs = [ca.vertcat(u)]
        outputs = [
            ca.vertcat(
                dae.g[self.__dict__["vre"]],
                dae.g[self.__dict__["vim"]],
            )
        ]

        power_flow_init = ca.Function("h", inputs, outputs)
        newton_init = ca.rootfinder("G", "newton", power_flow_init)

        solution = newton_init(ca.vertcat(u0))
        solution = np.array(solution).flatten()

        for idx, s in enumerate(_setpoints):
            setpoint_range_start = (len(self.states) + idx) * self.n
            self.__dict__[s] = solution[
                setpoint_range_start : setpoint_range_start + self.n
            ]
            changed_setpoints = (
                u0[idx * self.n : (idx + 1) * self.n]
                != solution[setpoint_range_start : setpoint_range_start + self.n]
            )
            for i in range(self.n):
                if changed_setpoints[i]:
                    logging.info(
                        f"Setpoint '{s}' - {self._descr[s]} - updated in device {self._name} at node {self.bus[i]} from {u0[idx * self.n + i]} to {solution[setpoint_range_start + i]} to match the initial power flow!"
                    )

        # Reset the algebraic equations so they can be rebuilt from scratch when fgcall runs
        dae.g *= 0
        # Reset the voltages to being again symbolic variables
        dae.y = ca.SX.sym("y", dae.ny)
        dae.s = ca.SX.sym("s", dae.nx)

    def finit(self, dae: Dae) -> None:

        self.finit_sub(dae, "p")
        self.finit_sub(dae, "z")
        self.finit_sub(dae, "i")

        # Non-fatal sanity check: each side's shares should sum to 1.0 per entry.
        # A violation means the declared shares don't account for the full BusInit
        # demand on that axis, so the load will under/over-deliver.
        for k in range(self.n):
            sP = float(self.z_share[k] + self.i_share[k] + self.p_share[k])
            sQ = (self.q_share('z', k)
                  + self.q_share('i', k)
                  + self.q_share('p', k))
            if not np.isclose(sP, 1.0, atol=1e-6):
                logging.warning(
                    f"StaticZIP at bus '{self.bus[k]}': P-side shares "
                    f"sum to {sP:.6f} ≠ 1.0 — load will under/over-deliver "
                    f"active power."
                )
            if not np.isclose(sQ, 1.0, atol=1e-6):
                logging.warning(
                    f"StaticZIP at bus '{self.bus[k]}': Q-side shares "
                    f"sum to {sQ:.6f} ≠ 1.0 — load will under/over-deliver "
                    f"reactive power."
                )
