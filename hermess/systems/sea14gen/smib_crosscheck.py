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

# Single-machine-infinite-bus cross-check of GENROU (+AVRST1A).
#
# The same physical setup is linearized twice:
#   (a) by the simulator's own eigenvalue machinery on a 2-bus system
#       (machine at bus M, infinite bus at bus I, line in between);
#   (b) by an independent, hand-coded linearization of the PDF equations
#       (11)-(24) with the stator and network eliminated algebraically
#       (numeric finite differences on the reduced ODE).
# Agreement isolates implementation errors from system-data issues.

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# BPS_2-like parameters on its own base (machine base values, Sb = S_machine):
P = dict(H=3.2, Xa=0.20, Xd=1.80, Xq=1.75, Xd1=0.30, Td01=8.50,
         Xd2=0.21, Td02=0.040, Xq1=0.70, Tq01=0.30, Xq2=0.21, Tq02=0.080)
AVR = dict(KA=400.0, TA=0.02, TB=1.12, TC=0.50)  # BPS_2 ST1A, no 2nd LL
XLINE = 0.30           # tie reactance to the infinite bus
P0, V0 = 0.8, 1.0      # operating point: P at machine bus, |V| at machine bus
FN = 50.0


def solve_operating_point():
    """Loadflow of the SMIB: machine bus PV (P0, V0), infinite bus slack 1.0."""
    # V_m = V0·e^{jθ}; P0 = V0·Vinf·sin(θ)/X
    theta = np.arcsin(P0 * XLINE / (V0 * 1.0))
    vm = V0 * np.exp(1j * theta)
    i_net = (vm - 1.0) / (1j * XLINE)  # injection into the network
    s = vm * np.conj(i_net)
    return vm, i_net, s


def machine_init(vm, i_inj):
    """Steady state of eqs. (11)-(24) for terminal voltage vm and injected
    current i_inj (machine base, generator convention)."""
    # rotor angle from the q-axis phasor E_q = vm + jXq·i
    eq_ph = vm + 1j * P["Xq"] * i_inj
    delta = np.angle(eq_ph)
    rot = np.exp(-1j * (delta - np.pi / 2))  # network -> dq (d leads q axis)
    v_dq = vm * rot
    i_dq = i_inj * rot
    vd, vq = v_dq.real, v_dq.imag
    id_, iq = i_dq.real, i_dq.imag

    psi2q = vd - P["Xq2"] * iq
    psi2d = vq + P["Xd2"] * id_

    # q-axis: dE'd=0 & dpsi_kq=0  ->  psi_kq = E'd - (Xq1-Xa)iq and
    # K1q E'd + K2q psi_kq + K3q iq = 0
    k1q = -(1 + (P["Xq"] - P["Xq1"]) * (P["Xq1"] - P["Xq2"]) / (P["Xq1"] - P["Xa"]) ** 2)
    k2q = -(1 + k1q)
    k3q = (P["Xq"] - P["Xq1"]) * (P["Xq2"] - P["Xa"]) / (P["Xq1"] - P["Xa"])
    # E'd from the two conditions:
    ed1 = -(k3q * iq + k2q * (-(P["Xq1"] - P["Xa"]) * iq)) / (k1q + k2q)
    psikq = ed1 - (P["Xq1"] - P["Xa"]) * iq

    # d-axis: psi_kd = E'q - (Xd1-Xa)id ; psi2d identity fixes E'q
    c1d = (P["Xd2"] - P["Xa"]) / (P["Xd1"] - P["Xa"])
    c2d = (P["Xd1"] - P["Xd2"]) / (P["Xd1"] - P["Xa"])
    # psi2d = c1d E'q + c2d (E'q - (Xd1-Xa) id)  ->  E'q
    eq1 = (psi2d + c2d * (P["Xd1"] - P["Xa"]) * id_) / (c1d + c2d)
    psikd = eq1 - (P["Xd1"] - P["Xa"]) * id_

    k1d = 1 + (P["Xd"] - P["Xd1"]) * (P["Xd1"] - P["Xd2"]) / (P["Xd1"] - P["Xa"]) ** 2
    k2d = 1 - k1d
    k3d = (P["Xd"] - P["Xd1"]) * (P["Xd2"] - P["Xa"]) / (P["Xd1"] - P["Xa"])
    efd = k1d * eq1 + k2d * psikd + k3d * id_

    pe = psi2d * iq + psi2q * id_ + (P["Xq2"] - P["Xd2"]) * id_ * iq
    return dict(delta=delta, eq1=eq1, psikd=psikd, ed1=ed1, psikq=psikq,
                efd=efd, pe=pe, vd=vd, vq=vq, id=id_, iq=iq)


def reduced_rhs(x, vref):
    """RHS of the reduced SMIB ODE. x = [delta, omega, E'q, psi_kd, E'd,
    psi_kq, Vll, Efd]; stator+network eliminated each call."""
    delta, omega, eq1, psikd, ed1, psikq, vll, efd = x

    c1d = (P["Xd2"] - P["Xa"]) / (P["Xd1"] - P["Xa"])
    c2d = (P["Xd1"] - P["Xd2"]) / (P["Xd1"] - P["Xa"])
    c1q = (P["Xq2"] - P["Xa"]) / (P["Xq1"] - P["Xa"])
    c2q = (P["Xq1"] - P["Xq2"]) / (P["Xq1"] - P["Xa"])
    psi2d = c1d * eq1 + c2d * psikd
    psi2q = c1q * ed1 + c2q * psikq

    # network: machine bus voltage = inf bus + jX·i ; stator (17)-(18).
    # In dq (rotating with delta): v_inf in dq = e^{-j(delta-pi/2)}·1.0
    rot = np.exp(-1j * (delta - np.pi / 2))
    vinf_dq = rot * 1.0
    vinf_d, vinf_q = vinf_dq.real, vinf_dq.imag
    # Solve for (id, iq) from network + stator in the dq frame:
    #   network (v_dq = vinf_dq + jX·i_dq): vd = vinf_d - XLINE·iq, vq = vinf_q + XLINE·id
    #   stator:                             vd = Xq2·iq + psi2q,     vq = -Xd2·id + psi2d
    iq = (vinf_d - psi2q) / (P["Xq2"] + XLINE)
    id_ = (psi2d - vinf_q) / (P["Xd2"] + XLINE)
    vd = P["Xq2"] * iq + psi2q
    vq = -P["Xd2"] * id_ + psi2d
    vt = np.hypot(vd, vq)

    k1d = 1 + (P["Xd"] - P["Xd1"]) * (P["Xd1"] - P["Xd2"]) / (P["Xd1"] - P["Xa"]) ** 2
    k2d = 1 - k1d
    k3d = (P["Xd"] - P["Xd1"]) * (P["Xd2"] - P["Xa"]) / (P["Xd1"] - P["Xa"])
    k1q = -(1 + (P["Xq"] - P["Xq1"]) * (P["Xq1"] - P["Xq2"]) / (P["Xq1"] - P["Xa"]) ** 2)
    k2q = -(1 + k1q)
    k3q = (P["Xq"] - P["Xq1"]) * (P["Xq2"] - P["Xa"]) / (P["Xq1"] - P["Xa"])

    pe = psi2d * iq + psi2q * id_ + (P["Xq2"] - P["Xd2"]) * id_ * iq

    # AVR ST1A (no transducer, single lead-lag TC/TB, gain KA/(1+sTA))
    u0 = vref - vt
    dvll = (u0 - vll) / AVR["TB"]
    y1 = vll * (1 - AVR["TC"] / AVR["TB"]) + (AVR["TC"] / AVR["TB"]) * u0
    defd = (AVR["KA"] * y1 - efd) / AVR["TA"]

    pm = PM0
    return np.array([
        2 * np.pi * FN * (omega - 1.0),
        (pm - pe) / (2 * P["H"]),
        (efd - (k1d * eq1 + k2d * psikd + k3d * id_)) / P["Td01"],
        (eq1 - psikd - (P["Xd1"] - P["Xa"]) * id_) / P["Td02"],
        (k1q * ed1 + k2q * psikq + k3q * iq) / P["Tq01"],
        (ed1 - psikq - (P["Xq1"] - P["Xa"]) * iq) / P["Tq02"],
        dvll,
        defd,
    ])


def main() -> None:
    global PM0
    vm, i_inj, s = solve_operating_point()
    op = machine_init(vm, i_inj)
    PM0 = op["pe"]

    x0 = np.array([op["delta"], 1.0, op["eq1"], op["psikd"], op["ed1"],
                   op["psikq"], 0.0, op["efd"]])
    # consistent AVR equilibrium: Efd = KA·(vref - vt), vll = u0
    vt0 = np.hypot(op["vd"], op["vq"])
    vref = vt0 + op["efd"] / AVR["KA"]
    x0[6] = vref - vt0

    r0 = reduced_rhs(x0, vref)
    print("analytic init x0:", np.array2string(x0, precision=4))
    print("reference RHS rows at analytic init:",
          np.array2string(r0, precision=2))

    # Independent root from a clearly physical guess: solve the 8 equations
    # for the 8 states with (vref, Pm) chosen to hit (V0, P0) — append those
    # two conditions and solve for [x, vref, Pm].
    from scipy.optimize import fsolve

    def full_res(z):
        x, vref_, pm_ = z[:8], z[8], z[9]
        globals()["PM0"] = pm_
        r = reduced_rhs(x, vref_)
        # terminal conditions: |V| = V0 and Pe = P0  (recompute like the rhs)
        delta = x[0]
        c1d = (P["Xd2"] - P["Xa"]) / (P["Xd1"] - P["Xa"])
        c2d = (P["Xd1"] - P["Xd2"]) / (P["Xd1"] - P["Xa"])
        c1q = (P["Xq2"] - P["Xa"]) / (P["Xq1"] - P["Xa"])
        c2q = (P["Xq1"] - P["Xq2"]) / (P["Xq1"] - P["Xa"])
        psi2d = c1d * x[2] + c2d * x[3]
        psi2q = c1q * x[4] + c2q * x[5]
        rot = np.exp(-1j * (delta - np.pi / 2))
        vinf_dq = rot * 1.0
        iq = (vinf_dq.real - psi2q) / (P["Xq2"] + XLINE)
        id_ = (psi2d - vinf_dq.imag) / (P["Xd2"] + XLINE)
        vd = P["Xq2"] * iq + psi2q
        vq = -P["Xd2"] * id_ + psi2d
        pe = psi2d * iq + psi2q * id_ + (P["Xq2"] - P["Xd2"]) * id_ * iq
        return np.concatenate([r, [np.hypot(vd, vq) - V0, pe - P0]])

    z_guess = np.array([0.6, 1.0, 1.1, 1.0, -0.5, -0.4, 0.0, 2.0, 1.0, P0])
    z_star = fsolve(full_res, z_guess, full_output=False, xtol=1e-12)
    print("\nfsolve physical-root states "
          "[delta, w, E'q, psi_kd, E'd, psi_kq, vll, Efd, vref, Pm]:")
    print(np.array2string(z_star, precision=4))
    globals()["PM0"] = z_star[9]
    x0 = z_star[:8]
    vref = z_star[8]

    # numeric Jacobian
    n = len(x0)
    J = np.zeros((n, n))
    h = 1e-7
    for k in range(n):
        xp, xm = x0.copy(), x0.copy()
        xp[k] += h
        xm[k] -= h
        J[:, k] = (reduced_rhs(xp, vref) - reduced_rhs(xm, vref)) / (2 * h)
    eig_ref = np.linalg.eigvals(J)
    eig_ref = eig_ref[np.argsort(-eig_ref.imag)]
    print("\nindependent linearization eigenvalues:")
    for e in eig_ref:
        if e.imag >= 0:
            print(f"   {e.real:+9.4f} {e.imag:+9.4f}j")

    # ---- (a) same setup through the simulator -------------------------------
    case_dir = HERE / "smib"
    case_dir.mkdir(exist_ok=True)
    theta = np.degrees(np.angle(vm))
    pgen = -(s.real) * 100
    qgen = -(s.imag) * 100
    sim = f"""
BusInit, bus = "M", p = {pgen:.10g}, v = {V0}, type = "PV"
BusInit, bus = "I", p = 0, v = 1.0, type = "slack"
Line, bus_i = "M", bus_j = "I", r = 0, x = {XLINE}, g = 0, b = 0, trafo = 1
StaticInfiniteBus, bus = "I", Sn = 100, fn = 50, r = 0, x = 1e-6
GENROU, idx = "G1", bus = "M", avr = "AVRST1A", governor = "GOVCONST",
\tSn = 100, fn = 50, H = {P['H']}, D = 0, f = 0, R_s = 0,
\tx_a = {P['Xa']}, x_d = {P['Xd']}, x_q = {P['Xq']}, x_dprim = {P['Xd1']},
\tx_qprim = {P['Xq1']}, x_dsec = {P['Xd2']}, x_qsec = {P['Xq2']},
\tT_d0prim = {P['Td01']}, T_q0prim = {P['Tq01']}, T_d0sec = {P['Td02']}, T_q0sec = {P['Tq02']},
\tKA = {AVR['KA']}, TA = {AVR['TA']}, Tr = 1e-5, TB = {AVR['TB']}, TC = {AVR['TC']}, TB1 = 1e-5, TC1 = 1e-5
"""
    (case_dir / "sim_param.txt").write_text(sim)

    from hermess.config import config
    from hermess import system
    from hermess.utils import data_loader

    with open(case_dir / "sim_param.txt") as fid:
        data_loader.read(fid, "sim")
    system.grid_sim.add_lines(system.line_sim)
    for item in system.device_list_sim:
        if item.properties["xy_index"]:
            item.xy_index(system.dae_sim, system.grid_sim)
    new_config = config.updated(
        testsystemfile="smib", system_root=HERE, fn=50, Sb=100,
        omega_mode="nom", ts=1e-3, T_start=0.0, T_end=0.01,
        plot=False, plot_voltage=False, plot_diff=False, log_level="WARNING",
        incl_lim=False, line_dyn=False, skip_disturance=True,
        print_power_flow=False, small_signal_analysis=False)
    dae = system.dae_sim
    dae.t = new_config.ts
    dae.grid = system.grid_sim
    dae.device_list = system.device_list_sim
    dae.bus_init = system.bus_init_sim
    dae.setup(**vars(new_config))
    system.grid_sim.setup(dae=dae, bus_init=system.bus_init_sim)
    for item in system.device_list_sim:
        if item.properties["finit"]:
            item.finit(dae)
    for item in system.device_list_sim:
        if item.properties["fgcall"]:
            item.fgcall(dae)
    system.grid_sim.gcall(dae, line=system.line_sim)
    dae.check_initialization()
    dae.update_omega()
    dae.eigenvalue_analysis()
    eigs = np.asarray(dae.eigenvalues)
    eigs = eigs[np.abs(eigs) > 1e-6]
    print("\nsimulator eigenvalues (|e|>1e-6, Im>=0):")
    for e in sorted(eigs, key=lambda z: -z.imag):
        if e.imag >= -1e-9 and abs(e) < 1e4:
            print(f"   {e.real:+9.4f} {e.imag:+9.4f}j")

    # ---- evaluate the reference physics at the simulator's equilibrium ------
    m = next(d for d in system.device_list_sim if "Synchronous" in d._name)
    xs = np.asarray(dae.xinit, dtype=float)
    sim_state = {
        name: xs[int(m.__dict__[name][0])]
        for name in ["delta", "omega", "e_qprim", "psi_kd", "e_dprim",
                     "psi_kq", "Efd"]
    }
    x_ref = np.array([
        sim_state["delta"], sim_state["omega"], sim_state["e_qprim"],
        sim_state["psi_kd"], sim_state["e_dprim"], sim_state["psi_kq"],
        0.0, sim_state["Efd"],
    ])
    PM_sim = float(np.asarray(m.Pref, dtype=float)[0])
    globals()["PM0"] = PM_sim
    r = reduced_rhs(x_ref, vref=0.0)  # AVR rows (6,7) not meaningful here
    names = ["delta", "omega", "e_qprim", "psi_kd", "e_dprim", "psi_kq"]
    print("\nreference RHS rows at the SIMULATOR equilibrium "
          "(zero ⇒ same physics):")
    for k, nm in enumerate(names):
        print(f"   {nm:8s} {r[k]:+12.3e}")
    print(f"   (sim delta={sim_state['delta']:.4f}, "
          f"E'q={sim_state['e_qprim']:.4f}, E'd={sim_state['e_dprim']:.4f}, "
          f"Efd={sim_state['Efd']:.4f}, Pm={PM_sim:.4f})")


if __name__ == "__main__":
    main()
