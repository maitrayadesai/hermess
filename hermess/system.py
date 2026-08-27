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
from typing import Literal, Optional, Sequence, Tuple
from hermess.devices.device import Line, BusInit, Disturbance
from hermess.config import config
from hermess.errors import SimulationCancelled
import casadi as ca
import numpy as np
import pandas as pd
from tabulate import tabulate
import logging
import math
import shutil
import time
from tqdm import tqdm

np.set_printoptions(threshold=np.inf)
np.random.seed(30)


class Grid:
    def __init__(self) -> None:

        self.y_adm_matrix: Optional[ca.SX] = None  # Admittance matrix
        self.y_series_r: Optional[ca.SX] = None  # Series admittance real
        self.y_series_i: Optional[ca.SX] = None  # Series admittance complex
        self.G_dyn: Optional[ca.SX] = (
            None  # Conductance with dynamic omega (with faults)
        )
        self.B_i_dyn: Optional[ca.SX] = None  # Susceptance on i side (with faults)
        self.B_j_dyn: Optional[ca.SX] = None  # Susceptance on j side (with faults)
        self.X_dyn: Optional[ca.SX] = None  # Reactance with dynamic omega (with faults)
        self.y_series: Optional[np.ndarray] = None  # Series admittance
        self.z_imp_matrix: Optional[np.ndarray] = None  # Impedance matrix
        self.tau: Optional[np.ndarray] = None  # Transformer tap ratios
        self.tau_r: Optional[np.ndarray] = None  # Transformer tap ratios real
        self.tau_i: Optional[np.ndarray] = None  # Transformer tap ratios complex
        self.incident_matrix: Optional[np.ndarray] = None
        self.Bsum: Optional[np.ndarray] = None  # sum of shunt susceptance at each node
        self.Gsum: Optional[np.ndarray] = None  # sum of shunt conductance at each node
        self.nb: int = 0  # Number of branches
        self.nn: int = 0  # Number of nodes
        self.buses: list = []  # list of all system buses
        self.Bsum_trafo: Optional[np.ndarray] = None
        self.Gsum_trafo: Optional[np.ndarray] = None

        self.Sb: float = 100
        # Indices corresponding to branches
        self.idx_i: list = []
        self.idx_j: list = []
        self.idx_i_re: list = []  # node i, real voltage index
        self.idx_j_re: list = []  # node j, real voltage index
        self.idx_i_im: list = []
        self.idx_j_im: list = []

        self.yinit: dict = {}  # Init voltages
        self.yf: dict = {}  # Output voltages
        self.sf: dict = {}  # Output power

        self.line: Optional[Line] = None
        self.line_is_faulted: list[bool] = []
        self.line_is_open: list[bool] = []
        self.line_fault_adm: list[float] = []
        self.bus_is_faulted: list[bool] = []
        self.bus_fault_adm: list[float] = []
        # Dictionary indices for fast look up
        self.idx_branch: dict[Tuple[str, str], int] = {}
        self.idx_bus: dict[str, int] = {}
        self.idx_bus_re: dict[str, int] = {}
        self.idx_bus_im: dict[str, int] = {}
        # Matrices to calculate all branch currents
        self.C_branches_forward: Optional[np.ndarray] = None
        self.C_branches_reverse: Optional[np.ndarray] = None
        self.C_branches: Optional[np.ndarray] = None  # stacked together

        # Mapping from line current states (xl) to nodal current balance entries (g)
        # Shape: (2*nn, 2*nb)
        self.C_linecurrents_to_nodes: Optional[np.ndarray] = None

    def save_data(self, dae: Dae) -> None:

        for idx, bus in enumerate(self.buses):
            self.yf[str(bus)] = dae.y_full[2 * idx : 2 * idx + 2, :]

        for idx, bus in enumerate(self.buses):
            self.sf[bus] = np.zeros([2, dae.nts])  # allocate

        I_bus_re = np.zeros((self.nn, dae.nts))
        I_bus_im = np.zeros((self.nn, dae.nts))

        for k in range(self.nb):
            I_bus_re[self.idx_i[k], :] += dae.i_full[4 * k + 0, :]
            I_bus_im[self.idx_i[k], :] += dae.i_full[4 * k + 1, :]
            I_bus_re[self.idx_j[k], :] += dae.i_full[4 * k + 2, :]
            I_bus_im[self.idx_j[k], :] += dae.i_full[4 * k + 3, :]

        # Restrict to the 2*nn voltage block before the even/odd split; device-
        # private algebraics live in y_full rows [2*nn:] and must not be read as
        # bus voltages.
        nv = 2 * self.nn
        Vr = dae.y_full[0:nv:2, :]
        Vi = dae.y_full[1:nv:2, :]

        P = Vr * I_bus_re + Vi * I_bus_im
        Q = Vi * I_bus_re - Vr * I_bus_im

        for idx, bus in enumerate(self.buses):
            self.sf[bus] = np.vstack((P[idx, :], Q[idx, :]))

    def init_symbolic(self, dae: Dae) -> None:
        # Algebraic vector layout: [ bus voltages (2*nn) | device privates (n_priv) ].
        # dae.n_priv is accumulated in device.xy_index, which runs before this.
        dae.nv = self.nn * 2  # size of the bus-voltage block
        dae.ny = dae.nv + dae.n_priv
        dae.nl = self.nb * 2
        dae.y = ca.SX.sym("y", dae.ny)
        dae.g = ca.SX(np.zeros(dae.ny))
        dae.xl = ca.SX.sym("xl", 2 * self.nb)
        dae.fl = ca.SX(np.zeros(2 * self.nb))
        dae.fnode = ca.SX(np.zeros(2 * self.nn))
        dae.grid = self
        # Line switches (1=active, 0=opened) for dynamic line mode
        if dae.line_dyn:
            dae.sl = ca.SX.sym("sl", 2 * self.nb)
            if not hasattr(dae, "slinit") or dae.slinit is None:
                dae.slinit = np.ones(2 * self.nb)

    def gcall(self, dae: Dae) -> None:
        # KCL at every bus: device injections + network admittance term = 0.
        # Devices contribute -I_gen (sources) or +I_load (sinks); the network
        # term enters with the same sign. T and y_adm_matrix are 2*nn x 2*nn,
        # so the admittance term applies to the bus-voltage block only. Device-
        # private algebraics occupy dae.y[2*nn:] with their own equations in
        # dae.g[2*nn:] (written by device fgcall) and are left untouched.
        # Without delta_ref the rotation is the identity, so the two extra
        # matrix products are skipped (mirror of guncall).
        nv = 2 * self.nn
        if getattr(dae, "has_delta_ref", False):
            T = self.build_bus_rotation_T(dae)
            dae.g[:nv] += T.T @ (self.y_adm_matrix @ (T @ dae.y[:nv]))
        else:
            dae.g[:nv] += self.y_adm_matrix @ dae.y[:nv]

        # delta_ref differential equation for omega_mode='dist':
        # dδ_ref / dt = ω_b · (ω_ref(bus) − 1). Without it the f vector has
        # free symbols at the delta_ref positions, which CasADi rejects.
        if getattr(dae, "has_delta_ref", False):
            omega_b = 2 * np.pi * dae.fn
            omega_ref_vec = ca.SX.ones(self.nn, 1) * dae.omega_net
            if getattr(dae, "omega_ref_buses", None) is not None:
                omega_ref_vec = dae.omega_ref_buses
            for bus in self.buses:
                idx_delta = dae.idx_delta_ref_by_bus[bus]
                idx_bus = self.idx_bus[bus]
                dae.f[idx_delta] = omega_b * (omega_ref_vec[idx_bus] - 1.0)

    def build_bus_rotation_T(self, dae: Dae) -> ca.SX:
        """
        Builds rotation matrix in order to translate bus voltages.
        returns:  Rotation matrix, SX (2*nn x 2*nn)
        """

        if not dae.has_delta_ref:
            return ca.SX.eye(2 * self.nn)

        # Assemble T as sparse selector @ diag(values) @ selectorᵀ products,
        # keeping the rotation sparse on large grids.
        # See docs/perf/01-sparse-symbolic-assembly.md.
        nn = self.nn
        idx_delta = [dae.idx_delta_ref_by_bus[bus] for bus in self.buses]
        theta = dae.x[idx_delta]
        c = ca.cos(theta)
        s = ca.sin(theta)

        cols = list(range(nn))
        E_re = ca.DM.ones(
            ca.Sparsity.triplet(2 * nn, nn, list(range(0, 2 * nn, 2)), cols)
        )
        E_im = ca.DM.ones(
            ca.Sparsity.triplet(2 * nn, nn, list(range(1, 2 * nn, 2)), cols)
        )
        T = (
            E_re @ ca.diag(c) @ E_re.T
            - E_re @ ca.diag(s) @ E_im.T
            + E_im @ ca.diag(s) @ E_re.T
            + E_im @ ca.diag(c) @ E_im.T
        )

        return T

    def guncall(self, dae: Dae) -> None:
        nv = 2 * self.nn  # bus-voltage block; privates live in dae.y[2*nn:]
        if getattr(dae, "has_delta_ref", False):
            T = self.build_bus_rotation_T(dae)
            dae.g[:nv] -= T.T @ (self.y_adm_matrix @ (T @ dae.y[:nv]))
        else:
            dae.g[:nv] -= self.y_adm_matrix @ dae.y[:nv]

    def add_lines(self, line: Line) -> None:
        self.line = line
        for bus_i, bus_j in zip(line.bus_i, line.bus_j):
            self.add_bus(bus_i, self.idx_i, self.idx_i_re, self.idx_i_im)
            self.add_bus(bus_j, self.idx_j, self.idx_j_re, self.idx_j_im)
            self.idx_branch[(bus_i, bus_j)] = self.nb
            self.nb += 1
        self.line_is_faulted = [False] * self.nb
        self.line_fault_adm = [0.0] * self.nb
        self.line_is_open = [False] * self.nb
        self.bus_is_faulted = [False] * self.nn
        self.bus_fault_adm = [0.0] * self.nn

    def add_bus(self, bus: str, idx: list, idx_re: list, idx_im: list) -> None:

        if bus not in self.buses:
            self.buses.append(bus)
            idx.append(self.nn)
            idx_re.append(2 * self.nn)
            idx_im.append(2 * self.nn + 1)
            self.idx_bus[bus] = self.nn
            self.nn += 1
        else:
            idx.append(self.buses.index(bus))
            idx_re.append(2 * self.buses.index(bus))
            idx_im.append(1 + 2 * self.buses.index(bus))

    def build_Bsum_Gsum_trafo(self) -> None:
        r = self.line.r.copy()
        x = self.line.x.copy()
        g = self.line.g.copy()
        b = self.line.b.copy()
        trafo = self.line.trafo.copy()

        z_inv = 1 / (r**2 + x**2)
        gs = r * z_inv * 0
        bs = -x * z_inv * 0

        # on the from side
        self.Gsum_trafo = np.zeros(self.nn)
        self.Bsum_trafo = np.zeros(self.nn)

        np.add.at(
            self.Gsum_trafo,
            self.idx_i,
            +gs / trafo**2 + g / 2 / (trafo**2 - 1) - gs / trafo,
        )
        np.add.at(self.Gsum_trafo, self.idx_j, +gs + g / 2 - gs / trafo)

        np.add.at(
            self.Bsum_trafo,
            self.idx_i,
            +bs / trafo**2 + b / 2 / (trafo**2 - 1) - bs / trafo,
        )
        np.add.at(self.Bsum_trafo, self.idx_j, +bs + b / 2 - bs / trafo)

    def build_y(self) -> None:
        # NOTE: w is 1.0 pu hardcoded here
        self.y_adm_matrix = np.zeros([2 * self.nn, 2 * self.nn])
        self.C_branches_forward = np.zeros([2 * self.nb, 2 * self.nn])
        self.C_branches_reverse = np.zeros([2 * self.nb, 2 * self.nn])

        r = self.line.r.copy()
        x = self.line.x.copy()
        g = self.line.g.copy()
        b = self.line.b.copy()
        trafo = self.line.trafo.copy()
        self.tau_r = np.real(trafo)
        self.tau_i = np.imag(trafo)

        for faulted_line, faulted in enumerate(self.line_is_faulted):
            if faulted:
                rtemp = complex(r[faulted_line])
                xtemp = complex(x[faulted_line])
                gtemp = complex(g[faulted_line])
                btemp = complex(b[faulted_line])

                zt = complex(rtemp, xtemp)
                yt = self.line_fault_adm[faulted_line]

                zp = zt * (1 + zt * yt / 4)
                yp = zt * yt / zp + complex(gtemp, btemp)

                r[faulted_line] = zp.real
                x[faulted_line] = zp.imag
                g[faulted_line] = yp.real
                b[faulted_line] = yp.imag

        for open_line, opened in enumerate(self.line_is_open):
            if opened:
                # For static lines: set impedance very high so admittance → 0
                # For dynamic lines: sl switch deactivates the branch, but we
                # still zero out shunt (g, b) so Bsum/Gsum are correct, and use
                # a moderate impedance to avoid float64 overflow in r² + x².
                r[open_line] = 1e15
                x[open_line] = 1e15
                g[open_line] = 0
                b[open_line] = 0

        for bus_id, faulted in enumerate(self.bus_is_faulted):
            if faulted:
                np.add.at(
                    self.y_adm_matrix,
                    (2 * bus_id, 2 * bus_id),
                    self.bus_fault_adm[bus_id],
                )
                np.add.at(
                    self.y_adm_matrix,
                    (2 * bus_id + 1, 2 * bus_id + 1),
                    self.bus_fault_adm[bus_id],
                )

        # Calculate Y matrix values
        z_inv = 1 / (r**2 + x**2)

        y_off_diag_real = -r * z_inv / trafo
        y_off_diag_imag = -x * z_inv / trafo
        y_diag_real = (g / 2 + r * z_inv) / trafo**2
        y_diag_imag = (-b / 2 + x * z_inv) / trafo**2

        self.y_series = 1 / (r + 1j * x)
        self.tau = trafo.copy()
        self.g_eff = g.copy()
        self.b_eff = b.copy()

        # Update Y matrix with vectorized operations
        np.add.at(self.y_adm_matrix, (self.idx_i_re, self.idx_j_re), y_off_diag_real)
        np.add.at(self.y_adm_matrix, (self.idx_i_re, self.idx_j_im), y_off_diag_imag)
        np.add.at(self.y_adm_matrix, (self.idx_i_im, self.idx_j_re), -y_off_diag_imag)
        np.add.at(self.y_adm_matrix, (self.idx_i_im, self.idx_j_im), y_off_diag_real)

        np.add.at(self.y_adm_matrix, (self.idx_j_re, self.idx_i_re), y_off_diag_real)
        np.add.at(self.y_adm_matrix, (self.idx_j_re, self.idx_i_im), y_off_diag_imag)
        np.add.at(self.y_adm_matrix, (self.idx_j_im, self.idx_i_re), -y_off_diag_imag)
        np.add.at(self.y_adm_matrix, (self.idx_j_im, self.idx_i_im), y_off_diag_real)

        # Update diagonal elements
        np.add.at(self.y_adm_matrix, (self.idx_i_re, self.idx_i_re), y_diag_real)
        np.add.at(self.y_adm_matrix, (self.idx_i_re, self.idx_i_im), y_diag_imag)
        np.add.at(self.y_adm_matrix, (self.idx_i_im, self.idx_i_re), -y_diag_imag)
        np.add.at(self.y_adm_matrix, (self.idx_i_im, self.idx_i_im), y_diag_real)

        np.add.at(self.y_adm_matrix, (self.idx_j_re, self.idx_j_re), g / 2 + r * z_inv)
        np.add.at(self.y_adm_matrix, (self.idx_j_re, self.idx_j_im), -b / 2 + x * z_inv)
        np.add.at(self.y_adm_matrix, (self.idx_j_im, self.idx_j_re), b / 2 - x * z_inv)
        np.add.at(self.y_adm_matrix, (self.idx_j_im, self.idx_j_im), g / 2 + r * z_inv)

        even_rows = np.arange(0, 2 * self.nb, 2)
        odd_rows = np.arange(1, 2 * self.nb, 2)

        # Create a branch impedance matrix to calculate branch currents
        np.add.at(
            self.C_branches_forward,
            (even_rows, self.idx_i_re),
            -y_off_diag_real / trafo + g / 2 / trafo**2,
        )
        np.add.at(
            self.C_branches_forward,
            (even_rows, self.idx_i_im),
            -y_off_diag_imag / trafo - b / 2 / trafo**2,
        )
        np.add.at(
            self.C_branches_forward,
            (odd_rows, self.idx_i_re),
            y_off_diag_imag / trafo + b / 2 / trafo**2,
        )
        np.add.at(
            self.C_branches_forward,
            (odd_rows, self.idx_i_im),
            -y_off_diag_real / trafo + g / 2 / trafo**2,
        )

        np.add.at(self.C_branches_forward, (even_rows, self.idx_j_re), y_off_diag_real)
        np.add.at(self.C_branches_forward, (even_rows, self.idx_j_im), y_off_diag_imag)
        np.add.at(self.C_branches_forward, (odd_rows, self.idx_j_re), -y_off_diag_imag)
        np.add.at(self.C_branches_forward, (odd_rows, self.idx_j_im), y_off_diag_real)

        np.add.at(
            self.C_branches_reverse,
            (even_rows, self.idx_j_re),
            -y_off_diag_real * trafo + g / 2,
        )
        np.add.at(
            self.C_branches_reverse,
            (even_rows, self.idx_j_im),
            -y_off_diag_imag * trafo - b / 2,
        )
        np.add.at(
            self.C_branches_reverse,
            (odd_rows, self.idx_j_re),
            y_off_diag_imag * trafo + b / 2,
        )
        np.add.at(
            self.C_branches_reverse,
            (odd_rows, self.idx_j_im),
            -y_off_diag_real * trafo + g / 2,
        )

        np.add.at(self.C_branches_reverse, (even_rows, self.idx_i_re), y_off_diag_real)
        np.add.at(self.C_branches_reverse, (even_rows, self.idx_i_im), y_off_diag_imag)
        np.add.at(self.C_branches_reverse, (odd_rows, self.idx_i_re), -y_off_diag_imag)
        np.add.at(self.C_branches_reverse, (odd_rows, self.idx_i_im), y_off_diag_real)

        self.C_branches = np.vstack((self.C_branches_forward, self.C_branches_reverse))

        # The dense bus impedance matrix Z = Y⁻¹ is not formed (nothing reads it,
        # and inverting Y is O((2·nn)³)). A consumer needing Z should prefer
        # np.linalg.solve(y_adm_matrix, rhs) over the full inverse.
        self.z_imp_matrix = None

    def _branch_selectors(self) -> dict:
        """Constant sparse selector matrices used to assemble the symbolic
        admittance and branch-current matrices without elementwise SX writes.

        ``ire``/``iim``/``jre``/``jim`` map branch k to the real/imag row of
        its from-/to-bus (shape 2·nn × nb); ``be``/``bo`` map branch k to its
        even/odd branch row (shape 2·nb × nb). Cached: they depend only on the
        topology, which is fixed after add_lines().
        """
        if getattr(self, "_selectors_cache", None) is None:
            nb, nn = self.nb, self.nn
            cols = list(range(nb))

            def sel(rows: list, nrow: int) -> ca.DM:
                return ca.DM.ones(
                    ca.Sparsity.triplet(nrow, nb, [int(r) for r in rows], cols)
                )

            self._selectors_cache = {
                "ire": sel(self.idx_i_re, 2 * nn),
                "iim": sel(self.idx_i_im, 2 * nn),
                "jre": sel(self.idx_j_re, 2 * nn),
                "jim": sel(self.idx_j_im, 2 * nn),
                "be": sel(range(0, 2 * nb, 2), 2 * nb),
                "bo": sel(range(1, 2 * nb, 2), 2 * nb),
            }
        return self._selectors_cache

    def build_y_sym(
        self,
        omega_buses: ca.SX = ca.SX(1.0),
        omega_lines: float | ca.SX = 1.0,
        dyn_update: bool = False,
    ) -> None:
        L = self.line.x.copy()
        C = self.line.b.copy()
        r = self.line.r.copy()
        g = self.line.g.copy()

        # For dynamic lines we use x and b, to be L and C, respectively,
        # As they are evaluated at 1.0 p.u. and thus equal.
        # For static lines x, and b are updated after fault calculation
        x = 1.0 * L
        b = 1.0 * C

        # trafo assumed to be real
        # NOTE: formulation needs to be extended for imaginary taps
        trafo = self.line.trafo.copy()
        self.tau = trafo
        self.tau_r = trafo.real
        self.tau_i = trafo.imag

        for faulted_line, faulted in enumerate(self.line_is_faulted):
            if faulted:
                # NOTE: took nondyn b (susceptance) & x (reactance) for fault admittance
                zt_r = r[faulted_line]
                zt_i = L[faulted_line]  # non dynamic
                gk = g[faulted_line]
                bk = C[faulted_line]  # non dynamic
                yt = self.line_fault_adm[faulted_line]

                # wz = 1 + zt*yt/4
                wz_r = 1 + (zt_r * yt / 4)
                wz_i = zt_i * yt / 4
                # zp = zt * wz
                zp_r = zt_r * wz_r - zt_i * wz_i
                zp_i = zt_r * wz_i + zt_i * wz_r

                # yp = (zt*yt)/zp + (g + jb)
                num_r = zt_r * yt
                num_i = zt_i * yt
                yp_r = (num_r * zp_r + num_i * zp_i) / (zp_r**2 + zp_i**2) + gk
                yp_i = (num_i * zp_r - num_r * zp_i) / (zp_r**2 + zp_i**2) + bk

                # Overwrite branch parameters
                r[faulted_line] = zp_r
                x[faulted_line] = zp_i
                g[faulted_line] = yp_r
                b[faulted_line] = yp_i

        for open_line, opened in enumerate(self.line_is_open):
            if opened:
                r[open_line] = 1e308
                x[open_line] = 1e308
                g[open_line] = 0
                b[open_line] = 0

        # Bus-fault shunt admittances are applied to the diagonal of the
        # admittance matrix after it is assembled below.
        # For static lines, we use x and b, evaluated at frequencies

        # Define shunt susceptances on each bus side
        # NOTE: defined here in order to include fault
        b_i = b
        b_j = b

        # For static case, evaluate parameters at frequencies
        # different from 1.0 pu, given by frequency reference framework.
        if not dae_sim.line_dyn:
            if dyn_update:
                # Series reactance evaluated at line frequency
                x = omega_lines * L
                # Shunt susceptance evaluated at respective bus frequency
                omega_buses_i = omega_buses[self.idx_i]
                omega_buses_j = omega_buses[self.idx_j]
                b_i = omega_buses_i * b
                b_j = omega_buses_j * b

        # Storing with fault applied
        self.G_dyn = g
        self.B_i_dyn = b_i
        self.B_j_dyn = b_j
        self.X_dyn = x

        # Calculate Y matrix values
        tau_abs = self.tau**2
        # tau_inv_r = self.tau_r / tau_abs
        # tau_inv_i = -self.tau_i / tau_abs
        z_inv = 1 / (r**2 + x**2)

        # Off-diagonal admittance: y_ij = -y_series / T
        # y_off_diag_real = -((r * z_inv) * tau_inv_r - (-x * z_inv) * tau_inv_i)
        # y_off_diag_imag = -((r * z_inv) * tau_inv_i + (-x * z_inv) * tau_inv_r)
        y_off_diag_real = -r * z_inv / self.tau
        y_off_diag_imag = -x * z_inv / self.tau

        # Diagonal at "i" (from side): (y_sh_i + y_series) / |T|^2
        y_diag_real_i = (g / 2 + r * z_inv) / tau_abs
        y_diag_imag_i = (-b_i / 2 + x * z_inv) / tau_abs

        # Diagonal at "j" (to side): (y_sh_j + y_series)
        y_diag_real_j = g / 2 + r * z_inv
        y_diag_imag_j = -b_j / 2 + x * z_inv

        # Series admittance: 1 / (r + jx)
        self.y_series_r = r * z_inv
        self.y_series_i = -x * z_inv

        # --- Sparse assembly ---------------------------------------------
        # Each accumulation pattern "Y[a_k, b_k] += v_k over branches k" is
        # written as E_a @ diag(v) @ E_bᵀ with constant sparse selector
        # matrices, keeping the admittance and branch-current matrices sparse.
        # Derivation and complexity: docs/perf/01-sparse-symbolic-assembly.md.
        S = self._branch_selectors()
        E_ire, E_iim = S["ire"], S["iim"]
        E_jre, E_jim = S["jre"], S["jim"]
        R_e, R_o = S["be"], S["bo"]

        def D(v) -> ca.SX:
            return ca.diag(ca.SX(v))

        yodr = y_off_diag_real
        yodi = y_off_diag_imag

        self.y_adm_matrix = (
            # Off-diagonal (i->j)
            E_ire @ D(yodr) @ E_jre.T
            + E_ire @ D(yodi) @ E_jim.T
            - E_iim @ D(yodi) @ E_jre.T
            + E_iim @ D(yodr) @ E_jim.T
            # Off-diagonal (j->i)
            + E_jre @ D(yodr) @ E_ire.T
            + E_jre @ D(yodi) @ E_iim.T
            - E_jim @ D(yodi) @ E_ire.T
            + E_jim @ D(yodr) @ E_iim.T
            # Diagonal at i
            + E_ire @ D(y_diag_real_i) @ E_ire.T
            + E_ire @ D(y_diag_imag_i) @ E_iim.T
            - E_iim @ D(y_diag_imag_i) @ E_ire.T
            + E_iim @ D(y_diag_real_i) @ E_iim.T
            # Diagonal at j
            + E_jre @ D(y_diag_real_j) @ E_jre.T
            + E_jre @ D(y_diag_imag_j) @ E_jim.T
            - E_jim @ D(y_diag_imag_j) @ E_jre.T
            + E_jim @ D(y_diag_real_j) @ E_jim.T
        )

        # Bus-fault shunt admittances on the diagonal (few entries; the
        # diagonal pattern already exists, so insertion is cheap).
        for bus_id, faulted in enumerate(self.bus_is_faulted):
            if faulted:
                adm = ca.SX(self.bus_fault_adm[bus_id])
                self.y_adm_matrix[2 * bus_id, 2 * bus_id] += adm
                self.y_adm_matrix[2 * bus_id + 1, 2 * bus_id + 1] += adm

        # Forward mapping: from-side terminal currents
        inv_tau = 1.0 / self.tau
        g_sh_i = g / (2 * tau_abs)
        b_sh_i = b_i / (2 * tau_abs)
        self.C_branches_forward = (
            R_e @ D(-yodr * inv_tau + g_sh_i) @ E_ire.T
            + R_e @ D(-yodi * inv_tau - b_sh_i) @ E_iim.T
            + R_o @ D(yodi * inv_tau + b_sh_i) @ E_ire.T
            + R_o @ D(-yodr * inv_tau + g_sh_i) @ E_iim.T
            + R_e @ D(yodr) @ E_jre.T
            + R_e @ D(yodi) @ E_jim.T
            - R_o @ D(yodi) @ E_jre.T
            + R_o @ D(yodr) @ E_jim.T
        )

        # Backward mapping: to-side terminal currents
        self.C_branches_reverse = (
            R_e @ D(-yodr * self.tau + g / 2) @ E_jre.T
            + R_e @ D(-yodi * self.tau - b_j / 2) @ E_jim.T
            + R_o @ D(yodi * self.tau + b_j / 2) @ E_jre.T
            + R_o @ D(-yodr * self.tau + g / 2) @ E_jim.T
            + R_e @ D(yodr) @ E_ire.T
            + R_e @ D(yodi) @ E_iim.T
            - R_o @ D(yodi) @ E_ire.T
            + R_o @ D(yodr) @ E_iim.T
        )

        self.C_branches = ca.vertcat(self.C_branches_forward, self.C_branches_reverse)

    def get_branch_index(
        self, node1: list[str], node2: list[str]
    ) -> tuple[np.ndarray, np.ndarray]:
        """

        Args:
            node1 (): List of starting nodes
            node2 (): List of receiving nodes

        Returns: The order of the given branch and the order of the opposite direction branch

        """
        # Sort the node pair and look it up in the dictionary
        # the first one sequence doesn't matter
        # the second one matters
        ids1 = []
        ids2 = []
        if isinstance(node1, str):
            node1 = [node1]
        if isinstance(node2, str):
            node2 = [node2]

        for n1, n2 in zip(node1, node2):
            key = (n1, n2)
            key_r = (n2, n1)

            if key in self.idx_branch:
                idx = self.idx_branch[key]
                ids1.append(idx)
                ids2.append(idx)
            elif key_r in self.idx_branch:
                idx = self.idx_branch[key_r]
                ids1.append(idx)
                ids2.append(idx + self.nb)
            else:
                ids1.append(None)
                ids2.append(None)

        return np.array(ids1), np.array(ids2)

    def get_node_index(self, buses: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # Calculate the real and imaginary indices in one step
        if not buses:
            return (
                np.array([]),
                np.array([]),
                np.array([]),
            )  # Return empty arrays safely, if list of buses empty
        var_indices = [
            (self.idx_bus[bus], 2 * self.idx_bus[bus], 2 * self.idx_bus[bus] + 1)
            for bus in buses
        ]
        idx, idx_re, idx_im = zip(*var_indices)
        return np.array(idx), np.array(idx_re), np.array(idx_im)


class GridSim(Grid):
    def gcall(self, dae: DaeSim, **kwargs):

        if dae.line_dyn:
            line = kwargs["line"]
            # First call line dynamics equations
            line.fcall(self, dae)

            omega_b = [2 * np.pi * dae.fn] * self.nn

            omega_ref_vec = (
                ca.SX.ones(self.nn, 1) * dae.omega_net
            )  # initialization and fallback

            # Set reference frequency
            if getattr(dae, "omega_ref_buses", None) is not None:
                # Vector of reference frequencies at all buses
                omega_ref_vec = dae.omega_ref_buses

            # d δ_ref / dt
            if dae.has_delta_ref:
                for bus in self.buses:
                    # Derivative d δ_ref/dt = ω_b * ω_ref
                    idx_delta = dae.idx_delta_ref_by_bus[bus]
                    idx_bus = self.idx_bus[bus]
                    dae.f[idx_delta] = omega_b[0] * (omega_ref_vec[idx_bus] - 1.0)

            idx_bus_re = [i for i in range(2 * self.nn) if i % 2 == 0]
            idx_bus_im = [i for i in range(2 * self.nn) if i % 2 != 0]

            i_shG_re = dae.y[idx_bus_re] * self.Gsum
            i_shG_im = dae.y[idx_bus_im] * self.Gsum

            # d vre / dt
            dae.fnode[idx_bus_re] = (
                omega_b / self.Bsum * -dae.g[idx_bus_re]
                + omega_b * omega_ref_vec * dae.y[idx_bus_im]
                - omega_b / self.Bsum * i_shG_re
            )
            # d vim / dt
            dae.fnode[idx_bus_im] = (
                omega_b / self.Bsum * -dae.g[idx_bus_im]
                - omega_b * omega_ref_vec * dae.y[idx_bus_re]
                - omega_b / self.Bsum * i_shG_im
            )

        else:
            # 2*nn x 2*nn admittance term applies to the bus-voltage block only;
            # device-private algebraics occupy dae.y[2*nn:] / dae.g[2*nn:].
            # Identity rotation (no delta_ref) skips the extra matrix products.
            nv = 2 * self.nn
            if getattr(dae, "has_delta_ref", False):
                T = self.build_bus_rotation_T(dae)
                dae.g[:nv] += T.T @ (self.y_adm_matrix @ (T @ dae.y[:nv]))
            else:
                dae.g[:nv] += self.y_adm_matrix @ dae.y[:nv]

            omega_b = [2 * np.pi * dae.fn] * self.nn

            omega_ref_vec = (
                ca.SX.ones(self.nn, 1) * dae.omega_net
            )  # initialization and fallback

            # Set reference frequency
            if getattr(dae, "omega_ref_buses", None) is not None:
                # Vector of reference frequencies at all buses
                omega_ref_vec = dae.omega_ref_buses

            # d δ_ref / dt
            if dae.has_delta_ref:
                for bus in self.buses:
                    # Derivative d δ_ref/dt = ω_b * ω_ref
                    idx_delta = dae.idx_delta_ref_by_bus[bus]
                    idx_bus = self.idx_bus[bus]
                    dae.f[idx_delta] = omega_b[0] * (omega_ref_vec[idx_bus] - 1.0)

    def init_from_power_flow(self, dae: DaeSim, static: BusInit) -> None:

        y = ca.SX.sym("y", self.nn * 2)
        y_init = []
        g = ca.SX(np.zeros(self.nn * 2))

        for idx, bus in enumerate(self.buses):
            y_init.extend([1, 0])
            static_idx = static.bus.index(bus)
            y_real = y[2 * idx]
            y_imag = y[2 * idx + 1]

            if static.type[static_idx] == "PQ":
                u_power = ca.horzcat(
                    ca.vertcat(y_real, y_imag), ca.vertcat(+y_imag, -y_real)
                )
                g[2 * idx : 2 * idx + 2] = (
                    u_power @ self.y_adm_matrix[2 * idx : 2 * idx + 2, :] @ y
                    + np.array([static.p[static_idx], static.q[static_idx]]) / self.Sb
                )

            elif static.type[static_idx] == "PV":
                u_power = ca.horzcat(y_real, +y_imag)
                g[2 * idx] = (
                    u_power @ self.y_adm_matrix[2 * idx : 2 * idx + 2, :] @ y
                    + static.p[static_idx] / self.Sb
                )
                g[2 * idx + 1] = (
                    np.sqrt(y[2 * idx] ** 2 + y[2 * idx + 1] ** 2)
                    - static.v[static_idx]
                )

            elif static.type[static_idx] == "slack":
                g[2 * idx] = np.sqrt(y_real**2 + y_imag**2) - static.v[static_idx]
                g[2 * idx + 1] = y_imag

        z = ca.Function("z", [y], [g])
        G = ca.rootfinder("G", "newton", z)
        try:
            solution = G(y_init)
        except Exception as e:
            logging.error(f"An exception occurred: {e}")
            logging.error("Init power flow failed.")
            raise Exception(
                "Power flow cannot be solved. Check if the grid parameters (pu) and initial power consumptions (MW and MVar) are realistic. Generated power should be negative. Only one bus can be slack."
            )
        if (solution == y_init).is_one():
            logging.error(
                "Init power flow aborted. Error unknown. Try different operating point"
            )
            raise Exception("Power flow not solved")
        # save the initial data into yinit dictionary

        for idx, bus in enumerate(self.buses):
            self.yinit[str(bus)] = np.array(solution[2 * idx : 2 * idx + 2].T)[0]

        dae.yinit = np.array(list(self.yinit.values())).reshape(self.nn * 2)
        dae.iinit = np.array(ca.DM(self.y_adm_matrix @ dae.yinit)).squeeze()

        # Append device-private algebraic init guesses after the 2*nn voltage
        # block. They seed the finit Newton solve and are overwritten there with
        # the converged consistent values. (iinit stays 2*nn: voltage block only.)
        if dae.n_priv:
            dae.yinit = np.concatenate(
                [dae.yinit, np.array(dae.yinit_priv, dtype=float)]
            )

        # find the admittance at each branch
        y_adm_branch = np.zeros((2 * self.nb, 2 * self.nb))
        y_adm_re = -self.y_adm_matrix[self.idx_i_re, self.idx_j_re]
        y_adm_im = -self.y_adm_matrix[self.idx_i_im, self.idx_j_re]
        for k in range(self.nb):
            y_adm_branch[2 * k, 2 * k] = y_adm_re[k]
            y_adm_branch[2 * k, 2 * k + 1] = -y_adm_im[k]
            y_adm_branch[2 * k + 1, 2 * k] = y_adm_im[k]
            y_adm_branch[2 * k + 1, 2 * k + 1] = y_adm_re[k]

        # yinit → complex bus voltages (nn,)
        yinit_reshape = np.array(list(self.yinit.values()), dtype=float).reshape(
            self.nn * 2
        )

        r = self.line.r.copy()
        x = self.line.x.copy()
        y_series = 1 / (r + 1j * x)

        Vbus = yinit_reshape[0::2] + 1j * yinit_reshape[1::2]
        # Vectorized branch computations
        Vi = Vbus[self.idx_i]  # (nb,)
        Vj = Vbus[self.idx_j]  # (nb,)

        Va = Vi / self.tau  # (nb,) tap can be complex
        # NOTE: not self.y_series to avoid mixing Casadi and Numpy
        I_series = y_series * (Va - Vj)  # (nb,) complex branch currents
        # Pack Re/Im interleaved into xlinit: [Re0, Im0, Re1, Im1, ...]
        xlinit = np.empty(2 * self.nb, dtype=float)
        xlinit[0::2] = I_series.real
        xlinit[1::2] = I_series.imag

        dae.xlinit = xlinit

        self.build_Bsum()
        self.build_Gsum()

    def power_flow_tables(self, dae: DaeSim) -> tuple:
        """Initial power flow as two pandas DataFrames: ``(bus, branch)``.

        The bus table carries the initialized voltage magnitude/angle, the net
        injection at every bus and the shunt contributions; the branch table the
        sending/receiving-end flows and the losses. This is the data behind
        :meth:`print_init_power_flow`, returned instead of printed so it can be
        inspected, filtered or exported.
        """
        # ---- BUS RESULTS ----
        idx_bus_re = [i for i in range(2 * self.nn) if i % 2 == 0]
        idx_bus_im = [i for i in range(2 * self.nn) if i % 2 != 0]

        vinit_re = np.array(dae.yinit)[idx_bus_re]
        vinit_im = np.array(dae.yinit)[idx_bus_im]

        vinit_mag = np.sqrt(vinit_re**2 + vinit_im**2)  # p.u.
        vinit_phase = np.arctan2(vinit_im, vinit_re)  # radians

        iinit_re = np.array(dae.iinit)[idx_bus_re]
        iinit_im = np.array(dae.iinit)[idx_bus_im]

        Pinit = (vinit_re * iinit_re + vinit_im * iinit_im) * self.Sb
        Qinit = (vinit_im * iinit_re - vinit_re * iinit_im) * self.Sb

        # calculate power (P & Q) loss due to shunts
        iinit_shunt_re = self.Gsum * vinit_re - self.Bsum * vinit_im
        iinit_shunt_im = self.Bsum * vinit_re + self.Gsum * vinit_im

        iinit_shunt_re_2 = self.Gsum * vinit_re - self.Bsum * vinit_im
        iinit_shunt_im_2 = self.Bsum * vinit_re + self.Gsum * vinit_im

        Ploss_shunt = (vinit_re * iinit_shunt_re + vinit_im * iinit_shunt_im) * self.Sb
        Qloss_shunt = (vinit_im * iinit_shunt_re - vinit_re * iinit_shunt_im) * self.Sb

        Ploss_shunt2 = (
            vinit_re * iinit_shunt_re_2 + vinit_im * iinit_shunt_im_2
        ) * self.Sb
        Qloss_shunt2 = (
            vinit_im * iinit_shunt_re_2 - vinit_re * iinit_shunt_im_2
        ) * self.Sb

        power_flow_bus_table = pd.DataFrame(
            {
                "Bus": pd.Series(np.array(self.buses), dtype="string"),
                "V Magnitude (pu)": pd.Series(vinit_mag, dtype=float),
                "V Phase (deg)": pd.Series(vinit_phase * 180 / np.pi, dtype=float),
                "P Gen (MW)": pd.Series(Pinit, dtype=float),
                "Q Gen (MVAr)": pd.Series(Qinit, dtype=float),
                "P Shunt (MW)": pd.Series(Ploss_shunt, dtype=float),
                "Q Shunt (MVAr)": pd.Series(Qloss_shunt, dtype=float),
                "P Shunt Trafo (MW)": pd.Series(Ploss_shunt2, dtype=float),
                "Q Shunt Trafo (MVAr)": pd.Series(Qloss_shunt2, dtype=float),
            }
        )

        # ---- BRANCH RESULTS ----
        # calculate the voltage across each branch (v_from - v_to)
        self.build_incident_matrix()
        # incident_matrix is (2*nb x 2*nn); dae.yinit may carry device-private
        # algebraic guesses appended after the voltage block, so use the
        # voltage block only.
        V_branch = self.incident_matrix @ dae.yinit[: 2 * self.nn]

        # find the admittance at each branch. y_adm_matrix is a CasADi SX here
        # (built by build_y_sym with ω placeholders defaulted to 1.0, so it is
        # numerically evaluable). SX fancy indexing Y[arr_i, arr_j] is an
        # outer/cross slice, not numpy element-wise pairing, so evaluate to a
        # numpy array first.
        Y_num = np.array(ca.DM(self.y_adm_matrix))
        y_adm_branch = np.zeros((2 * self.nb, 2 * self.nb))
        y_adm_re = -Y_num[self.idx_i_re, self.idx_j_re]
        y_adm_im = -Y_num[self.idx_i_im, self.idx_j_re]
        for k in range(self.nb):
            y_adm_branch[2 * k, 2 * k] = y_adm_re[k]
            y_adm_branch[2 * k, 2 * k + 1] = -y_adm_im[k]
            y_adm_branch[2 * k + 1, 2 * k] = y_adm_im[k]
            y_adm_branch[2 * k + 1, 2 * k + 1] = y_adm_re[k]

        # calculate the initial line currents through each branch
        ilinit = y_adm_branch @ V_branch

        idx_branch_re = [i for i in range(2 * self.nb) if i % 2 == 0]
        idx_branch_im = [i for i in range(2 * self.nb) if i % 2 != 0]

        # calculate the from_bus power injection
        Pinit_ij = (
            dae.yinit[self.idx_i_re] * ilinit[idx_branch_re]
            + dae.yinit[self.idx_i_im] * ilinit[idx_branch_im]
        ) * self.Sb
        Qinit_ij = (
            dae.yinit[self.idx_i_im] * ilinit[idx_branch_re]
            - dae.yinit[self.idx_i_re] * ilinit[idx_branch_im]
        ) * self.Sb

        # calculate the to_bus power injection
        Pinit_ji = (
            -(
                dae.yinit[self.idx_j_re] * ilinit[idx_branch_re]
                + dae.yinit[self.idx_j_im] * ilinit[idx_branch_im]
            )
            * self.Sb
        )
        Qinit_ji = (
            -(
                dae.yinit[self.idx_j_im] * ilinit[idx_branch_re]
                - dae.yinit[self.idx_j_re] * ilinit[idx_branch_im]
            )
            * self.Sb
        )

        Ploss = Pinit_ij + Pinit_ji
        Qloss = Qinit_ij + Qinit_ji

        power_flow_branch_table = pd.DataFrame(
            {
                "From Bus": [self.buses[i] for i in self.idx_i],
                "To Bus": [self.buses[j] for j in self.idx_j],
                "From Bus P (MW)": Pinit_ij,
                "From Bus Q (MVAr)": Qinit_ij,
                "To Bus P (MW)": Pinit_ji,
                "To Bus Q (MVAr)": Qinit_ji,
                "P Loss (MW)": Ploss,
                "Q Loss (MVAr)": Qloss,
            }
        )

        return power_flow_bus_table, power_flow_branch_table

    def print_init_power_flow(self, dae: DaeSim) -> None:
        """Print the initial power flow (bus and branch tables)."""
        power_flow_bus_table, power_flow_branch_table = self.power_flow_tables(dae)
        power_flow_bus_table = tabulate(power_flow_bus_table, headers="keys")
        power_flow_branch_table = tabulate(power_flow_branch_table, headers="keys")

        print("\nPower flow for initialization successfully solved")
        print(
            "======================================================================================================="
        )
        print("Power Flow: Bus Results")
        print(
            "======================================================================================================="
        )
        print(power_flow_bus_table)
        print(
            "-------------------------------------------------------------------------------------------------------"
        )
        print(
            "======================================================================================================="
        )
        print("Power Flow: Branch Results")
        print(
            "======================================================================================================="
        )
        print(power_flow_branch_table)
        print(
            "-------------------------------------------------------------------------------------------------------"
        )
        print(
            "-------------------------------------------------------------------------------------------------------"
        )

    def build_Gsum(self) -> None:
        # finds the sum of the shunt conductances (g) at each node due to line parameters
        g = self.line.g

        self.Gsum = np.zeros(self.nn)
        np.add.at(self.Gsum, self.idx_i, g / 2 / self.line.trafo**2)
        np.add.at(self.Gsum, self.idx_j, g / 2)
        # Add bus fault shunt admittances (real-valued conductance)
        for bus_id, faulted in enumerate(self.bus_is_faulted):
            if faulted:
                self.Gsum[bus_id] += self.bus_fault_adm[bus_id]

    def build_Bsum(self) -> None:
        # finds the sum of the shunt susceptances (b) at each node due to line parameters
        b = self.line.b

        self.Bsum = np.zeros(self.nn)
        np.add.at(self.Bsum, self.idx_i, b / 2 / self.line.trafo**2)
        np.add.at(self.Bsum, self.idx_j, b / 2)

    def build_incident_matrix(self) -> None:
        # build incident matrix for network (+1 indicates start node; -1 indicates end node)
        self.incident_matrix = np.zeros([self.nb * 2, self.nn * 2])

        for k in range(self.nb):
            self.incident_matrix[2 * k, self.idx_i_re[k]] = 1
            self.incident_matrix[2 * k + 1, self.idx_i_im[k]] = 1
            self.incident_matrix[2 * k, self.idx_j_re[k]] = -1
            self.incident_matrix[2 * k + 1, self.idx_j_im[k]] = -1

    def build_linecurrents_to_nodes(self) -> None:
        """Builds a constant mapping matrix that accumulates branch current
        states (xl) into nodal current balance entries (g).

        For each branch k with from-bus i and to-bus j:
          - Real current i_ijr contributes +1 at (vre_i) and -1 at (vre_j)
          - Imag current i_iji contributes +1 at (vim_i) and -1 at (vim_j)
        """
        self.C_linecurrents_to_nodes = np.zeros((2 * self.nn, 2 * self.nb))
        # rows for nodes (vre/vim), columns for line currents (i_ijr/i_iji)
        for k in range(self.nb):

            # real current mapping
            self.C_linecurrents_to_nodes[self.idx_i_re[k], 2 * k] = (
                1.0 / self.line.trafo[k]
            )
            self.C_linecurrents_to_nodes[self.idx_j_re[k], 2 * k] = -1.0

            # imag current mapping
            self.C_linecurrents_to_nodes[self.idx_i_im[k], 2 * k + 1] = (
                1.0 / self.line.trafo[k]
            )
            self.C_linecurrents_to_nodes[self.idx_j_im[k], 2 * k + 1] = -1.0

    def build_linecurrents_transformed_to_bus_frame(self, dae: DaeSim) -> ca.SX:
        """Builds the nodal current balance from line current states (xl)
        after rotating them from the line reference frame into each corresponding
        bus reference frame.

        For each branch k with from-bus i and to-bus j:
            - Real current i_ijr, transformed to reference frame of bus i, contributes +1 at (node i)
            - Real current i_ijr, transformed to reference frame of bus j, contributes -1 at (node j)
            - Imag current i_iji, transformed to reference frame of bus i, contributes +1 at (node i)
            - Imag current i_iji, transformed to reference frame of bus j, contributes -1 at (node j)
            - And applies (real) tap ratio at from side (i)

        Returns:
            (g_line)
            nodal current injection vector of length 2·nn
        """

        # Bus reference frame angles at terminals
        if dae.has_delta_ref:
            idx_i_bus = [self.buses[i] for i in self.idx_i]
            idx_i_delta = [dae.idx_delta_ref_by_bus[i] for i in idx_i_bus]
            delta_i = dae.x[idx_i_delta]

            idx_j_bus = [self.buses[j] for j in self.idx_j]
            idx_j_delta = [dae.idx_delta_ref_by_bus[j] for j in idx_j_bus]
            delta_j = dae.x[idx_j_delta]

            # Line reference frame angles
            delta_line = 0.5 * (delta_i + delta_j)

            # Rotation angles (same angle as for voltage transform)
            theta_i = delta_i - delta_line
            theta_j = delta_j - delta_line
        else:
            theta_i = 0.0
            theta_j = 0.0

        # Note: Gate by sl so opened lines don't inject current into nodes
        I_line_re = dae.xl[self.line.i_ijr] * dae.sl[self.line.i_ijr]
        I_line_im = dae.xl[self.line.i_iji] * dae.sl[self.line.i_iji]

        # Rotation of line currents into nodal reference frame (with sign change, -theta)
        Ii_re = ca.cos(theta_i) * I_line_re + ca.sin(theta_i) * I_line_im
        Ii_im = -ca.sin(theta_i) * I_line_re + ca.cos(theta_i) * I_line_im

        Ij_re = ca.cos(theta_j) * I_line_re + ca.sin(theta_j) * I_line_im
        Ij_im = -ca.sin(theta_j) * I_line_re + ca.cos(theta_j) * I_line_im

        # NOTE: Not yet accounted for complex tap ratios

        # Accumulate into nodal balance g_line
        g_line = ca.SX.zeros(2 * self.nn)
        for k in range(self.nb):
            # Real mapping of currents
            g_line[self.idx_i_re[k]] += (1.0 / self.line.trafo[k]) * Ii_re[
                k
            ]  # current contribution at i-side scaled by 1/tau
            g_line[self.idx_j_re[k]] += -Ij_re[k]

            # Imaginary mapping of currents
            g_line[self.idx_i_im[k]] += (1.0 / self.line.trafo[k]) * Ii_im[
                k
            ]  # current contribution at i-side scaled by 1/tau
            g_line[self.idx_j_im[k]] += -Ij_im[k]

        return g_line

    def build_voltage_transformed_to_line_frame(self, dae: DaeSim) -> ca.SX:
        """Builds the from- and to-terminal bus voltages expressed in the corresponding line reference frame.

        For each branch k with from-bus i and to-bus j:
            - Takes (V_i, V_j) given in the local bus frames of the from-bus i and to-bus j, respectively
            - Rotates both into branch k's line frame whose angle is defined by δ_line = 0.5(δ_i + δ_j)

        Returns:
            (Vi_re_L, Vi_im_L, Vj_re_L, Vj_im_L)
            transformed voltages as CasADi vectors of length nb
        """

        # Bus reference frame angles at terminals
        if dae.has_delta_ref:
            idx_i_bus = [self.buses[i] for i in self.idx_i]
            idx_i_delta = [dae.idx_delta_ref_by_bus[i] for i in idx_i_bus]
            delta_i = dae.x[idx_i_delta]
            idx_j_bus = [self.buses[j] for j in self.idx_j]
            idx_j_delta = [dae.idx_delta_ref_by_bus[j] for j in idx_j_bus]
            delta_j = dae.x[idx_j_delta]

            # Line reference frame angles
            delta_line = 0.5 * (delta_i + delta_j)

            # Rotation angles
            theta_i = delta_i - delta_line
            theta_j = delta_j - delta_line
        else:
            theta_i = 0.0
            theta_j = 0.0

        # Rotation of voltages into line reference frame (BUS to LINE)
        Vi_re = (
            ca.cos(theta_i) * dae.y[self.idx_i_re]
            - ca.sin(theta_i) * dae.y[self.idx_i_im]
        )
        Vi_im = (
            ca.sin(theta_i) * dae.y[self.idx_i_re]
            + ca.cos(theta_i) * dae.y[self.idx_i_im]
        )

        Vj_re = (
            ca.cos(theta_j) * dae.y[self.idx_j_re]
            - ca.sin(theta_j) * dae.y[self.idx_j_im]
        )
        Vj_im = (
            ca.sin(theta_j) * dae.y[self.idx_j_re]
            + ca.cos(theta_j) * dae.y[self.idx_j_im]
        )

        return Vi_re, Vi_im, Vj_re, Vj_im

    def build_branch_current_fun(self, dae: "DaeSim") -> None:
        """Builds a CasADi function that computes terminal branch currents from (x, y)
        consistent with distributed reference-frame formulation.

        For each branch k with from-bus i and to-bus j:
            - Takes terminal bus voltages (y) in the respective bus reference frames
            - Rotates Vi and Vj into the line reference frame of branch k
            - Applies the (real) tap ratio on the from-side (i)

            - Computes series and shunt currents (from transformed Vi,Vj) in the line frame
            - Forms terminal currents (If at i-side, It at j-side) in the line frame
            - Rotates If back to the i-bus frame and It back to the j-bus frame

        Stores:
            self._branch_current_fun(x, y) -> I_out, with length 4·nb
            ordered as [If_re, If_im, It_re, It_im] (in corresponding bus frames).
        """

        # Get bus reference frame angles at terminals
        if dae.has_delta_ref:
            idx_i_bus = [self.buses[i] for i in self.idx_i]
            idx_i_delta = [dae.idx_delta_ref_by_bus[i] for i in idx_i_bus]
            delta_i = dae.x[idx_i_delta]

            idx_j_bus = [self.buses[j] for j in self.idx_j]
            idx_j_delta = [dae.idx_delta_ref_by_bus[j] for j in idx_j_bus]
            delta_j = dae.x[idx_j_delta]

            # Line reference frame angles SS
            delta_line = 0.5 * (delta_i + delta_j)

            # Rotation angles
            theta_i = delta_i - delta_line
            theta_j = delta_j - delta_line
        else:
            theta_i = 0.0
            theta_j = 0.0

        # Rotate voltages into line reference frame
        Vi_re_L = (
            ca.cos(theta_i) * dae.y[self.idx_i_re]
            - ca.sin(theta_i) * dae.y[self.idx_i_im]
        )
        Vi_im_L = (
            ca.sin(theta_i) * dae.y[self.idx_i_re]
            + ca.cos(theta_i) * dae.y[self.idx_i_im]
        )

        Vj_re_L = (
            ca.cos(theta_j) * dae.y[self.idx_j_re]
            - ca.sin(theta_j) * dae.y[self.idx_j_im]
        )
        Vj_im_L = (
            ca.sin(theta_j) * dae.y[self.idx_j_re]
            + ca.cos(theta_j) * dae.y[self.idx_j_im]
        )

        # Apply tap ratio on i-side
        Vi_re_Lt = Vi_re_L / self.line.trafo
        Vi_im_Lt = Vi_im_L / self.line.trafo

        # Voltage drop across series element (line frame)
        dV_re = Vi_re_Lt - Vj_re_L
        dV_im = Vi_im_Lt - Vj_im_L

        # y_series = 1/(r + jx) = (r - jx)/(r^2 + x^2)
        # denom = self.line.r * self.line.r + self.line.x * self.line.x
        # y_series_re = self.line.r / denom
        # y_series_im = - self.line.x / denom

        # I_series = y_series * dV (line frame)
        I_series_re = self.y_series_r * dV_re - self.y_series_i * dV_im
        I_series_im = self.y_series_r * dV_im + self.y_series_i * dV_re

        # Shunt currents (line frame)
        Ish_i_re = 0.5 * self.G_dyn * Vi_re_Lt - 0.5 * self.B_i_dyn * Vi_im_Lt
        Ish_i_im = 0.5 * self.G_dyn * Vi_im_Lt + 0.5 * self.B_i_dyn * Vi_re_Lt

        Ish_j_re = 0.5 * self.G_dyn * Vj_re_L - 0.5 * self.B_j_dyn * Vj_im_L
        Ish_j_im = 0.5 * self.G_dyn * Vj_im_L + 0.5 * self.B_j_dyn * Vj_re_L

        # Terminal currents (line frame)
        # Forward: from i into the branch
        If_re_L = I_series_re + Ish_i_re
        If_im_L = I_series_im + Ish_i_im
        # Reverse: from j into the branch
        It_re_L = -I_series_re + Ish_j_re
        It_im_L = -I_series_im + Ish_j_im

        # Inverse rotation (-theta) to bus frame (LINE to BUS)
        If_re_B = ca.cos(theta_i) * If_re_L + ca.sin(theta_i) * If_im_L
        If_im_B = -ca.sin(theta_i) * If_re_L + ca.cos(theta_i) * If_im_L

        It_re_B = ca.cos(theta_j) * It_re_L + ca.sin(theta_j) * It_im_L
        It_im_B = -ca.sin(theta_j) * It_re_L + ca.cos(theta_j) * It_im_L

        I_out = ca.SX.zeros((4 * self.nb, 1))

        for k in range(self.nb):
            I_out[4 * k + 0] = If_re_B[k]
            I_out[4 * k + 1] = If_im_B[k]
            I_out[4 * k + 2] = It_re_B[k]
            I_out[4 * k + 3] = It_im_B[k]

        # Helper for Reference frequency substitution
        W_sym = ca.vertcat(
            dae.omega_ref, dae.omega_ref_buses, dae.omega_ref_lines
        )  # symbolic placeholder
        W_expr = ca.vertcat(
            dae.omega_ref_expr, dae.omega_ref_buses_expr, dae.omega_ref_lines_expr
        )  # function of states

        if I_out is not None:
            I_out = ca.substitute(I_out, W_sym, W_expr)

        self.branch_current_fun = ca.Function(
            "branch_current_fun",
            [dae.x, dae.y],
            [I_out],
        )

    def setup(self, dae: DaeSim, bus_init: BusInit) -> None:
        # Save original line parameters for fault restoration
        self.line_r_orig = self.line.r.copy()
        self.line_x_orig = self.line.x.copy()
        self.line_g_orig = self.line.g.copy()
        self.line_b_orig = self.line.b.copy()

        self.build_y_sym()
        self.build_incident_matrix()
        self.build_linecurrents_to_nodes()
        self.init_from_power_flow(dae, bus_init)
        self.init_symbolic(dae)

    def update_effective_line_params(self) -> None:
        """Update Line object parameters to reflect current fault/open state.
        Uses saved originals so clearing a fault restores the original values."""
        r = self.line_r_orig.copy()
        x = self.line_x_orig.copy()
        g = self.line_g_orig.copy()
        b = self.line_b_orig.copy()

        # For opened lines, zero out shunt admittance so Bsum/Gsum exclude them.
        # The series branch is already deactivated by the sl switch in Line.fcall,
        # but shunts enter the voltage dynamics via Bsum and Gsum directly.
        for idx, opened in enumerate(self.line_is_open):
            if opened:
                g[idx] = 0.0
                b[idx] = 0.0

        self.line.r = r
        self.line.x = x
        self.line.g = g
        self.line.b = b


class Dae:
    def __init__(self) -> None:

        # Counters
        self.nx: int = 0  # Number of differential states
        self.ny: int = 0  # Number of differential/algebraic states for voltages
        self.nv: int = 0  # Size of the bus-voltage block (2*nn); ny = nv + n_priv
        self.ng: int = 0  # Number of algebraic equations
        self.nl: int = 0  # Number of differential states for line currents
        self.np: int = 0  # Number of parameters/inputs (not used)
        self.nts: int = 0  # Number of time steps
        self.n_priv: int = 0  # Number of device-private algebraic variables

        # Device-private algebraic bookkeeping (populated during device.xy_index).
        # Privates occupy y/g indices [2*nn, ny).
        self.algebs_int_names: list[str] = []  # human-readable name per private
        self.yinit_priv: list[float] = []  # init guess per private (for dae.yinit)

        # Symbolic variables
        self.x: Optional[ca.SX] = None  # Symbolic differential states
        self.y: Optional[ca.SX] = (
            None  # Symbolic states voltages (differential or algebraic)
        )
        self.f: Optional[ca.SX] = None  # Symbolic first derivatives
        self.g: Optional[ca.SX] = (
            None  # Symbolic equations current balance (algebraic) or capacitor current (differential)
        )
        self.fnode: Optional[ca.SX] = None  # Symbolic nodal voltage time derivatives
        self.xl: Optional[ca.SX] = None  # Symbolic differential states of line currents
        self.fl: Optional[ca.SX] = (
            None  # Symbolic vector for derivatives of line currents
        )
        self.p: Optional[ca.SX] = None  # Stacked device-parameter symbols
        # (parametric build only; see hermess/parametric.py)
        self.p_val: Optional[np.ndarray] = None  # Their numeric values
        self.p0: Optional[ca.SX] = None  # Will be used for parameters/inputs
        self.s: Optional[ca.SX] = None  # Switches
        #: Parametric expressions of the build (a
        #: :class:`hermess.parametric.ParametricModel`), set by
        #: :func:`hermess.parametric.finalize` when ``Config.parametric``;
        #: ``None`` otherwise.
        self.parametric_model = None

        # Simulation outputs
        self.x_full: Optional[np.ndarray] = None  # Differential states output
        self.y_full: Optional[np.ndarray] = None  # Algebraic states output
        self.i_full: Optional[np.ndarray] = None  # Branch currents output

        # Simulation parameters
        self.T_start: float = 0.0
        self.T_end: float = 10.0
        self.time_steps: Optional[np.ndarray] = None  # Time steps of the simulation
        self.states: list[str] = []  # List of all states used in the model
        self.Sb: float = 100
        self.fn: Literal[50, 60] = 50
        self.t: float = 0.02

        # Reference frame parameters
        self.omega_net: float = 1.0  # System synchronous frequency in pu; fallback
        self.omega_coi: Optional[ca.SX] = ca.SX(1.0)  # COI frequency (States)

        self.omega_ref: Optional[ca.SX] = None  # Scalar reference frequency (Symbolic)
        self.omega_ref_buses: Optional[ca.SX] = (
            None  # Reference frequencies at buses (Symbolic)
        )
        self.omega_ref_lines: Optional[ca.SX] = (
            None  # Reference frequencies at lines (Symbolic)
        )

        self.omega_ref_expr: Optional[ca.SX] = (
            None  # Scalar reference frequency (States)
        )
        self.omega_ref_buses_expr: Optional[ca.SX] = (
            None  # Reference frequencies at buses (States)
        )
        self.omega_ref_lines_expr: Optional[ca.SX] = (
            None  # Reference frequencies at lines (States)
        )

        self.omega_mode: Literal["coi", "single", "nom", "dist"] = (
            config.omega_mode
        )  # Chosen reference frame
        self.has_delta_ref: bool = False  # Set True only when omega_mode == "dist"
        self.omega_single_idx: Optional[str] = getattr(
            config, "omega_single_idx", None
        )  # index to chosen device for single mode
        # TODO: eliminate equation (for single implementation)

        # Initial values
        self.xinit: list = []
        self.yinit: list = []
        self.iinit: list = []
        self.xlinit: list = []
        self.sinit = np.ndarray([], dtype=float)
        self.xmin: list = []  # minimal state limiter values
        self.xmax: list = []  # maximal state limiter values
        # Store the grid as an attribute of the class
        self.grid: Optional[Grid] = None
        # Per-instance device list + bus init. The reference-frame methods
        # (update_omega, compute_coi_expr, set_omega_single_idx_from_slack)
        # iterate these rather than module globals.
        self.device_list: list = []
        self.bus_init: Optional[BusInit] = None
        self.incl_lim: bool  # Include state limiters or not

        self.FG: Optional[ca.Function] = None  # Casadi function for the DAE model

    def __reduce__(self):
        # Filter the attributes based on their types
        picklable_attrs = {}
        for key, value in self.__dict__.items():
            if isinstance(value, (float, int, list, np.ndarray)):
                # Only serialize float, int, list, or numpy arrays
                picklable_attrs[key] = value

        # Return the class constructor and the picklable attributes as a tuple
        return (self.__class__, (), picklable_attrs)

    def __setstate__(self, state):
        # Restore the state from the pickled attributes
        self.__dict__.update(state)

    def setup(self, **kwargs) -> None:
        # Overwrite default values
        self.__dict__.update(kwargs)

        # Number of time steps
        self.nts = round((self.T_end - self.T_start) / self.t)
        self.time_steps = np.arange(self.T_start, self.T_end, self.t)

        self.set_omega_single_idx_from_slack()

        # Initialize reference frame angle states
        self.init_reference_frame_angle_states()

        # Initialize symbolic reference frequency formulations. Sizes come from
        # self.grid so they match the *_expr vectors update_omega() builds from
        # self.grid.nn / self.grid.nb; the two must align for the ca.substitute
        # call in fgcall() to succeed.
        if self.grid is None:
            raise RuntimeError(
                "Dae.setup() requires self.grid to be set before being called. "
                "Assign dae.grid = <appropriate Grid instance> first."
            )
        self.omega_ref = ca.SX.sym("omega_ref")  # Scalar reference frequency
        self.omega_ref_buses = ca.SX.sym(
            "omega_ref_b", self.grid.nn
        )  # Reference frequencies at buses
        self.omega_ref_lines = ca.SX.sym(
            "omega_ref_l", self.grid.nb
        )  # Reference frequencies at lines

        self.init_symbolic()

        # State initialization and setting of limits
        self.xinit = np.array(self.xinit)
        self.xlinit = np.array(self.xlinit)
        self.xmin = np.array(self.xmin)
        self.xmax = np.array(self.xmax)

    def fgcall(self) -> None:
        pass

    def init_symbolic(self) -> None:
        pass

    def parametric_rhs(self):
        """The parametric right-hand side of the build, for user-defined
        sensitivity problems.

        Returns a namespace with the symbol vectors (``x``, ``y``, ``s``,
        and ``xl``/``sl`` with dynamic lines), the assembled expressions
        (``f``, ``g``, ``fnode``, ``fl``) containing the parameter symbols
        ``p``, and their numeric values ``p_val``; the reference-frequency
        placeholders are already substituted, mirroring the integrator build.
        ``ca.substitute(f, p, p_val)`` recovers the numeric model, and
        ``ca.jacobian(f, p)`` is the parameter Jacobian. Requires a run with
        ``Config(parametric=True)``; see :mod:`hermess.parametric` for the
        scope and for :meth:`~hermess.parametric.ParametricModel.dae_dict`,
        which packages the same expressions for ``ca.integrator``. After a
        mid-run rebuild (dynamic-line disturbance or SETPOINT event) the
        returned expressions still describe the pre-disturbance model.
        """
        if self.parametric_model is None:
            raise RuntimeError(
                "no parametric build available: run with "
                "Config(parametric=True)"
            )
        return self.parametric_model.rhs()

    def compute_coi_expr(self, device_list=None) -> None:
        """Compute the symbolic Centre-of-Inertia expression from devices.

        ``device_list`` defaults to ``self.device_list``; pass an explicit list
        to override.
        """
        if device_list is None:
            device_list = self.device_list

        Mtot = ca.SX(0)
        num = ca.SX(0)

        for dev in device_list:
            for k in range(getattr(dev, "n", 0)):

                # Synchronous machines
                if "synchronous" in (getattr(dev, "_type", "") or "").lower():
                    if (
                        not hasattr(dev, "omega")
                        or not hasattr(dev, "H")
                        or not hasattr(dev, "Sn")
                    ):
                        continue

                    idx_omega = int(dev.omega[k])
                    omega_k = self.x[idx_omega]
                    Sn_k = float(dev.Sn[k])
                    H_eq = float(dev.H[k])

                    if H_eq <= 0.0 or Sn_k <= 0.0:
                        continue

                # Grid-forming inverter
                elif "gridforming" in dev.__class__.__name__.lower():
                    if not (
                        hasattr(dev, "Kp")
                        and hasattr(dev, "omega_f")
                        and hasattr(dev, "Sn")
                    ):
                        continue

                    if dev.omega_c is None:
                        omega_k = self.omega_net
                    else:
                        omega_k = dev.omega_c[k]
                    Kp_k = dev.Kp[k]
                    omega_f_k = dev.omega_f[k]
                    Sn_k = dev.Sn[k]
                    if Kp_k <= 0.0 or omega_f_k <= 0.0 or Sn_k <= 0.0:
                        continue
                    # Equivalent virtual inertia
                    H_eq = 1.0 / (2.0 * Kp_k * omega_f_k)

                else:
                    continue

                num += H_eq * (Sn_k / self.Sb) * omega_k
                Mtot += H_eq * (Sn_k / self.Sb)
        self.omega_coi = (num / Mtot) if Mtot > 0.0 else ca.SX(self.omega_net)

    def update_omega(self) -> None:
        """
        Update system reference frequency to frequency of selected mode.

        - If omega_mode == 'coi': compute inertia-weighted COI of synchronous machines.
        - If omega_mode == 'single' get frequency of chosen synchronous machine or inverter.
        - If omega_mode == 'dist' get frequencies at all buses from frequency divider.
        - Otherwise: set ω_ref = ω_net (fallback behavior).
        """

        # Default (fallback): nominal synchronous frequency
        omega_ref = ca.SX(self.omega_net)
        omega_ref_buses = omega_ref * ca.SX.ones(self.grid.nn, 1)
        omega_ref_lines = omega_ref * ca.SX.ones(self.grid.nb, 1)

        mode = getattr(self, "omega_mode", "nom")

        if mode not in ("coi", "single", "dist"):
            # Keep fallback expressions
            pass

        # Calculate Centre of Inertia (COI) reference frequency
        elif mode == "coi":

            self.compute_coi_expr(self.device_list)

            # Set Centre of Inertia (COI) reference frequency
            omega_ref = self.omega_coi
            omega_ref_buses = omega_ref * ca.SX.ones(self.grid.nn, 1)
            omega_ref_lines = omega_ref * ca.SX.ones(self.grid.nb, 1)

        # Calculate single machine or inverter reference frequency
        elif mode == "single":
            if getattr(self, "omega_single_idx", None) is None:
                omega_ref = ca.SX(self.omega_net)
                omega_ref_buses = omega_ref * ca.SX.ones(self.grid.nn, 1)
                omega_ref_lines = omega_ref * ca.SX.ones(self.grid.nb, 1)
                return

            for dev in self.device_list:
                k = getattr(dev, "int", {}).get(self.omega_single_idx)
                omega_k = None

                if k is None:
                    continue

                # Set Synchronous machine reference frequency
                if hasattr(dev, "omega"):
                    if dev.omega is None:
                        omega_k = self.omega_net
                    idx_omega = int(getattr(dev, "omega")[k])
                    omega_k = self.x[idx_omega]
                    break

                # Set GFL inverter reference frequency
                elif hasattr(dev, "omega_pll"):
                    if dev.omega_pll is None:
                        omega_k = self.omega_net
                    else:
                        omega_k = dev.omega_pll[k]
                    break

                # Set GFM inverter reference frequency
                elif hasattr(dev, "omega_c"):
                    if dev.omega_c is None:
                        omega_k = ca.SX(self.omega_net)
                    else:
                        omega_k = dev.omega_c[k]
                    break

            # Fallback
            if omega_k is None:
                omega_ref = ca.SX(self.omega_net)
            # Set single reference frequency of chosen SM, GFM- or GFL inverter
            else:
                omega_ref = omega_k

            # Create vector formulation of reference frequency
            # Buses and lines have same reference frequency for nom, coi and single mode
            omega_ref_buses = omega_ref * ca.SX.ones(self.grid.nn, 1)
            omega_ref_lines = omega_ref * ca.SX.ones(self.grid.nb, 1)

        elif mode == "dist":
            grid = getattr(self, "grid", None)

            omega_G_list, gen_bus_idx, gen_Xs_list = [], [], []
            omega_M_list, gfm_bus_idx, gfm_Bm_list = [], [], []
            omega_L_list, gfl_bus_idx, gfl_Bl_list = [], [], []

            for dev in self.device_list:
                dev_type = (getattr(dev, "_type", "") or "").lower()
                dev_name = (getattr(dev, "_name", "") or "").lower()
                if "synchronous" in dev_type:
                    for k in range(getattr(dev, "n", 0)):
                        if not hasattr(dev, "omega"):
                            continue
                        idx_omega = int(getattr(dev, "omega")[k])
                        omega_k = self.x[idx_omega]
                        omega_G_list.append(omega_k)  # generator Frequencies
                        gen_bus_idx.append(grid.idx_bus[dev.bus[k]])
                        gen_Xs_list.append(
                            float(dev.x_d[k])
                        )  # internal series reactance

                # Get GFL inverter parameters
                elif "gridfollowing" in dev_name:
                    for k in range(getattr(dev, "n", 0)):
                        omega_k = dev.omega_pll[k]
                        omega_L_list.append(omega_k)
                        gfl_bus_idx.append(grid.idx_bus[dev.bus[k]])
                        omega_b = 2 * np.pi * self.fn
                        Bl_k = dev.Kp[k] * dev.omega_f[k] / omega_b
                        gfl_Bl_list.append(Bl_k)  # 0.002

                # Get GFM inverter parameters
                elif "gridforming" in dev_name:
                    for k in range(getattr(dev, "n", 0)):
                        omega_k = dev.omega_c[k]
                        omega_M_list.append(omega_k)
                        gfm_bus_idx.append(grid.idx_bus[dev.bus[k]])
                        gfm_Bm_list.append(dev.Lt[k])  # 0.02

            mG, mM, mL = len(omega_G_list), len(omega_M_list), len(omega_L_list)
            mT = mG + mM + mL

            if mT == 0:
                omega_ref = ca.SX(self.omega_net)
                omega_ref_buses = omega_ref * ca.SX.ones(self.grid.nn, 1)
                omega_ref_lines = omega_ref * ca.SX.ones(self.grid.nb, 1)

            else:
                omega_tilde = ca.vertcat(*(omega_G_list + omega_M_list + omega_L_list))

                # Susceptance matrix for the buses
                Y = self.grid.y_adm_matrix
                B_BB = Y[1::2, 0::2]

                # Internal series susceptances at buses (diagonal matrix)
                B_tilde_BS = np.zeros((grid.nn, grid.nn))
                # Generator buses
                b_s = 1.0 / np.asarray(gen_Xs_list, dtype=float)
                np.add.at(B_tilde_BS, (gen_bus_idx, gen_bus_idx), b_s)
                # GFM buses
                b_m = np.asarray(gfm_Bm_list, dtype=float) if mM > 0 else np.zeros(0)
                np.add.at(B_tilde_BS, (gfm_bus_idx, gfm_bus_idx), b_m)
                # GFL buses
                b_l = np.asarray(gfl_Bl_list, dtype=float) if mL > 0 else np.zeros(0)
                np.add.at(B_tilde_BS, (gfl_bus_idx, gfl_bus_idx), b_l)

                # Susceptance matrix using stator and step-up transformer impedances
                # Extended to include GFM and GFL
                B_tilde_BG = ca.SX.zeros(grid.nn, mT)
                # Generator buses
                for k, b_i in enumerate(gen_bus_idx):
                    B_tilde_BG[b_i, k] += -b_s[k]
                # GFM buses
                for k, b_i in enumerate(gfm_bus_idx):
                    B_tilde_BG[b_i, mG + k] += -b_m[k]
                # GFL buses
                for k, b_i in enumerate(gfl_bus_idx):
                    B_tilde_BG[b_i, k + mG + mM] += -b_l[k]

                # Distributed frequencies at buses
                D = -ca.solve(B_BB + B_tilde_BS, B_tilde_BG)
                # Calculate COI expression
                self.compute_coi_expr(self.device_list)

                # Extended COI-FDF centred to COI frequency
                omega_B = D @ (
                    omega_tilde - self.omega_coi * ca.SX.ones(mT, 1)
                ) + self.omega_coi * ca.SX.ones(grid.nn, 1)

                # Set scalar reference frequency to be mean value
                omega_ref = ca.sum1(omega_B) / omega_B.shape[0]  # Mean value
                # Set bus reference frequencies to be estimate obtained by FDF
                omega_ref_buses = omega_B

                # Obtain line frequency: average of frequencies at terminal buses
                omega_ref_lines = [None] * grid.nb
                for (fb, tb), k in grid.idx_branch.items():
                    i = grid.idx_bus[fb]
                    j = grid.idx_bus[tb]
                    omega_ref_lines[k] = 0.5 * (omega_B[i] + omega_B[j])

                # Set line frequency to average of estimated FDF frequencies at terminal buses
                omega_ref_lines = ca.vertcat(*omega_ref_lines)

        # Store reference frequencies as function of states
        self.omega_ref_expr = omega_ref
        self.omega_ref_buses_expr = omega_ref_buses
        self.omega_ref_lines_expr = omega_ref_lines

    def set_omega_single_idx_from_slack(self) -> None:
        """
        If omega_mode == 'single' and omega_single_idx is None,
        choose the device connected to the slack bus as reference.

        Uses ``self.bus_init`` and ``self.device_list`` bound to this Dae.
        If bus_init has no entries (e.g. the system does not declare a
        BusInit), falls back to the module-level ``bus_init_sim`` for the
        slack lookup — the slack bus is a property of the physical grid.
        """
        if self.omega_mode != "single" or self.omega_single_idx is not None:
            return

        bus_init_for_slack = self.bus_init
        # Fallback: if no BusInit declared on this Dae, use the sim global.
        if bus_init_for_slack is None or not getattr(bus_init_for_slack, "bus", []):
            bus_init_for_slack = bus_init_sim

        slack_buses = [
            b
            for b, t in zip(bus_init_for_slack.bus, bus_init_for_slack.type)
            if t is not None and str(t).lower() == "slack"
        ]
        if not slack_buses:
            raise ValueError(
                "Cannot infer omega_single_idx: no slack bus declared in "
                "BusInit on either the calling Dae's side or the simulation."
            )
        slack_bus = slack_buses[0]  # In case of multiple, pick first

        for dev in self.device_list:
            if not hasattr(dev, "bus"):
                continue
            for local_pos, bus in enumerate(dev.bus):
                if bus == slack_bus:
                    for idx_name, pos in dev.int.items():
                        if pos == local_pos:
                            self.omega_single_idx = idx_name
                            return
        raise ValueError(
            f"No generator or converter found at slack bus {slack_bus} "
            f"to use as omega_single_idx."
        )

    def init_reference_frame_angle_states(self) -> None:
        """Initialize reference-frame angle states (δ_ref) for all network buses.

        - This function allocates one differential state per bus representing the
          local reference-frame angle δ_ref at that bus.
        - These angles are only needed for the distributed frequency reference
          framework (omega_mode == "dist"), specifically for transformations
          between the multiple local reference frames.
        """

        if self.omega_mode != "dist":
            self.has_delta_ref = False
            return

        if hasattr(self, "idx_delta_ref"):
            return

        # Use the buses from this Dae's grid; fall back to bus_init_sim if the
        # grid is not yet bound.
        if self.grid is not None and getattr(self.grid, "buses", []):
            buses: Sequence[str] = list(self.grid.buses)
        else:
            buses = getattr(bus_init_sim, "bus", [])
        nbus = len(buses)
        if nbus > 0:
            start = self.nx
            stop = self.nx + nbus
            self.idx_delta_ref = np.arange(start, stop, dtype=int)

            # Indexing is important as buses from bus_init_sim may have different order than grid.buses
            self.idx_delta_ref_by_bus = {
                bus: int(idx) for bus, idx in zip(buses, self.idx_delta_ref)
            }
            for bus in buses:
                self.states.append(f"Reference_frame_model_at_{bus}_delta_ref")
                self.xinit.append(0.0)
                self.xmin.append(-1e9)
                self.xmax.append(1e9)

            self.nx += nbus
            self.has_delta_ref = True

    # Load device class names recognised by the ZIP-aware LOAD disturbance
    # handler. Each entry maps the device's `_name` to a function that returns
    # the (z_share, i_share, p_share) tuple for the k-th entry of that device.
    _LOAD_DEVICE_SHARES = {
        "Static_load_ZIP":
            lambda dev, k: (float(dev.z_share[k]), float(dev.i_share[k]), float(dev.p_share[k])),
        "Static_load_impedance":
            lambda dev, k: (1.0, 0.0, 0.0),
        "Static_load_power":
            lambda dev, k: (0.0, 0.0, 1.0),
    }

    def _find_bus_load(self, bus_name: str):
        """Return (device, k) for the load attached to *bus_name*, or raise.

        Iterates `self.device_list` and matches against any of the registered
        load device classes. The first matching (device, local-index) pair is
        returned. Single-load-per-bus is enforced upstream by the framework
        (one device per bus per type), so the first match is unambiguous.
        """
        for dev in self.device_list:
            if getattr(dev, "_name", None) in self._LOAD_DEVICE_SHARES:
                if bus_name in dev.bus:
                    return dev, dev.bus.index(bus_name)
        raise ValueError(
            f"LOAD disturbance at bus '{bus_name}': no load device "
            f"(StaticZIP / StaticLoadImpedance / StaticLoadPower) declared "
            f"at this bus. Declare one in sim_param.txt before applying a "
            f"LOAD disturbance here."
        )

    def dist_load(self, p: float, q: float, bus: list) -> None:
        """ZIP-aware LOAD disturbance.

        Increments the rated demand at the load attached to ``bus`` by
        (p, q) MW/MVAr. The increment is apportioned across the device's
        configured Z, I, P shares so the load preserves its
        voltage-dependence shape:

          * Z share contributes a linear admittance step (no ``1/|V|^2`` term),
          * I share contributes a rotated constant-current step,
          * P share contributes a constant-power step.

        For ``StaticLoadImpedance`` (z=1) and ``StaticLoadPower`` (p=1)
        the shares are inferred. With ``line_dyn=True`` the contributions
        feed ``dae.fnode`` via the ω_b / B_sum capacitor coupling; with
        ``line_dyn=False`` they feed ``dae.g`` directly.
        """
        target_bus = bus[0]
        load_dev, k = self._find_bus_load(target_bus)
        # P-side shares from the dispatch table.
        a_z_P, a_i_P, a_p_P = self._LOAD_DEVICE_SHARES[load_dev._name](load_dev, k)
        # Q-side shares: StaticZIP exposes q_share(), which falls back to the
        # P-side when no Q-specific value is declared. StaticLoadImpedance and
        # StaticLoadPower have no Q-share concept; their Q-side equals P-side.
        if hasattr(load_dev, "q_share"):
            a_z_Q = load_dev.q_share("z", k)
            a_i_Q = load_dev.q_share("i", k)
            a_p_Q = load_dev.q_share("p", k)
        else:
            a_z_Q, a_i_Q, a_p_Q = a_z_P, a_i_P, a_p_P

        idx_re = int(load_dev.vre[k])
        idx_im = int(load_dev.vim[k])
        idx_node = self.grid.get_node_index([target_bus])[0][0]

        # V_nom = |V_init| at this bus. Matches the convention used by
        # StaticZIP.finit_sub to calibrate the rated device constants.
        v_re_init = float(self.yinit[idx_re])
        v_im_init = float(self.yinit[idx_im])
        V_nom_sq = v_re_init ** 2 + v_im_init ** 2
        V_nom = V_nom_sq ** 0.5

        dp_pu = p / self.Sb
        dq_pu = q / self.Sb
        vre = self.y[idx_re]
        vim = self.y[idx_im]

        # --- Z share: linear admittance step ----------------------------
        # ΔG from the P-side share, ΔB from the Q-side share, independently.
        dG =  a_z_P * dp_pu / V_nom_sq
        dB = -a_z_Q * dq_pu / V_nom_sq
        ire_z = dG * vre - dB * vim
        iim_z = dB * vre + dG * vim

        # --- I share: constant current in the bus frame -----------------
        theta = ca.atan2(vim, vre)
        dId = a_i_P * dp_pu / V_nom
        dIq = a_i_Q * dq_pu / V_nom
        ire_i = ca.cos(theta) * dId + ca.sin(theta) * dIq
        iim_i = ca.sin(theta) * dId - ca.cos(theta) * dIq

        # --- P share: constant power ------------------------------------
        dP = a_p_P * dp_pu
        dQ = a_p_Q * dq_pu
        v_sq = vre ** 2 + vim ** 2
        ire_p = (dP * vre + dQ * vim) / v_sq
        iim_p = (dP * vim - dQ * vre) / v_sq

        ire_total = ire_z + ire_i + ire_p
        iim_total = iim_z + iim_i + iim_p

        if self.line_dyn:
            omega_b = 2 * np.pi * self.fn
            B_node = self.grid.Bsum[idx_node]
            # The load current is a sink, so it feeds dae.fnode with a minus.
            self.fnode[idx_re] -= omega_b / B_node * ire_total
            self.fnode[idx_im] -= omega_b / B_node * iim_total
        else:
            self.g[idx_re] += ire_total
            self.g[idx_im] += iim_total

        self.fgcall()

    def check_disturbance(self, dist: Disturbance, iter_forward: int) -> bool:
        params_changed = False
        active = dist.time <= iter_forward * self.t
        if active.any():
            for idx, state in enumerate(active):
                if state:
                    match dist.type[0]:
                        case "FAULT_LINE":
                            if self.line_dyn:
                                logging.error(
                                    "FAULT_LINE is not supported with line_dyn=True. Skipping."
                                )
                                for key in dist._params:
                                    dist.__dict__[key] = np.array(
                                        dist.__dict__[key][1:]
                                    )
                                break
                            short_index = self.grid.get_branch_index(
                                dist.bus_i[0], dist.bus_j[0]
                            )[0][0]
                            self.grid.line_is_faulted[short_index] = True
                            self.grid.line_fault_adm[short_index] += dist.y[0]
                            self.exec_dist()
                            params_changed = True
                        case "CLEAR_FAULT_LINE":
                            if self.line_dyn:
                                logging.error(
                                    "CLEAR_FAULT_LINE is not supported with line_dyn=True. Skipping."
                                )
                                for key in dist._params:
                                    dist.__dict__[key] = np.array(
                                        dist.__dict__[key][1:]
                                    )
                                break
                            short_index = self.grid.get_branch_index(
                                dist.bus_i[0], dist.bus_j[0]
                            )[0][0]
                            self.grid.line_is_faulted[short_index] = False
                            self.exec_dist()
                            params_changed = True
                        case "OPEN_LINE":
                            short_index = self.grid.get_branch_index(
                                dist.bus_i[0], dist.bus_j[0]
                            )[0][0]
                            self.grid.line_is_open[short_index] = True
                            self.exec_dist()
                            params_changed = True
                        case "LOAD":
                            if not dae_sim.line_dyn:
                                # NOTE: need Y(w_ref) to be built with dependency on omega
                                # and integrated into equations
                                self.grid.guncall(self)
                                self.grid.build_y_sym(
                                    omega_buses=self.omega_ref_buses,
                                    omega_lines=self.omega_ref_lines,
                                    dyn_update=True,
                                )
                                self.grid.gcall(self)
                            self.dist_load(
                                p=dist.p_delta[0],
                                q=dist.q_delta[0],
                                bus=[dist.bus[0]],
                            )
                        case "SETPOINT":
                            device = self._find_device(dist.device[0])
                            row = device.int[dist.device[0]]
                            getattr(device, dist.param[0])[row] = dist.value[0]
                            # Setpoint values are baked into the symbolic
                            # expressions as constants: rebuild them.
                            self.exec_setpoint()
                            params_changed = True
                        case "FAULT_BUS":
                            short_index = self.grid.get_node_index([dist.bus[0]])[0][0]
                            self.grid.bus_is_faulted[short_index] = True
                            self.grid.bus_fault_adm[short_index] += dist.y[0]
                            self.exec_dist()
                            params_changed = True
                        case "CLEAR_FAULT_BUS":
                            short_index = self.grid.get_node_index([dist.bus[0]])[0][0]
                            self.grid.bus_is_faulted[short_index] = False
                            self.exec_dist()
                            params_changed = True
                        case _:
                            logging.ERROR(
                                f"Disturbance type {dist.type[0]} not found - skipped."
                            )
                            for key, value in dist._params.items():
                                dist.__dict__[key] = np.array(dist.__dict__[key][1:])
                            break
                    logging.info(
                        f"Disturbance {dist.type[0]} at {dist.time[0]} successfully executed!"
                    )
                    #  Remove the executed disturbance
                    for key, value in dist._params.items():
                        dist.__dict__[key] = np.array(dist.__dict__[key][1:])
        return params_changed

    def _find_device(self, idx: str):
        """The device whose ``int`` map carries the id ``idx`` (SETPOINT
        disturbances address devices by id, not by bus)."""
        for dev in self.device_list:
            if idx in getattr(dev, "int", {}):
                return dev
        raise KeyError(f"SETPOINT disturbance: no device with idx {idx!r}")

    def exec_setpoint(self) -> None:
        """Rebuild the model equations after a setpoint change. The setpoint
        arrays enter the symbolic expressions as numeric constants, so a
        changed value only takes effect through a rebuild. With dynamic lines
        :meth:`exec_dist` already rebuilds every device; the quasi-static path
        mirrors it: fresh symbols, every device's equations, then the network.
        Limitation (shared with the full rebuild of :meth:`exec_dist`): the
        rebuild discards the extra current injections of LOAD events executed
        earlier in the same run; schedule a SETPOINT before any LOAD step."""
        if self.line_dyn:
            self.exec_dist()
            return

        saved_sinit = self.sinit.copy()
        self.init_symbolic()
        self.sinit = saved_sinit
        # Fresh algebraic symbols and zeroed residuals (dae.y / dae.g live on
        # the grid's symbolic init, like in the dynamic-line rebuild).
        self.grid.init_symbolic(self)

        for dev in self.device_list:
            if dev.properties["fgcall"]:
                dev.fgcall(self)

        self.grid.build_y_sym()
        self.update_omega()
        self.grid.build_y_sym(
            omega_buses=self.omega_ref_buses,
            omega_lines=self.omega_ref_lines,
            dyn_update=True,
        )
        self.grid.gcall(self)
        self.grid.build_y()
        self.fgcall()

    def exec_dist(self):
        if self.line_dyn:
            # Update slinit for opened lines
            for idx, opened in enumerate(self.grid.line_is_open):
                self.slinit[2 * idx] = 0.0 if opened else 1.0
                self.slinit[2 * idx + 1] = 0.0 if opened else 1.0

            # Restore line params from originals (clears any stale modifications)
            self.grid.update_effective_line_params()

            # Rebuild derived quantities (Gsum now includes bus fault admittances)
            self.grid.build_y_sym(
                omega_buses=self.omega_ref_buses,
                omega_lines=self.omega_ref_lines,
                dyn_update=True,
            )
            self.grid.build_Gsum()
            self.grid.build_Bsum()

            # Full symbolic rebuild — reset symbolic expressions
            saved_sinit = self.sinit.copy()
            saved_slinit = self.slinit.copy()
            self.init_symbolic()
            self.sinit = saved_sinit
            self.grid.init_symbolic(self)
            self.slinit = saved_slinit

            # Rebuild all device equations.
            for dev in self.device_list:
                if dev.properties["fgcall"]:
                    dev.fgcall(self)

            # Rebuild grid equations (Line.fcall + voltage dynamics)
            self.grid.gcall(self, line=self.grid.line)

            # Refresh ω_ref expressions against the freshly rebuilt self.x,
            # device omega symbols, and post-fault y_adm_matrix. Without this,
            # fgcall() would substitute placeholders with expressions still
            # referencing the pre-rebuild SX symbols.
            self.update_omega()

            # Rebuild CasADi integrator
            self.fgcall()

        else:
            self.grid.guncall(self)

            # Build a plain (no-ω-substitution) Y so dist-mode's FDF D matrix
            # can be computed against the post-fault topology without picking
            # up the symbolic ω_ref placeholders that the next build bakes in.
            self.grid.build_y_sym()
            self.update_omega()

            self.grid.build_y_sym(
                omega_buses=self.omega_ref_buses,
                omega_lines=self.omega_ref_lines,
                dyn_update=True,
            )
            self.grid.gcall(self)
            # Re-numerify y_adm_matrix and C_branches after the network
            # change so the next fgcall() rebuilds the model functions
            # against the updated admittance/branch matrices.
            self.grid.build_y()
            self.fgcall()

    def debug_check_initialization(self) -> None:
        if self.line_dyn:
            f = ca.Function(
                "f",
                [self.x, self.y, self.xl, self.s, self.sl],
                [self.f, self.fnode, self.fl],
            )
            init_test = f(
                i0=self.xinit,
                i1=self.yinit,
                i2=self.xlinit,
                i3=self.sinit,
                i4=self.slinit,
            )
        else:
            f = ca.Function("f", [self.x, self.y, self.s], [self.f, self.g])
            init_test = f(i0=self.xinit, i1=self.yinit, i2=self.sinit)
        print("Results of initialization:")
        for o in init_test.keys():
            non_zero_indices = [
                i
                for i in range(init_test[o].size()[0])
                if abs(float(init_test[o][i])) > 1e-6
            ]
            non_zero_values = [float(init_test[o][i]) for i in non_zero_indices]
            if self.line_dyn:
                if o == "o0":
                    print(
                        f"Device dynamic equations non zero indices: {non_zero_indices}"
                    )
                    print(
                        f"Device dynamic equations non zero values: {non_zero_values}"
                    )
                elif o == "o1":
                    print(
                        f"Nodal voltage dynamic equation non zero indices: {non_zero_indices}"
                    )
                    print(
                        f"Nodal voltage dynamic equation non zero values: {non_zero_values}"
                    )
                elif o == "o2":
                    print(
                        f"Line current dynamic equation non zero indices: {non_zero_indices}"
                    )
                    print(
                        f"Line current dynamic equation non zero values: {non_zero_values}"
                    )
            else:
                if o == "o0":
                    print(f"Differential states non zero indices: {non_zero_indices}")
                    print(f"Differential states non zero values: {non_zero_values}")
                elif o == "o1":
                    print(f"Algebraic states non zero indices: {non_zero_indices}")
                    print(f"Algebraic states non zero values: {non_zero_values}")

    def check_initialization(self) -> None:
        W_sym = ca.vertcat(self.omega_ref, self.omega_ref_buses, self.omega_ref_lines)
        W_one = ca.SX.ones(1 + self.grid.nn + self.grid.nb, 1)

        if self.line_dyn:
            # Initialize all symbolic reference frequencies to nominal 1.0 p.u.
            f_init = ca.substitute(self.f, W_sym, W_one)
            fnode_init = ca.substitute(self.fnode, W_sym, W_one)
            fl_init = ca.substitute(self.fl, W_sym, W_one)

            f = ca.Function(
                "f",
                [self.x, self.y, self.xl, self.s, self.sl],
                [f_init, fnode_init, fl_init],
            )
            init_test = f(
                i0=self.xinit,
                i1=self.yinit,
                i2=self.xlinit,
                i3=self.sinit,
                i4=self.slinit,
            )
        else:
            # Initialize all symbolic reference frequencies to nominal 1.0 p.u.
            f_init = ca.substitute(self.f, W_sym, W_one)
            g_init = ca.substitute(self.g, W_sym, W_one)
            f = ca.Function("f", [self.x, self.y, self.s], [f_init, g_init])

            init_test = f(
                i0=self.xinit, i1=self.yinit, i2=self.sinit
            )  # TODO: check i2 and i3 what it should be here
        tol = 1e-6

        non_zero_indices_final = []
        for o in init_test.keys():
            non_zero_indices = [
                i
                for i in range(init_test[o].size()[0])
                if abs(float(init_test[o][i])) > tol
            ]
            non_zero_indices_final += non_zero_indices
        if non_zero_indices_final:
            logging.critical(
                "Initialization check failed. Non-zero entries found in the dynamic equations at initialization. Dynamic Simulation will either start with a transient or fail to simulate."
            )
        else:
            logging.info(
                "Initialization check passed. All dynamic equations are zero at initialization."
            )


class DaeSim(Dae):
    def __init__(self) -> None:
        super().__init__()
        self.int_scheme_sim = None
        self.int_scheme_sim_options: dict = {}
        #: Eigenvalues of :attr:`A`, filled by :meth:`eigenvalue_analysis`.
        self.eigenvalues = None
        #: Reduced state matrix at the operating point: the linearization
        #: ``dx/dt = A dx`` after eliminating the algebraic variables. Rows and
        #: columns follow :attr:`state_names`. Filled by
        #: :meth:`eigenvalue_analysis`.
        self.A = None
        #: Participation factors of every mode, filled by
        #: :meth:`eigenvalue_analysis`.
        self.participation_factors = None
        #: Participation factors normalized to [0, 1] per mode.
        self.participation_factors_normalized = None
        #: Names of the differential states, in the order used by :attr:`A`.
        self.state_names: list = []
        #: One entry per mode (eigenvalue, frequency, damping, dominant states),
        #: as used by :meth:`print_modal_report` and :meth:`participation_table`.
        self.modes: Optional[list] = None
        # Gated by config; when True the small-signal eigenvalue analysis is run
        # and its figures shown at the operating point before the simulation.
        self.small_signal_analysis: bool = False
        #: Optional hook called during :meth:`simulate` with the completed
        #: fraction in [0, 1]. Returning ``False`` cancels the run by raising
        #: :class:`~hermess.errors.SimulationCancelled`. Granularity: one call
        #: per accepted block with ``incl_lim``, one per disturbance interval
        #: otherwise (a disturbance-free run reports only 0 and 1).
        self.progress_callback = None
        #: Optional hook called once at the initialized operating point,
        #: after the small-signal analysis (when enabled) and before the time
        #: stepping, with this model as its argument. Returning ``False``
        #: cancels the run by raising
        #: :class:`~hermess.errors.SimulationCancelled` — e.g. to abort when
        #: :attr:`eigenvalues` show the operating point is unstable.
        self.init_callback = None
        self.t0: float  # Start of the next DAE call
        self.tf: float  # End of the next DAE call
        self.line_dyn: bool  # Simulate with dynamic lines or not

    def init_symbolic(self) -> None:

        self.x = ca.SX.sym("x", self.nx)
        self.f = ca.SX.sym("f", self.nx)
        self.s = ca.SX.sym("s", self.nx)
        self.p = ca.SX.sym("p", self.np)
        self.p0 = np.ones(self.np)
        self.sinit = np.ones(self.nx)  # Initial values for limiters (nothing limited)

    def fgcall(self, tout: Optional[np.ndarray] = None) -> Optional[ca.Function]:
        """Build the simulation integrator.

        With ``tout=None`` (the default) the integrator over
        ``(self.t0, self.tf)`` is built and stored as ``self.FG``. With an
        explicit output grid ``tout`` the integrator is built over
        ``(self.T_start, tout)`` and *returned* instead — used by the
        block-stepping limiter loop, which needs multi-step integrators next
        to the canonical single-step ``self.FG``.
        """
        # A model has algebraic constraints whenever the network voltages are
        # solved algebraically (line_dyn=False) OR a device declares private
        # algebraic variables (n_priv > 0). Either case requires a DAE solver,
        # regardless of line_dyn. ODE-only schemes (cvodes/rk) are valid only
        # when there are no algebraic constraints at all.
        has_alg = (not self.line_dyn) or (self.n_priv > 0)
        if self.int_scheme_sim in ("cvodes", "rk") and has_alg:
            raise ValueError(
                f"Integration scheme '{self.int_scheme_sim}' only supports ODE systems, "
                f"but the model is a DAE ("
                + (
                    "network voltages are algebraic"
                    if not self.line_dyn
                    else f"{self.n_priv} device-private algebraic constraint(s)"
                )
                + "). Use 'idas'/'collocation', or remove the algebraic constraints."
            )

        # Helper for Reference frequency substitution
        W_sym = ca.vertcat(
            self.omega_ref, self.omega_ref_buses, self.omega_ref_lines
        )  # symbolic placeholder
        W_expr = ca.vertcat(
            self.omega_ref_expr, self.omega_ref_buses_expr, self.omega_ref_lines_expr
        )  # function of states

        # Substitute reference frequency expression in all equations
        if self.f is not None:
            f = ca.substitute(self.f, W_sym, W_expr)
        if self.g is not None:
            g = ca.substitute(self.g, W_sym, W_expr)
        if self.fnode is not None:
            fnode = ca.substitute(self.fnode, W_sym, W_expr)
        if self.fl is not None:
            fl = ca.substitute(self.fl, W_sym, W_expr)

        if self.line_dyn:
            if self.n_priv > 0:
                # Mixed DAE: the network (voltages + line currents) is
                # differential, but device-private algebraics remain algebraic.
                # Voltages occupy y[:nv]; privates occupy y[nv:] with their
                # defining equations in g[nv:].
                y_volt = self.y[: self.nv]
                y_priv = self.y[self.nv :]
                g_priv = g[self.nv :]
                dae_dict = {
                    "x": ca.vertcat(self.x, y_volt, self.xl),
                    "z": y_priv,
                    "p": ca.vertcat(self.s, self.sl),
                    "ode": ca.vertcat(f, fnode, fl),
                    "alg": g_priv,
                }
            else:
                dae_dict = {
                    "x": ca.vertcat(self.x, self.y, self.xl),
                    "p": ca.vertcat(self.s, self.sl),
                    "ode": ca.vertcat(f, fnode, fl),
                }
        else:
            dae_dict = {
                "x": self.x,
                "z": self.y,
                "p": self.s,
                "ode": f,
                "alg": g,
            }
        # JIT-compiling the integrator (int_scheme_sim_options["jit"]) needs a C
        # compiler. Drop JIT when gcc is absent so integrator construction still
        # succeeds (identical results, just not compiled to native code).
        sim_options = self.int_scheme_sim_options
        if sim_options.get("jit") and shutil.which("gcc") is None:
            sim_options = {**sim_options, "jit": False}
            logging.warning(
                "No C compiler (gcc) found on PATH; disabling integrator JIT for this run."
            )
        # An empty output grid crashes the CasADi/SUNDIALS integrator (a hard
        # segfault, no exception), so it is refused here with an explanation.
        # It arises when a segment is shorter than one output step -- typically
        # T_end at or just after the last disturbance.
        out_grid = self.tf if tout is None else tout
        if np.size(out_grid) == 0:
            raise ValueError(
                "Empty integrator output grid: the interval to integrate is "
                f"shorter than one output step (ts = {self.t}). This usually means "
                f"T_end ({self.T_end}) is at or just after the last disturbance; "
                "extend T_end by at least one time step."
            )
        FG = ca.integrator(
            "FG",
            self.int_scheme_sim,
            dae_dict,
            self.T_start if tout is not None else self.t0,
            out_grid,
            sim_options,
        )
        if tout is not None:
            # Custom output grid (block stepping in the limiter loop): hand the
            # integrator back without touching self.FG.
            return FG
        self.FG = FG
        return None

    def _line_dyn_integrate(self, x0, y0, i0, s0, sl0, FG: Optional[ca.Function] = None):
        """Run the line_dyn integrator for one (set of) step(s) and return
        (x, y_full, i_line) as 2-D arrays (columns = time steps).

        Under line_dyn the differential block is [x | y_volt | xl]. With device
        private algebraics the voltages stay differential (driven by fnode) while
        the privates are algebraic: they are passed as z0 and returned in zf, and
        recombined here so y_full has the standard layout [voltages | privates].

        ``FG`` overrides the integrator (block stepping); defaults to self.FG.
        """
        if FG is None:
            FG = self.FG
        p = np.concatenate((s0, sl0))
        if self.n_priv > 0:
            nv = self.nv
            res = FG(
                x0=np.concatenate((x0, y0[:nv], i0)), z0=y0[nv:], p=p
            )
        else:
            res = FG(x0=np.concatenate((x0, y0, i0)), p=p)

        xf = np.array(res["xf"])
        if xf.ndim == 1:
            xf = xf.reshape(-1, 1)
        x = xf[: self.nx, :]
        if self.n_priv > 0:
            nv = self.nv
            y_volt = xf[self.nx : self.nx + nv, :]
            i_line = xf[self.nx + nv : self.nx + nv + self.nl, :]
            zf = np.array(res["zf"])
            if zf.ndim == 1:
                zf = zf.reshape(-1, 1)
            y = np.vstack((y_volt, zf))
        else:
            y = xf[self.nx : self.nx + self.ny, :]
            i_line = xf[self.nx + self.ny :, :]
        return x, y, i_line

    def simulate(self, dist: Disturbance) -> None:

        # Prepare for successive calls
        self.t0 = self.T_start
        self.tf = self.t

        self.update_omega()
        self.fgcall()

        iter_forward = 0
        self.x_full = np.zeros([self.nx, self.nts])
        self.y_full = np.zeros([self.ny, self.nts])

        # Set initial values
        x0 = self.xinit
        y0 = self.yinit
        i0 = self.xlinit
        s0 = self.sinit
        if self.line_dyn:
            sl0 = self.slinit
        self.x_full[:, iter_forward] = x0
        self.y_full[:, iter_forward] = y0
        previous_value = None

        # Build functions for evaluation
        if not self.line_dyn:
            # Rebuild Y to include static
            self.grid.build_y_sym(
                omega_buses=self.omega_ref_buses,
                omega_lines=self.omega_ref_lines,
                dyn_update=True,
            )
        # Small-signal analysis (gated by config) runs at the operating point,
        # before the time-stepping loop, so its results are produced even if the
        # simulation later fails. The blocking show below guarantees the figures
        # are seen before the run proceeds.
        if getattr(self, "small_signal_analysis", False):
            self.eigenvalue_analysis()
            self.print_modal_report()
            if getattr(self, "small_signal_figures", True):
                self.plot_eigenvalues()
                self.plot_participation_bands()
                import matplotlib
                import matplotlib.pyplot as plt

                # Block only on an interactive backend (so the user sees the
                # figures before the run proceeds); on a non-interactive backend
                # (headless/CI) the figures are built but plt.show would only
                # warn, so skip it.
                _non_interactive = {
                    "agg", "pdf", "svg", "ps", "template", "cairo", "pgf",
                }
                if matplotlib.get_backend().lower() not in _non_interactive:
                    plt.show(block=True)

        # Snapshot initial admittance state for post-processing branch currents
        self.grid.build_y()
        self._fault_intervals = [(0, self._snapshot_branch_params())]

        # The model is built and initialized; give the caller one look at the
        # operating point (eigenvalues, power flow) before the time stepping.
        if self.init_callback is not None and self.init_callback(self) is False:
            raise SimulationCancelled(
                "Simulation cancelled at the operating point by the init callback."
            )

        # Time stepping starts now.
        self._report_progress(0.0)

        if self.incl_lim:
            # Limit-aware block stepping. Runs of steps with no pending
            # disturbance are integrated with a single call producing a block of
            # outputs, avoiding the per-call solver setup (consistent-IC
            # computation, BDF history rebuild) that dominates wall time at small
            # step sizes. A block is accepted only up to (excluding) the first
            # step where the limits would clip the state; from there the loop
            # falls back to exact single-step clipping until the trajectory
            # leaves the limits again.
            # Semantics and measurements: docs/perf/07-incl-lim-block-stepping.md.
            #
            # block_max=1 reproduces a one-integrator-call-per-step loop, useful
            # for debugging/regression checks.
            block_max = getattr(self, "sim_block_max", 64)
            single_streak = 8  # single steps to take after a clip event
            block_cache: dict[int, ca.Function] = {}
            single_left = 0

            def _block_fg(n_block: int) -> ca.Function:
                if n_block not in block_cache:
                    block_cache[n_block] = self.fgcall(
                        tout=self.T_start + self.t * np.arange(1, n_block + 1)
                    )
                return block_cache[n_block]

            pbar = tqdm(total=self.nts - 1, desc="Simulation", unit="step")
            while iter_forward < self.nts - 1:
                remaining = self.nts - 1 - iter_forward
                # First step index at which check_disturbance() would execute
                # an event (it fires when dist.time[0] <= step*t): steps
                # strictly below that index are guaranteed event-free, so a
                # block may end there but not cross it.
                if dist.time.size:
                    next_event = max(
                        iter_forward + 1,
                        math.ceil(dist.time[0] / self.t - 1e-9),
                    )
                else:
                    next_event = self.nts - 1
                safe = min(remaining, next_event - iter_forward)
                n_block = block_max if (single_left == 0 and safe >= block_max) else 1

                try:
                    if self.line_dyn:
                        xs, ys, i_s = self._line_dyn_integrate(
                            x0, y0, i0, s0, sl0,
                            FG=_block_fg(n_block) if n_block > 1 else None,
                        )
                    else:
                        FG = _block_fg(n_block) if n_block > 1 else self.FG
                        res = FG(x0=x0, z0=y0, p=s0)
                        xs = res["xf"].full()
                        ys = res["zf"].full()
                        i_s = None
                except RuntimeError:
                    logging.critical(
                        f"Simulation failed numerically at or before {(iter_forward + 1) * self.t} [s]. "
                        f"Check the log to see if the system was stable at the initial point. "
                        f"Try reducing the disturbance, changing the operating point (reduce the loading), "
                        f"reducing the time step, changing the simulation solver, tuning model parameters, "
                        f"decrease the constant power loads... Good luck!"
                    )
                    raise

                clipped = np.clip(xs, self.xmin[:, None], self.xmax[:, None])
                limit_hit = np.any(clipped != xs, axis=0)
                first_hit = int(np.argmax(limit_hit)) if limit_hit.any() else xs.shape[1]

                if n_block == 1:
                    n_acc = 1
                    xs = clipped  # enforce the limits on the accepted step
                    if first_hit == 0:
                        single_left = single_streak
                    elif single_left:
                        single_left -= 1
                else:
                    if first_hit == 0:
                        # Already clipping at the first block step: discard the
                        # block and redo it with exact single-step clipping.
                        single_left = single_streak
                        continue
                    # Accept the violation-free prefix only; clipping is a no-op
                    # on those steps, so they match exact single-step clipping.
                    n_acc = min(first_hit, xs.shape[1])
                    if first_hit < xs.shape[1]:
                        single_left = single_streak

                self.x_full[:, iter_forward + 1 : iter_forward + 1 + n_acc] = xs[:, :n_acc]
                self.y_full[:, iter_forward + 1 : iter_forward + 1 + n_acc] = ys[:, :n_acc]
                x0 = xs[:, n_acc - 1]
                y0 = ys[:, n_acc - 1]
                if self.line_dyn:
                    i0 = i_s[:, n_acc - 1]
                iter_forward += n_acc
                pbar.update(n_acc)
                self._report_progress(iter_forward / max(self.nts - 1, 1))

                current_value = round(iter_forward * self.t, 0)
                # Log only when the first digit after the decimal changes
                (
                    logging.info(f"Simulation time is {current_value} [s]")
                    if previous_value != current_value
                    else None
                )
                previous_value = current_value

                n_pending = dist.time.size
                params_changed = self.check_disturbance(dist, iter_forward)
                if self.line_dyn:
                    sl0 = self.slinit  # pick up updated line switches after disturbance
                if dist.time.size != n_pending:
                    # A disturbance executed and rebuilt the equations (and
                    # self.FG); the cached block integrators are stale.
                    block_cache.clear()

                if params_changed:
                    self.grid.build_y()
                    self._fault_intervals.append(
                        (iter_forward, self._snapshot_branch_params())
                    )
            pbar.close()

        else:
            # Collect per-interval result blocks and concatenate once at the
            # end; growing x_full/y_full with np.hstack per disturbance
            # interval copies the whole history every time (quadratic in nts).
            # See docs/perf/06-simulate-segment-accumulation.md.
            x_segments = [x0.reshape(-1, 1)]
            y_segments = [y0.reshape(-1, 1)]
            n_cols = 1  # running column count of the segments collected so far

            total_duration = self.T_end - self.T_start
            pbar = tqdm(
                total=100,
                desc="Simulation",
                unit="%",
                bar_format="{l_bar}{bar}| {n:.1f}/{total:.0f}% [{elapsed}<{remaining}]",
            )

            for i in range(len(dist.time)):
                if not dist.time.any():
                    break
                tf = dist.time[0]  # Take the next disturbance event
                if tf > self.T_end:
                    continue
                self.tf = np.arange(self.t0 + self.t, tf + self.t - 1e-10, self.t)
                if self.tf.size == 0:
                    # Two disturbances closer together than one output step: there
                    # is nothing to integrate between them, so apply the next one
                    # at the same operating point.
                    self.check_disturbance(dist, math.ceil(tf / self.t))
                    continue
                self.fgcall()

                try:
                    if self.line_dyn:
                        xf, yf, ifinal = self._line_dyn_integrate(
                            x0, y0, i0, s0, sl0
                        )
                    else:
                        res_grid = self.FG(x0=x0, z0=y0, p=s0)
                except RuntimeError:
                    logging.critical(
                        f"Simulation failed numerically at or before time {tf}. Check the log for details. "
                        "Try reducing the disturbance, changing the operating point, "
                        "reducing the time step, or tuning model parameters."
                    )
                    raise
                logging.info(f"Simulation time is {tf} [s]")
                iter_forward = math.ceil(tf / self.t)
                if self.line_dyn:
                    i0 = ifinal[:, -1]
                else:
                    xf = res_grid["xf"].full()
                    yf = res_grid["zf"].full()

                x_segments.append(xf)
                y_segments.append(yf)
                n_cols += xf.shape[1]

                params_changed = self.check_disturbance(dist, iter_forward)
                if self.line_dyn:
                    sl0 = self.slinit  # pick up updated line switches after disturbance

                if params_changed:
                    self.grid.build_y()
                    self._fault_intervals.append(
                        (n_cols, self._snapshot_branch_params())
                    )

                self.t0 = self.tf[
                    -1
                ]  # set the beginning of the next interval as the end of the current interval

                x0 = xf[:, -1]  # initial value for the next interval
                y0 = yf[:, -1]  # initial value for the next interval

                progress = (self.t0 - self.T_start) / total_duration * 100
                pbar.n = progress
                pbar.refresh()
                self._report_progress(progress / 100.0)

            # Now do the last interval, unless the last disturbance leaves less
            # than one output step before T_end (then the trajectory is complete).
            self.tf = np.arange(self.t0 + self.t, self.T_end - 1e-10, self.t)
            if self.tf.size == 0:
                logging.warning(
                    "T_end (%s) is less than one time step (%s) after the last "
                    "disturbance at %s; the simulation ends there.",
                    self.T_end,
                    self.t,
                    self.t0,
                )
            else:
                self.fgcall()
                try:
                    if self.line_dyn:
                        xf, yf, _ifinal = self._line_dyn_integrate(x0, y0, i0, s0, sl0)
                    else:
                        res_grid = self.FG(x0=x0, z0=y0, p=s0)
                except RuntimeError:
                    logging.critical(
                        f"Simulation failed numerically at or before time {self.T_end}. Check the log for details. \n "
                        "Try reducing the disturbance, changing the operating point, "
                        "reducing the time step, or tuning model parameters."
                    )
                    raise

                if not self.line_dyn:
                    xf = res_grid["xf"].full()
                    yf = res_grid["zf"].full()

                x_segments.append(xf)
                y_segments.append(yf)
            self.x_full = np.hstack(x_segments)
            self.y_full = np.hstack(y_segments)

            pbar.n = 100
            pbar.refresh()
            pbar.close()

        self._report_progress(1.0)

        # Reconcile nts with actual data size (np.arange rounding can cause off-by-one)
        self.nts = self.x_full.shape[1]
        self.time_steps = np.linspace(self.T_start, self.T_end, self.nts)

        # Compute branch currents in post-processing (vectorized NumPy)
        self.compute_i_full()

    def _report_progress(self, fraction: float) -> None:
        """Invoke :attr:`progress_callback`, if set, with the completed fraction
        of the run clamped to [0, 1]. A callback returning ``False`` (exactly)
        cancels the run by raising
        :class:`~hermess.errors.SimulationCancelled`."""
        if self.progress_callback is None:
            return
        if self.progress_callback(min(max(fraction, 0.0), 1.0)) is False:
            raise SimulationCancelled(
                f"Simulation cancelled at {fraction:.0%} by the progress callback."
            )

    def _snapshot_branch_params(self) -> dict:
        """Snapshot the current numeric branch admittance parameters from Grid.build_y()."""
        grid = self.grid
        return {
            "C_branches": grid.C_branches.copy(),
            "y_series_r": np.real(grid.y_series).copy(),
            "y_series_i": np.imag(grid.y_series).copy(),
            "g_eff": grid.g_eff.copy(),
            "b_eff": grid.b_eff.copy(),
            "trafo": grid.tau.copy(),
        }

    def compute_i_full(self) -> None:
        """Compute branch currents from x_full and y_full in post-processing
        with vectorized NumPy.

        For has_delta_ref=False: matrix multiply C_branches @ y_full.
        For has_delta_ref=True: includes reference-frame rotation using delta_ref from x_full.
        """
        nb = self.grid.nb
        nts = self.nts
        self.i_full = np.zeros((4 * nb, nts))

        # Build reordering index: C_branches layout [fwd; rev] → i_full layout [interleaved]
        # C_branches rows: fwd[2k]=If_re_k, fwd[2k+1]=If_im_k, rev[2k]=It_re_k, rev[2k+1]=It_im_k
        # i_full rows: [4k]=If_re_k, [4k+1]=If_im_k, [4k+2]=It_re_k, [4k+3]=It_im_k
        k = np.arange(nb)
        reorder_idx = np.empty(4 * nb, dtype=int)
        reorder_idx[0::4] = 2 * k  # If_re from forward row 2k
        reorder_idx[1::4] = 2 * k + 1  # If_im from forward row 2k+1
        reorder_idx[2::4] = 2 * nb + 2 * k  # It_re from reverse row 2k
        reorder_idx[3::4] = 2 * nb + 2 * k + 1  # It_im from reverse row 2k+1

        # Determine interval boundaries from fault snapshots
        boundaries = [snap[0] for snap in self._fault_intervals] + [nts]

        for idx in range(len(self._fault_intervals)):
            start = boundaries[idx]
            end = boundaries[idx + 1]
            if start >= end:
                continue
            params = self._fault_intervals[idx][1]

            if not self.has_delta_ref:
                # No rotation needed — constant matrix multiply. C_branches is
                # built on the 2*nn voltage block; device-private algebraics
                # occupy y_full rows [2*nn:], so use the voltage block only.
                nv = 2 * self.grid.nn
                self.i_full[:, start:end] = (
                    params["C_branches"] @ self.y_full[:nv, start:end]
                )[reorder_idx, :]
            else:
                # Distributed reference frames: vectorized rotation + admittance
                self._compute_i_full_with_rotation(params, start, end)

    def _compute_i_full_with_rotation(self, params: dict, start: int, end: int) -> None:
        """Compute branch currents with reference-frame rotation (has_delta_ref=True)."""
        grid = self.grid
        nb = grid.nb

        y_sr = params["y_series_r"][:, None]  # (nb, 1) for broadcasting
        y_si = params["y_series_i"][:, None]
        G = params["g_eff"][:, None]
        B = params["b_eff"][:, None]
        trafo = params["trafo"][:, None]

        # Get delta_ref indices for from/to buses of each branch
        idx_i_bus = [grid.buses[i] for i in grid.idx_i]
        idx_j_bus = [grid.buses[j] for j in grid.idx_j]
        idx_i_delta = [self.idx_delta_ref_by_bus[b] for b in idx_i_bus]
        idx_j_delta = [self.idx_delta_ref_by_bus[b] for b in idx_j_bus]

        # Extract delta_ref angles from x_full (nb, nts_interval)
        delta_i = self.x_full[idx_i_delta, start:end]
        delta_j = self.x_full[idx_j_delta, start:end]
        delta_line = 0.5 * (delta_i + delta_j)
        theta_i = delta_i - delta_line
        theta_j = delta_j - delta_line

        cos_ti = np.cos(theta_i)
        sin_ti = np.sin(theta_i)
        cos_tj = np.cos(theta_j)
        sin_tj = np.sin(theta_j)

        # Extract bus voltages (nb, nts_interval)
        Vi_re = self.y_full[grid.idx_i_re, start:end]
        Vi_im = self.y_full[grid.idx_i_im, start:end]
        Vj_re = self.y_full[grid.idx_j_re, start:end]
        Vj_im = self.y_full[grid.idx_j_im, start:end]

        # Rotate voltages to line frame
        Vi_re_L = cos_ti * Vi_re - sin_ti * Vi_im
        Vi_im_L = sin_ti * Vi_re + cos_ti * Vi_im
        Vj_re_L = cos_tj * Vj_re - sin_tj * Vj_im
        Vj_im_L = sin_tj * Vj_re + cos_tj * Vj_im

        # Apply tap ratio on i-side
        Vi_re_Lt = Vi_re_L / trafo
        Vi_im_Lt = Vi_im_L / trafo

        # Series current: I_series = y_series * (Vi_tapped - Vj)
        dV_re = Vi_re_Lt - Vj_re_L
        dV_im = Vi_im_Lt - Vj_im_L
        I_s_re = y_sr * dV_re - y_si * dV_im
        I_s_im = y_sr * dV_im + y_si * dV_re

        # Shunt currents
        Ish_i_re = 0.5 * G * Vi_re_Lt - 0.5 * B * Vi_im_Lt
        Ish_i_im = 0.5 * G * Vi_im_Lt + 0.5 * B * Vi_re_Lt
        Ish_j_re = 0.5 * G * Vj_re_L - 0.5 * B * Vj_im_L
        Ish_j_im = 0.5 * G * Vj_im_L + 0.5 * B * Vj_re_L

        # Terminal currents in line frame
        If_re_L = I_s_re + Ish_i_re
        If_im_L = I_s_im + Ish_i_im
        It_re_L = -I_s_re + Ish_j_re
        It_im_L = -I_s_im + Ish_j_im

        # Rotate back to bus frames (inverse rotation: -theta)
        If_re_B = cos_ti * If_re_L + sin_ti * If_im_L
        If_im_B = -sin_ti * If_re_L + cos_ti * If_im_L
        It_re_B = cos_tj * It_re_L + sin_tj * It_im_L
        It_im_B = -sin_tj * It_re_L + cos_tj * It_im_L

        # Write to i_full (interleaved layout)
        self.i_full[0::4, start:end] = If_re_B
        self.i_full[1::4, start:end] = If_im_B
        self.i_full[2::4, start:end] = It_re_B
        self.i_full[3::4, start:end] = It_im_B

    def eigenvalue_analysis(self) -> None:
        """Linearize the DAE at the operating point and analyze its modes.

        Eliminates the algebraic variables to obtain the reduced state matrix
        ``A`` (``dx/dt = A dx``), then computes its eigenvalues and the
        participation factors of every mode. The results are stored on the
        object rather than returned: :attr:`A`, :attr:`eigenvalues`,
        :attr:`state_names`, :attr:`participation_factors`,
        :attr:`participation_factors_normalized` and :attr:`modes`.

        Run automatically before the simulation when
        ``config.small_signal_analysis`` is set. See :meth:`print_modal_report`
        and :meth:`participation_table` for the readable summaries, and
        :meth:`plot_eigenvalues` for the s-plane scatter.
        """

        # Helper for Reference frequency substitution
        W_sym = ca.vertcat(
            self.omega_ref, self.omega_ref_buses, self.omega_ref_lines
        )  # symbolic placeholder
        W_expr = ca.vertcat(
            self.omega_ref_expr, self.omega_ref_buses_expr, self.omega_ref_lines_expr
        )  # function of states

        # Substitute reference frequency expression in all equations
        if self.f is not None:
            f = ca.substitute(self.f, W_sym, W_expr)
        if self.g is not None:
            g = ca.substitute(self.g, W_sym, W_expr)
        if self.fnode is not None:
            fnode = ca.substitute(self.fnode, W_sym, W_expr)
        if self.fl is not None:
            fl = ca.substitute(self.fl, W_sym, W_expr)

        if self.line_dyn and self.n_priv > 0:
            # Mixed DAE: the network (voltages y_volt + line currents xl) is
            # differential, the device-private algebraics y_priv are algebraic.
            # Reduce by Schur-complementing out the privates (constrained by
            # g_priv = g[nv:]) from the differential block [x, y_volt, xl]. Note
            # g[:nv] are the device injections that feed fnode, not independent
            # algebraic equations here.
            y_volt = self.y[: self.nv]
            y_priv = self.y[self.nv :]
            g_priv = g[self.nv :]
            nd = self.nx + self.nv + self.nl  # differential variable count
            J = ca.jacobian(
                ca.vertcat(f, fnode, fl, g_priv),
                ca.vertcat(self.x, y_volt, self.xl, y_priv),
            )
            jacobian_func = ca.Function(
                "jacobian_func", [self.x, self.y, self.xl, self.s, self.sl], [J]
            )
            Ac = jacobian_func(
                self.xinit, self.yinit, self.xlinit, self.sinit, self.slinit
            )
            Ac = np.array(Ac)
            fd_d = Ac[:nd, :nd]
            fd_a = Ac[:nd, nd:]
            ga_d = Ac[nd:, :nd]
            ga_a = Ac[nd:, nd:]
            # Schur complement via a LAPACK solve on the numeric Jacobian. A
            # singular algebraic block raises and is caught below, leaving a
            # non-finite As that the guard further down skips.
            # See docs/perf/05-small-signal-schur.md.
            try:
                As = fd_d - fd_a @ np.linalg.solve(ga_a, ga_d)
            except np.linalg.LinAlgError:
                As = np.full_like(fd_d, np.nan)

        elif self.line_dyn:
            J = ca.jacobian(
                ca.vertcat(f, fnode, fl),
                ca.vertcat(self.x, self.y, self.xl),
            )
            jacobian_func = ca.Function(
                "jacobian_func", [self.x, self.y, self.xl, self.s, self.sl], [J]
            )
            Ac = jacobian_func(
                self.xinit, self.yinit, self.xlinit, self.sinit, self.slinit
            )
            As = Ac[: self.nx + self.ny + self.nl, : self.nx + self.ny + self.nl]

        else:
            J = ca.jacobian(ca.vertcat(f, g), ca.vertcat(self.x, self.y))
            jacobian_func = ca.Function("jacobian_func", [self.x, self.y, self.s], [J])
            Ac = jacobian_func(self.xinit, self.yinit, self.sinit)

            Ac = np.array(Ac)
            fx = Ac[: self.nx, : self.nx]
            fy = Ac[: self.nx, self.nx :]
            gx = Ac[self.nx :, : self.nx]
            gy = Ac[self.nx :, self.nx :]

            # Schur complement via a LAPACK solve (see comment above).
            try:
                As = fx - fy @ np.linalg.solve(gy, gx)
            except np.linalg.LinAlgError:
                As = np.full_like(fx, np.nan)

        # The small-signal eigenvalue analysis is a diagnostic; never let it
        # abort the simulation. A non-finite reduced state matrix (e.g. a
        # near-singular algebraic Jacobian gy at the operating point) is logged
        # and the analysis is skipped.
        if not np.isfinite(np.array(As)).all():
            logging.warning(
                "Eigenvalue analysis skipped: reduced state matrix is not finite "
                "(algebraic Jacobian may be singular at the operating point)."
            )
            self.eigenvalues = np.array([])
            return

        # Keep the reduced state matrix: it is the linearization of the model at
        # the operating point (dx/dt = A dx, after eliminating the algebraic
        # variables) and is what a user needs for any further analysis --
        # controllability, model reduction, control design. Rows/columns follow
        # ``self.state_names``, built below.
        self.A = np.array(As)

        # Compute eigenvalues and right eigenvectors of the reduced state matrix.
        self.eigenvalues, right_eigenvectors = np.linalg.eig(As)
        # Left eigenvectors are the rows of the inverse modal matrix. For a
        # defective/ill-conditioned modal matrix fall back to the pseudo-inverse
        # so the diagnostic still yields (approximate) participation factors
        # instead of aborting the run.
        try:
            left_eigenvectors = np.linalg.inv(right_eigenvectors)
        except np.linalg.LinAlgError:
            logging.warning(
                "Eigenvector matrix is singular; using pseudo-inverse for "
                "participation factors (eigenvalues may be defective/repeated)."
            )
            left_eigenvectors = np.linalg.pinv(right_eigenvectors)

        # Participation factor of state k in mode j: |phi_kj * psi_jk|.
        participation_factors = np.abs(right_eigenvectors * left_eigenvectors.T)
        # Normalize each mode (column) so its participations sum to 1, making them
        # comparable across modes; guard against an all-zero column.
        col_sums = participation_factors.sum(axis=0)
        col_sums[col_sums == 0] = 1.0
        participation_normalized = participation_factors / col_sums

        # Build state name list (always, not just for unstable modes)
        _device_abbrev = {
            "Synchronous_machine_transient_model": "SM",
            "Synchronous_machine_subtransient_model": "SM",
            "Synchronous_machine_subtransient_model_Sauer_Pai": "SM_SP",
            "Synchronous_machine_subtransient_model_Sauer_Pai_6th_order": "SM_SP6",
            "GridForming_inverter_model": "GFM",
            "GridSupporting_inverter_model": "GFL",
            "Static_load_power": "SLP",
            "Static_load_impedance": "SLZ",
            "Static_load_ZIP": "ZIP",
            "Infinite_bus": "INF",
        }
        # Use the devices and grid bound to THIS Dae, not the module globals:
        # run() reloads this module in place, so the globals always describe
        # the most recently built system, and a lazy eigenvalue_analysis() on
        # an earlier run would label (or mis-count) its states from the wrong
        # system.
        state_names = []
        for item in self.device_list:
            short = _device_abbrev.get(item._name, item._name[:6])
            for i in range(item.n):
                for state in item.states:
                    state_names.append(f"{short}@{item.bus[i]}:{state}")

        if self.line_dyn:
            # Dynamic-network states: branch currents (LINE_i-j) and the
            # algebraic-turned-differential node voltages (BUS_n).
            line = self.grid.line
            for i in range(self.grid.nb):
                for state in line.states:
                    state_names.append(
                        f"LINE_{line.bus_i[i]}-{line.bus_j[i]}:{state}"
                    )
            for i in range(self.grid.nn):
                for state in ["vre", "vim"]:
                    state_names.append(f"BUS_{self.grid.buses[i]}:{state}")

        self.participation_factors = participation_factors
        self.participation_factors_normalized = participation_normalized
        self.state_names = state_names
        self.modes = self._build_modes(participation_normalized)

        unstable_modes = [e for e in self.eigenvalues if np.real(e) > 1e-4]
        if unstable_modes:
            logging.error(
                f"The operating point seems unstable. It has unstable modes: {np.array(unstable_modes)}.\n "
                f"The simulation will potentially fail. Known causes: too much fix power loads, model parameter issues..."
            )

    def _build_modes(self, participation_normalized: np.ndarray) -> list:
        """Collapse the raw eigenvalues into physical modes (complex-conjugate
        pairs merged) and attach the modal metrics used by the reports.

        Returns a list of mode dicts sorted by damping ratio (most critical
        first). Each carries the representative eigenvalue, natural frequency
        [Hz], damping ratio, and that mode's normalized participation column.
        """
        eigs = np.asarray(self.eigenvalues)
        names = self.state_names
        n = eigs.size
        used = np.zeros(n, dtype=bool)
        modes = []
        for i in range(n):
            if used[i]:
                continue
            used[i] = True
            lam = eigs[i]
            members = [i]
            if abs(lam.imag) > 1e-9:
                # Pair with the closest still-unused conjugate, if present.
                best_j, best_err = None, np.inf
                for j in range(n):
                    if used[j]:
                        continue
                    err = abs(eigs[j] - np.conj(lam))
                    if err < best_err:
                        best_err, best_j = err, j
                if best_j is not None and best_err < 1e-6 * (abs(lam) + 1.0):
                    used[best_j] = True
                    members.append(best_j)
            # Representative = the member with non-negative imaginary part.
            rep = members[int(np.argmax([eigs[m].imag for m in members]))]
            lam = eigs[rep]
            sigma, omega = float(lam.real), abs(float(lam.imag))
            denom = math.hypot(sigma, omega)
            zeta = (-sigma / denom) if denom > 1e-12 else 0.0
            pf = participation_normalized[:, rep]
            order = np.argsort(pf)[::-1]
            dominant = [(names[k], float(pf[k])) for k in order if pf[k] > 0]
            modes.append(
                {
                    "members": members,
                    "rep_idx": rep,
                    "eig": complex(lam),
                    "sigma": sigma,
                    "omega": omega,
                    "freq_hz": omega / (2.0 * math.pi),
                    "zeta": zeta,
                    "is_complex": len(members) == 2,
                    "participation": pf,
                    "dominant": dominant,
                }
            )
        # Most critical (least damped) modes first.
        modes.sort(key=lambda m: m["zeta"])
        for idx, m in enumerate(modes):
            m["id"] = idx + 1
        return modes

    def print_modal_report(self, top_k: int = 4) -> str:
        """Print a per-mode small-signal summary and return it as a string.

        One row per physical mode (complex-conjugate pairs collapsed), with the
        eigenvalue, natural frequency, damping ratio and the dominant states.
        Modes are sorted by damping ratio so the most critical appear first.
        """
        if self.eigenvalues is None or len(self.eigenvalues) == 0 or not self.modes:
            logging.info("No eigenvalue data available; skipping modal report.")
            return ""

        rows = []
        for m in self.modes:
            lam = m["eig"]
            if m["is_complex"]:
                eig_str = f"{lam.real:+.3f} ± {m['omega']:.3f}j"
                freq_str = f"{m['freq_hz']:.3f}"
            else:
                eig_str = f"{lam.real:+.3f}"
                freq_str = "—"
            if abs(m["eig"]) < 1e-4:
                flag = "zero"
            elif m["sigma"] > 1e-4:
                flag = "UNSTABLE"
            elif m["zeta"] < 0.05:
                flag = "low ζ"
            else:
                flag = ""
            dom = ", ".join(
                f"{name} ({frac * 100:.0f}%)" for name, frac in m["dominant"][:top_k]
            )
            rows.append(
                [m["id"], eig_str, freq_str, f"{m['zeta'] * 100:+.1f}", flag, dom]
            )

        headers = [
            "#",
            "Eigenvalue (σ±jω)",
            "f [Hz]",
            "ζ [%]",
            "Flag",
            f"Dominant states (top {top_k}, participation %)",
        ]
        table = tabulate(
            rows, headers=headers, tablefmt="github", disable_numparse=True
        )
        n_unstable = sum(1 for m in self.modes if m["sigma"] > 1e-4)
        header_line = (
            f"Small-signal modal analysis: {len(self.modes)} modes "
            f"({n_unstable} unstable) over {len(self.state_names)} states, "
            "sorted by damping ratio (most critical first)."
        )
        report = header_line + "\n" + table
        print("\n" + report + "\n")
        return report

    def participation_table(self, mode: int = 1, top: int | None = 10):
        """Participation factors of one mode as a pandas DataFrame.

        ``mode`` is the mode id shown by :meth:`print_modal_report` (1 = least
        damped). The rows are the states, sorted by participation, with the
        normalized factor in [0, 1]. ``top=None`` returns every state.
        """
        import pandas as pd

        if not getattr(self, "modes", None):
            logging.info("No eigenvalue data available; run eigenvalue_analysis() first.")
            return pd.DataFrame()
        match = [m for m in self.modes if m["id"] == mode]
        if not match:
            raise KeyError(f"no mode with id {mode}; ids run 1..{len(self.modes)}")
        m = match[0]
        df = pd.DataFrame(
            {"state": [n for n, _ in m["dominant"]],
             "participation": [round(p, 4) for _, p in m["dominant"]]}
        )
        df.attrs["mode"] = mode
        df.attrs["eigenvalue"] = m["eig"]
        df.attrs["freq_hz"] = m["freq_hz"]
        df.attrs["zeta"] = m["zeta"]
        return df.head(top) if top else df

    def plot_eigenvalues(self, damping_ref: float = 0.05) -> None:
        """Simple eigenvalue (s-plane) scatter of the reduced state matrix.

        Every eigenvalue is plotted in the complex plane with the imaginary axis
        as the stability boundary. Points are colored red = unstable (Re>0),
        orange = lightly damped (ζ < ``damping_ref``), blue = well damped, grey =
        marginal (near the origin). A dashed wedge marks the constant-damping
        locus ζ = ``damping_ref``. When the spectrum is very wide (fast real
        modes far in the left half-plane) a second panel zooms in near the
        imaginary axis, where the slow/critical modes live. Unstable eigenvalues
        are annotated when there are only a few.
        """
        import matplotlib.pyplot as plt

        if self.eigenvalues is None or len(self.eigenvalues) == 0:
            logging.info("No eigenvalue data available; skipping eigenvalue plot.")
            return

        eigs = np.asarray(self.eigenvalues)
        re, im = eigs.real, eigs.imag
        mag = np.abs(eigs)
        with np.errstate(divide="ignore", invalid="ignore"):
            zeta = np.where(mag > 1e-12, -re / mag, 0.0)

        marginal = mag < 1e-4
        unstable = (re > 1e-4) & ~marginal
        lightly = (~unstable) & (~marginal) & (zeta < damping_ref)
        stable = ~(marginal | unstable | lightly)

        osc = np.abs(im) > 1e-6
        if osc.any():
            x_focus = max(5.0, 1.5 * float(np.abs(re[osc]).max()))
            y_focus = 1.1 * float(np.abs(im).max())
        else:
            x_focus = max(5.0, 1.5 * float(np.median(np.abs(re)) or 1.0))
            y_focus = 1.0
        # A zoom panel only helps when fast real modes push the full range far
        # past the slow/oscillatory cluster.
        need_zoom = re.size > 1 and float(re.min()) < -1.5 * x_focus

        def draw(ax, annotate):
            ax.axhline(0.0, color="0.7", lw=0.6, zorder=0)
            ax.axvline(0.0, color="k", lw=1.2, zorder=1)  # stability boundary
            if 0.0 < damping_ref < 1.0 and osc.any():
                w = float(np.abs(im).max()) * 1.05
                slope = damping_ref / np.sqrt(1.0 - damping_ref**2)
                ax.plot([0, -slope * w], [0, w], ls="--", color="#E07000", lw=0.9)
                ax.plot(
                    [0, -slope * w],
                    [0, -w],
                    ls="--",
                    color="#E07000",
                    lw=0.9,
                    label=f"ζ = {damping_ref * 100:.0f}%",
                )
            for mask, color, lbl, mk in (
                (stable, "#1f77b4", "stable", "o"),
                (lightly, "#E07000", f"lightly damped (ζ<{damping_ref * 100:.0f}%)", "o"),
                (unstable, "#CC0000", "unstable (Re>0)", "o"),
                (marginal, "#999999", "marginal (≈0)", "s"),
            ):
                if np.any(mask):
                    ax.scatter(
                        re[mask], im[mask], s=42, c=color, marker=mk,
                        edgecolors="black", linewidths=0.4, label=lbl, zorder=3,
                    )
            if annotate:
                idx = np.where(unstable)[0]
                if 0 < idx.size <= 10:
                    for k in idx:
                        sign = "+" if im[k] >= 0 else "−"
                        ax.annotate(
                            f"{re[k]:.2g}{sign}{abs(im[k]):.2g}j",
                            (re[k], im[k]), textcoords="offset points",
                            xytext=(6, 4), fontsize=7, color="#CC0000",
                        )
            ax.set_xlabel("Real part  σ  [1/s]")
            ax.grid(True, alpha=0.25, zorder=0)

        ncols = 2 if need_zoom else 1
        fig, axes = plt.subplots(
            1, ncols, figsize=(7.7 * ncols, 7.0), squeeze=False
        )
        axes = axes[0]

        draw(axes[0], annotate=not need_zoom)
        axes[0].set_ylabel("Imaginary part  ω  [rad/s]")
        axes[0].legend(loc="upper left", fontsize=8, framealpha=0.9)

        if need_zoom:
            axes[0].set_title("Full spectrum")
            draw(axes[1], annotate=True)
            axes[1].set_xlim(-x_focus, 0.06 * x_focus)
            axes[1].set_ylim(-y_focus, y_focus)
            axes[1].set_title(f"Zoom near imaginary axis (σ > −{x_focus:.0f})")
            fig.suptitle(
                f"Eigenvalue spectrum (s-plane) — {eigs.size} eigenvalues, "
                f"{int(unstable.sum())} unstable",
                fontsize=12,
            )
        else:
            axes[0].set_title(
                f"Eigenvalue spectrum (s-plane) — {eigs.size} eigenvalues, "
                f"{int(unstable.sum())} unstable"
            )
        fig.tight_layout()

    def _render_participation_heatmap(
        self,
        modes: list,
        title: str,
        max_states: Optional[int] = 35,
        min_participation: float = 0.02,
        annotate: bool = True,
    ) -> None:
        """Render one participation-factor heatmap for a pre-selected, already
        ordered list of modes. Shared by the damping overview and the banded
        frequency views. Cells below ``min_participation`` are greyed out and
        states that never reach it (in the shown modes) are dropped; the row axis
        is capped at ``max_states`` strongest participants.
        """
        import matplotlib.pyplot as plt

        if not modes:
            return

        pf = np.column_stack([m["participation"] for m in modes])
        state_names = list(self.state_names)
        n_states_total = len(state_names)

        # Keep only states that participate meaningfully, then cap the row count.
        peak = pf.max(axis=1)
        relevant = np.where(peak >= min_participation)[0]
        if relevant.size == 0:
            relevant = np.argsort(peak)[::-1][: (max_states or n_states_total)]
        if max_states and relevant.size > max_states:
            relevant = relevant[np.argsort(peak[relevant])[::-1][:max_states]]
        relevant = np.sort(relevant)
        pf = pf[relevant, :]
        state_names = [state_names[k] for k in relevant]

        n_states, n_modes = pf.shape
        if n_states < n_states_total:
            print(
                f"  [{title}] showing {n_modes} modes and "
                f"{n_states}/{n_states_total} states (participation >= "
                f"{min_participation:g})."
            )

        vmax = max(float(pf.max()), 1e-9)
        pf_masked = np.ma.masked_less(pf, min_participation)
        cmap = plt.get_cmap("viridis").copy()
        cmap.set_bad("#ECECEC")

        def mode_label(m):
            if m["is_complex"]:
                return f"#{m['id']}  {m['freq_hz']:.2f} Hz  ζ{m['zeta'] * 100:.0f}%"
            return f"#{m['id']}  real  σ{m['sigma']:+.2g}"

        col_labels = [mode_label(m) for m in modes]

        fig_w = min(max(0.55 * n_modes + 4.0, 7.0), 32.0)
        fig_h = min(max(0.5 * n_states + 2.0, 4.0), 26.0)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        im = ax.imshow(pf_masked, aspect="auto", cmap=cmap, vmin=0.0, vmax=vmax)

        fs = 9 if max(n_states, n_modes) <= 35 else 7
        ax.set_xticks(range(n_modes))
        ax.set_xticklabels(col_labels, fontsize=fs, rotation=90)
        ax.set_yticks(range(n_states))
        ax.set_yticklabels(state_names, fontsize=fs)
        ax.tick_params(length=0)
        ax.set_xlabel("Mode", fontsize=10)

        # Flag critical modes via x-tick label colors.
        for j, m in enumerate(modes):
            lbl = ax.get_xticklabels()[j]
            if m["sigma"] > 1e-4:
                lbl.set_color("#CC0000")
                lbl.set_fontweight("bold")
            elif m["zeta"] < 0.05 and abs(m["eig"]) >= 1e-4:
                lbl.set_color("#E07000")
                lbl.set_fontweight("bold")

        # Annotate only when the grid is small enough to stay readable.
        if annotate and n_states * n_modes <= 400:
            for i in range(n_states):
                for j in range(n_modes):
                    v = pf[i, j]
                    if v >= min_participation:
                        ax.text(
                            j,
                            i,
                            f"{v:.2f}",
                            ha="center",
                            va="center",
                            fontsize=max(fs - 2, 6),
                            color="white" if v < 0.55 * vmax else "black",
                        )

        cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cbar.set_label("Normalized participation", fontsize=9)
        cbar.ax.tick_params(labelsize=8)

        ax.set_title(
            f"{title}\n"
            "red label = unstable · orange = lightly damped (ζ<5%) · "
            "grey cell = negligible",
            fontsize=11,
        )
        fig.tight_layout()

    def plot_participation_factors(
        self,
        max_modes: Optional[int] = 25,
        max_states: Optional[int] = 35,
        min_participation: float = 0.02,
        annotate: bool = True,
    ) -> None:
        """Single participation-factor heatmap of the most critical modes.

        Modes are sorted by damping ratio (most critical first) and the view is
        focused for legibility on large systems: only the first ``max_modes`` and
        the states that participate meaningfully in them are shown. Pass
        ``max_modes=None`` / ``max_states=None`` to show everything. For the
        frequency-banded views (one figure per band) use
        :meth:`plot_participation_bands`.
        """
        if self.eigenvalues is None or len(self.eigenvalues) == 0 or not self.modes:
            logging.info(
                "No eigenvalue data available; skipping participation plot."
            )
            return

        modes = self.modes[:max_modes] if max_modes else list(self.modes)
        self._render_participation_heatmap(
            modes,
            "Participation factors — states × modes (most critical first)",
            max_states=max_states,
            min_participation=min_participation,
            annotate=annotate,
        )

    def plot_participation_bands(
        self,
        max_states: Optional[int] = 35,
        min_participation: float = 0.02,
        annotate: bool = True,
    ) -> None:
        """Frequency-banded participation heatmaps — one figure per band.

        The modes are split into non-oscillatory (real) modes and four frequency
        bands; a figure is produced only for a band that actually contains modes.
        Within a band the modes are frequency-sorted (real modes are ordered by
        proximity to instability). Bands: real · 0–0.1 Hz · 0.1–2 Hz (electro-
        mechanical) · 2–50 Hz · >50 Hz.
        """
        if self.eigenvalues is None or len(self.eigenvalues) == 0 or not self.modes:
            logging.info(
                "No eigenvalue data available; skipping participation plots."
            )
            return

        bands = [
            (
                "Non-oscillatory (real) modes",
                lambda m: not m["is_complex"],
                lambda m: -m["sigma"],  # closest to instability first
            ),
            (
                "Oscillatory modes 0–0.1 Hz",
                lambda m: m["is_complex"] and m["freq_hz"] <= 0.1,
                lambda m: m["freq_hz"],
            ),
            (
                "Oscillatory modes 0.1–2 Hz (electromechanical)",
                lambda m: m["is_complex"] and 0.1 < m["freq_hz"] <= 2.0,
                lambda m: m["freq_hz"],
            ),
            (
                "Oscillatory modes 2–50 Hz",
                lambda m: m["is_complex"] and 2.0 < m["freq_hz"] <= 50.0,
                lambda m: m["freq_hz"],
            ),
            (
                "Oscillatory modes > 50 Hz",
                lambda m: m["is_complex"] and m["freq_hz"] > 50.0,
                lambda m: m["freq_hz"],
            ),
        ]

        any_shown = False
        for title, predicate, sort_key in bands:
            subset = sorted(
                (m for m in self.modes if predicate(m)), key=sort_key
            )
            if not subset:
                continue
            any_shown = True
            self._render_participation_heatmap(
                subset,
                title,
                max_states=max_states,
                min_participation=min_participation,
                annotate=annotate,
            )
        if not any_shown:
            logging.info("No modes to plot in any frequency band.")


# create the simulation grid
grid_sim = GridSim()
# initialize the DAE class
dae_sim = DaeSim()

bus_init_sim = BusInit()


line_sim = Line()

disturbance_sim = Disturbance()

device_list_sim = []


def stack_volt_power(vre, vim) -> np.ndarray:
    u_power = np.hstack((np.vstack((vre, vim)), np.vstack((vim, -vre))))
    return u_power
