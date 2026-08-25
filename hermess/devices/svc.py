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

# Created: 2026-06-10
# Static Var Compensator device model.
#
# Implements the SVC of the simplified 14-generator South East Australian
# benchmark (Gibbard & Vowles, Univ. of Adelaide, Rev 4, 2014), Appendix I.2.3
# Fig. 22: a continuously-controlled shunt susceptance regulated by an
# integrator voltage controller with current (Q/Vt) droop.
#
# The published model is written in per-unit on the SVC Mvar base (MBASE) with
# an explicit base-conversion factor Ks = MBASE/SBASE. Multiplying the loop
# through by Ks gives the equivalent system-base form implemented here:
#
#     e   = Vref − Vt − Kd·(B·Vt − Bref)          (droop on Q/Vt = B·Vt)
#     dxB/dt = KA · e                              (integrator)
#     Td · dB/dt = 2.5 · xB − B                    (thyristor lag)
#     I_inj  = jB·V  →  load-convention currents
#         g[vre] += −B·vim ,   g[vim] += +B·vre
#
# with B in pu on the system base (100 MVA); B > 0 injects reactive power
# Q = B·|V|². Bref is a finit-solved setpoint so that the droop term measures
# the *deviation* of Q/Vt from the initial operating point, exactly like the
# Δ[Q/Vt] signal of the small-signal model; Vref then equals the loadflow
# voltage at the regulated bus. B carries limits (B_min/B_max from the SVC
# Mvar range) enforced by the simulator's limiter loop when incl_lim=True.

"""Static var compensator device model.

Selected in a system file by its class name in the first column (see
:class:`SVC`). Implements the SVC of the simplified 14-generator South East
Australian benchmark (Gibbard and Vowles 2014, Appendix I.2.3, Fig. 22): a
continuously controlled shunt susceptance regulated by an integrator voltage
controller with a Q/V droop. The class documents its equations and a table
mapping the code parameter names to the mathematical symbols used there.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import numpy as np

from hermess.devices.device import DeviceRect

if TYPE_CHECKING:
    from hermess.system import Dae, Grid

sqrt = np.sqrt


class SVC(DeviceRect):
    r"""Static var compensator: a voltage-regulated shunt susceptance
    (Gibbard and Vowles 2014, Appendix I.2.3, Fig. 22, converted from the SVC
    Mvar base to the system base).

    Selected in a system file by its class name in the first column, e.g.
    ``SVC, idx = "ASVC_2", bus = "205", KA = 500, q = -68.3``.

    **Model.** Integrator voltage regulator with a droop on the deviation of
    :math:`Q/V_t = B V_t` from its initial operating point, a thyristor-control
    lag, and the shunt current injection (load convention):

    .. math::

       e &= V_{ref} - V_t - K_d \left( B V_t - B_{ref} \right) \\
       \dot{x}_B &= K_A \, e \\
       T_d \, \dot{B} &= 2.5 \, x_B - B \\
       \bar{i} &= \mathrm{j} B \bar{v}_n
       \quad\Longleftrightarrow\quad
       i_{re} = -B v_{n,im}, \;\; i_{im} = B v_{n,re}

    with :math:`V_t = |\bar{v}_n|` the bus-voltage magnitude and :math:`B` the
    susceptance in p.u. on the system base (:math:`B > 0` injects
    :math:`Q = B V_t^2`). The factor 2.5 is the fixed gain of the published
    thyristor block. With ``incl_lim`` the limiter loop enforces
    :math:`B^{min} \le B \le B^{max}`.

    **Initialization** is sequential (closed form): the initial reactive output
    ``q`` [Mvar] is a device input (the loadflow result at the SVC bus, e.g.
    Table 9 of the SEA benchmark), from which

    .. math::

       B_0 = \frac{q / S_b}{V_0^2}, \qquad x_{B,0} = \frac{B_0}{2.5}, \qquad
       V_{ref} = V_0, \qquad B_{ref} = B_0 V_0 .

    SVC buses typically also carry loads, and a joint Newton solve would
    attribute the whole bus current to this device; the SVC therefore removes
    its share of the bus current from the initialization residual, so
    co-located devices calibrate themselves from the remaining injection
    (SVC entries must precede those devices in the system file). Consistency
    with the power flow is verified by the zero-residual initialization check.

    **Symbols.**

    .. csv-table::
       :header: Code, Symbol, Meaning, Default
       :widths: 14, 12, 58, 10

       "``KA``", ":math:`K_A`", "voltage-regulator integrator gain [p.u. B / s / p.u. V]", "500"
       "``Kd``", ":math:`K_d`", "Q/V droop gain [p.u. V / p.u. Q]", "0.01"
       "``Td``", ":math:`T_d`", "thyristor-control lag time constant [s]", "0.005"
       "``B_min`` / ``B_max``", ":math:`B^{min,max}`", "susceptance limits, system base (with ``incl_lim``)", "-10 / 10"
       "``q``", ":math:`q`", "initial reactive output from the loadflow [Mvar]", "0"
       "``xB``", ":math:`x_B`", "regulator integrator state [p.u.]", ""
       "``B``", ":math:`B`", "shunt susceptance (state) [p.u.]", ""
       "``Vref``", ":math:`V_{ref}`", "voltage reference (set to :math:`V_0` by the initialization)", ""
       "``Bref``", ":math:`B_{ref}`", "droop anchor (set to :math:`B_0 V_0` by the initialization)", ""
       "``Sn``", ":math:`S_n`", "rated power (inherited device rating) [MVA]", "100"
       "``Vn``", ":math:`V_n`", "rated voltage (inherited device rating) [kV]", "220"
       "``fn``", ":math:`f_n`", "nominal frequency (inherited device rating) [Hz]", "50"
       "``u``", ":math:`u`", "connection status (inherited device flag)", "True"
    """

    _init_method = "sequential"

    def __init__(self) -> None:
        super().__init__()
        self._type = "SVC"
        self._name = "Static_var_compensator"

        self.states.extend(["xB", "B"])
        self.units.extend(["pu", "pu"])
        self.ns = 2

        self._params.update(
            {
                "KA": 500.0,
                "Kd": 0.01,
                "Td": 0.005,
                "B_min": -10.0,
                "B_max": 10.0,
                "q": 0.0,  # initial reactive output [Mvar] from the loadflow
            }
        )
        self._setpoints.update({"Vref": 1.0, "Bref": 0.0})

        self._x0.update({"xB": 0.0, "B": 0.0})
        self._descr.update(
            {
                "KA": "voltage regulator integrator gain",
                "Kd": "Q/Vt droop gain",
                "Td": "thyristor control lag",
                "B_min": "minimum susceptance (system base)",
                "B_max": "maximum susceptance (system base)",
                "Vref": "voltage reference",
                "Bref": "initial Q/Vt anchoring the droop",
            }
        )

        # DAE index arrays (filled by xy_index)
        self.xB = np.array([], dtype=int)
        self.B = np.array([], dtype=int)
        # parameters / setpoints as arrays (filled by add())
        self.KA = np.array([], dtype=float)
        self.Kd = np.array([], dtype=float)
        self.Td = np.array([], dtype=float)
        self.B_min = np.array([], dtype=float)
        self.B_max = np.array([], dtype=float)
        self.q = np.array([], dtype=float)
        self.Vref = np.array([], dtype=float)
        self.Bref = np.array([], dtype=float)

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

    def _finit_sequential(self, dae: Dae) -> None:
        v0 = np.sqrt(dae.yinit[self.vre] ** 2 + dae.yinit[self.vim] ** 2)
        b0 = (self.q / dae.Sb) / v0**2

        self.xinit["B"] = list(b0)
        self.xinit["xB"] = list(b0 / 2.5)
        dae.xinit[self.B] = b0
        dae.xinit[self.xB] = b0 / 2.5

        # Regulator equilibrium: droop deviation zero, voltage error zero.
        self.Vref = v0
        self.Bref = b0 * v0

        # Remove this device's share of the bus init current from dae.iinit:
        # co-located devices that calibrate themselves from the *remaining*
        # bus current in their own finit (e.g. StaticZIP loads sharing the
        # SVC bus) then see exactly the non-SVC injection. Requires SVC
        # entries to precede those devices in the system file (finit order
        # is file order).
        i_re0 = -b0 * dae.yinit[self.vim]
        i_im0 = b0 * dae.yinit[self.vre]
        dae.iinit[self.vre] += i_re0
        dae.iinit[self.vim] += i_im0

    def input_current(self, dae: Dae):
        """Load-convention terminal currents of the shunt susceptance."""
        i_re = -dae.x[self.B] * dae.y[self.vim]
        i_im = dae.x[self.B] * dae.y[self.vre]
        return i_re, i_im

    def fgcall(self, dae: Dae) -> None:
        v_t = sqrt(dae.y[self.vre] ** 2 + dae.y[self.vim] ** 2)
        b = dae.x[self.B]

        # Droop on the Q/Vt deviation from the initial operating point.
        err = self.Vref - v_t - self.Kd * (b * v_t - self.Bref)

        dae.f[self.xB] = self.KA * err
        dae.f[self.B] = (2.5 * dae.x[self.xB] - b) / self.Td

        i_re, i_im = self.input_current(dae)
        dae.g[self.vre] += i_re
        dae.g[self.vim] += i_im
