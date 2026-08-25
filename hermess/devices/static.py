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

from __future__ import annotations  # Postponed type evaluation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermess.system import Dae
from hermess.devices.device import DeviceRect
import numpy as np
import casadi as ca
import logging


class StaticLoadPower(DeviceRect):  # Not finished
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
    r"""
    This model implements the infinite bus with current balance equations. Resistance
    and reactance need to be set and the voltage values get calculated during
    initialization.

    Attributes:
        r (np.ndarray): Resistance value
        x (np.ndarray): Reactance value
        vre_int (np.ndarray): Internal voltage value
        vim_int (np.ndarray): Internal voltage value

    .. math::
       :nowrap:

       \begin{aligned}
       i_{re} &= \frac{1}{r^2 + x^2} \left( (v_{re} - v_{re}^{\text{int}}) r + (v_{im} - v_{im}^{\text{int}}) x \right) \\
       i_{im} &= \frac{1}{r^2 + x^2} \left( -\left(v_{re} - v_{re}^{\text{int}}\right) x + \left(v_{im} - v_{im}^{\text{int}}\right) r \right)
       \end{aligned}
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
    r"""
    ZIP static load. The shares of Z, I, and P (z_share, i_share, p_share) in the overall load need to be specified,
    and then the inner  parameters of the load will be set during the initialization
    to satisfy the initial power flow and the share of contributions of each load tape. The shares need to sum up to one for the
    initialization to work perfectly. Positive reactive current i_q means consumption.



    .. math::
      :nowrap:

      \begin{aligned}
      i_{re} &= \left(\frac{{p}v_{re} + {q} v_{im}}{v_{re}^2 + v_{im}^2}\right) + (g v_{re} - b v_{im}) + (\cos{\theta} i_d + \sin{\theta} i_q)\\
      i_{re} &=\left(\frac{{p}v_{im} - {q} v_{re}}{v_{re}^2 + v_{im}^2} \right)+ (b v_{re} + g v_{im}) + (\sin{\theta} i_q - \sin{\theta} i_d)
      \end{aligned}

    Attributes:
        g (np.ndarray:  Conductance value
        b (np.ndarray):  Susceptance value
        p (np.ndarray):  Active power value
        q (np.ndarray):  Reactive power value
        id (np.ndarray):  Active current value
        iq (np.ndarray):  Reactive current value
        p_share (np.ndarray):  Share of power load (default: 0.0)
        i_share (np.ndarray):  Share of current load (default: 0.0)
        z_share (np.ndarray):  Share of impedance load (default: 1.0)

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
