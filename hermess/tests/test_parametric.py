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

"""Tests of the parametric build (Config(parametric=True)).

Three claims, per docs/differentiability_plan.md phase 1:

* the parametric run is the numeric run: same trajectories (to floating point
  association) and identical eigenvalues, with the numeric attributes restored;
* the parameter symbols sit where the physical parameters sit: substituting
  the values reproduces the numeric right-hand side at machine precision, and
  the parameter Jacobian is non-trivial;
* the gradient of a trajectory functional with respect to a machine inertia
  and a converter droop gain matches finite differences.
"""

import casadi as ca
import numpy as np

from hermess.config import config
from hermess.run import run


def base_config(**overrides):
    settings = dict(
        testsystemfile="3bus",
        omega_mode="nom",
        fn=50,
        Sb=100,
        ts=0.005,
        T_start=0.0,
        int_scheme_sim="idas",
        int_scheme_sim_options={"reltol": 1e-10, "max_num_steps": 10000},
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        log_level="ERROR",
        incl_lim=False,
        line_dyn=False,
        skip_disturance=False,
        debug_check_init=False,
        print_power_flow=False,
        small_signal_analysis=False,
    )
    settings.update(overrides)
    return config.updated(**settings)


def find_device(sim, param):
    for dev in sim.device_list:
        if param in dev._params and dev.properties.get("fgcall"):
            return dev
    raise AssertionError(f"no device with parameter '{param}'")


def test_parametric_run_matches_numeric():
    # T_end past the OPEN_LINE event at t = 3 s, so the parametric run also
    # exercises the numeric mid-run rebuild after the attribute restore.
    cfg = base_config(T_end=3.5)

    sim_num = run(cfg)
    x_num = np.array(sim_num.x_full)
    sim_num.eigenvalue_analysis()
    eig_num = np.sort_complex(np.array(sim_num.eigenvalues))
    f_num, x_sym_num, y_sym_num, s_sym_num = (
        sim_num.f, sim_num.x, sim_num.y, sim_num.s,
    )
    xinit, yinit = np.array(sim_num.xinit), np.array(sim_num.yinit)

    sim_par = run(cfg.updated(parametric=True))
    x_par = np.array(sim_par.x_full)
    sim_par.eigenvalue_analysis()
    eig_par = np.sort_complex(np.array(sim_par.eigenvalues))

    model = sim_par.parametric_model
    assert model is not None

    # Same trajectory (the two builds differ only in floating point
    # association; record the achieved error in the message).
    err_x = np.abs(x_par - x_num).max()
    assert err_x < 1e-5, f"trajectory deviation {err_x:.3e}"
    err_e = np.abs(eig_par - eig_num).max()
    assert err_e < 1e-8, f"eigenvalue deviation {err_e:.3e}"

    # Numeric attributes restored on every device.
    for dev in sim_par.device_list:
        for name in dev._params:
            val = getattr(dev, name, None)
            assert not isinstance(val, ca.SX), f"{dev._name}.{name} left symbolic"

    # Published expressions are numeric in p again (evaluable without p).
    machine = find_device(sim_par, "H")
    ca.Function("Pe", [model.x, model.y], [machine.Pe])

    # The parameter Jacobian exists and is non-trivial.
    assert model.p.numel() > 0
    assert ca.jacobian(model.f, model.p).nnz() > 0

    # Substituting the values reproduces the numeric right-hand side at
    # machine precision, at the operating point and at a perturbed point.
    W_num = ca.vertcat(sim_num.omega_ref, sim_num.omega_ref_buses,
                       sim_num.omega_ref_lines)
    W_par = ca.vertcat(sim_par.omega_ref, sim_par.omega_ref_buses,
                       sim_par.omega_ref_lines)
    ones_num = ca.SX.ones(W_num.numel(), 1)
    f_ref = ca.Function(
        "f", [x_sym_num, y_sym_num, s_sym_num],
        [ca.substitute(f_num, W_num, ones_num)],
    )
    f_sub = ca.Function(
        "f", [model.x, model.y, model.s, model.p],
        [ca.substitute(model.f, W_par, ca.SX.ones(W_par.numel(), 1))],
    )
    rng = np.random.default_rng(7)
    s_ones = np.ones(sim_par.nx)
    for scale in (0.0, 0.02):
        x_pt = xinit * (1 + scale * rng.standard_normal(xinit.size))
        y_pt = yinit * (1 + scale * rng.standard_normal(yinit.size))
        a = np.array(f_ref(x_pt, y_pt, s_ones)).flatten()
        b = np.array(f_sub(x_pt, y_pt, s_ones, model.p_val)).flatten()
        err_f = np.abs(a - b).max()
        assert err_f < 1e-10, f"rhs deviation {err_f:.3e} at scale {scale}"


def test_gradient_matches_finite_differences():
    # Fixed (slightly perturbed) initial condition, no disturbance: the
    # relaxation back to the operating point depends strongly on the machine
    # inertia H and the converter droop Kp.
    cfg = base_config(T_end=0.5, skip_disturance=True, parametric=True)
    sim = run(cfg)
    model = sim.parametric_model

    machine = find_device(sim, "H")
    converter = find_device(sim, "Kp")
    i_H = model.slice_of(machine, "H").start
    i_Kp = model.slice_of(converter, "Kp").start

    # Kick the machine speed off the equilibrium.
    x0 = np.array(sim.xinit)
    x0[machine.omega] += 2e-3

    tgrid = np.arange(0.01, 0.5 + 1e-9, 0.01)
    integrator = ca.integrator(
        "I", "idas", model.dae_dict(), 0.0, tgrid,
        {"reltol": 1e-10, "abstol": 1e-12},
    )

    p_mx = ca.MX.sym("p", model.p.numel())
    res = integrator(
        x0=x0, z0=sim.yinit, p=ca.vertcat(ca.DM.ones(sim.nx), p_mx)
    )
    # Functional: integrated squared speed deviation of the machine.
    J = ca.sumsqr(res["xf"][int(machine.omega[0]), :] - 1.0)

    J_fun = ca.Function("J", [p_mx], [J])
    grad_fun = ca.Function("dJ", [p_mx], [ca.gradient(J, p_mx)])
    grad = np.array(grad_fun(model.p_val)).flatten()

    for idx, label in ((i_H, "H"), (i_Kp, "Kp")):
        h = 1e-5 * max(1.0, abs(model.p_val[idx]))
        p_plus, p_minus = model.p_val.copy(), model.p_val.copy()
        p_plus[idx] += h
        p_minus[idx] -= h
        fd = (float(J_fun(p_plus)) - float(J_fun(p_minus))) / (2 * h)
        assert abs(grad[idx]) > 1e-12, f"gradient wrt {label} is trivially zero"
        rel = abs(grad[idx] - fd) / max(abs(fd), 1e-12)
        assert rel < 1e-3, (
            f"gradient wrt {label}: adjoint {grad[idx]:.6e} vs FD {fd:.6e} "
            f"(rel err {rel:.2e})"
        )
