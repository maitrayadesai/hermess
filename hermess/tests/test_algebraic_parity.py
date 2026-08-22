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

"""Parity test for the device-private algebraic-equation mechanism.

Runs the stock SynchronousSubtransientSP machine (stator currents inlined as
explicit expressions) and SynchronousSubtransientSP_DAE (the same currents
declared as device-private algebraic variables/equations and handed to the DAE
solver) on the same system, and asserts the differential-state trajectories
agree to integrator tolerance.

This validates the full private-algebraic path: declaration, index allocation,
finit with private unknowns, DAE assembly/solve, and the grid/output slicing.
"""

from pathlib import Path

import numpy as np

from hermess.config import config
from hermess.run import run

FIXTURE_ROOT = Path(__file__).parent / "fixtures"

_COMMON = dict(
    system_root=FIXTURE_ROOT,
    fn=50,
    Sb=100,
    ts=0.005,
    T_start=0.0,
    T_end=6.0,
    int_scheme_sim="idas",
    plot=False,
    plot_voltage=False,
    plot_diff=False,
    log_level="ERROR",
    incl_lim=False,
    line_dyn=False,
    print_power_flow=False,
)


def test_sp_dae_matches_eliminated_sp():
    """SP_DAE (explicit algebraic stator currents) must reproduce the stock SP
    (eliminated currents) on identical systems, to integrator tolerance."""
    sim_ground = run(config.updated(testsystemfile="sp_ground", **_COMMON))
    sim_dae = run(config.updated(testsystemfile="sp_dae", **_COMMON))

    # The DAE model adds two ALGEBRAIC variables (in y), not states, so nx and
    # the differential-state ordering are identical; x_full is positionally
    # comparable.
    assert sim_ground.nx == sim_dae.nx
    assert sim_ground.n_priv == 0
    assert sim_dae.n_priv == 2  # id_alg, iq_alg
    assert sim_dae.ny == sim_ground.ny + 2

    xg = np.array(sim_ground.x_full)
    xd = np.array(sim_dae.x_full)
    assert xg.shape == xd.shape
    max_diff = np.abs(xg - xd).max()
    assert max_diff < 1e-4, (
        f"SP_DAE differential states diverged from eliminated SP by {max_diff:.3e} "
        f"(expected < 1e-4; trajectories should match to integrator tolerance)."
    )


def test_sp_dae_private_constraints_hold():
    """The private stator-current constraints g = -i + <expr> must be satisfied
    along the SP_DAE trajectory: the recovered i_d/i_q (in y_full) equal the
    explicit expression evaluated on the states."""
    sim_dae = run(config.updated(testsystemfile="sp_dae", **_COMMON))

    # Locate the machine device and its private/state indices.
    from hermess import system as _sys

    machine = next(
        d
        for d in _sys.device_list_sim
        if getattr(d, "_name", "").endswith("Sauer_Pai_DAE")
    )
    y = np.array(sim_dae.y_full)
    x = np.array(sim_dae.x_full)

    gd1 = (machine.x_dsec - machine.x_l) / (machine.x_dprim - machine.x_l)
    gq1 = (machine.x_qsec - machine.x_l) / (machine.x_qprim - machine.x_l)

    # n == 1 machine; index arrays hold one global index each.
    id_alg = y[machine.id_alg[0]]
    iq_alg = y[machine.iq_alg[0]]
    expr_id = (1 / machine.x_dsec[0]) * (
        -x[machine.psid[0]]
        + gd1[0] * x[machine.e_qprim[0]]
        + (1 - gd1[0]) * x[machine.psid2[0]]
    )
    expr_iq = (1 / machine.x_qsec[0]) * (
        -x[machine.psiq[0]]
        - gq1[0] * x[machine.e_dprim[0]]
        + (1 - gq1[0]) * x[machine.psiq2[0]]
    )
    assert np.abs(id_alg - expr_id).max() < 1e-6
    assert np.abs(iq_alg - expr_iq).max() < 1e-6


def test_sp6_dae_matches_eliminated_sp6():
    """Subtransient Sauer-Pai 6th-order machine with the 4-equation stator block
    (i_d, i_q, psi_d, psi_q) declared as device-private algebraics. Must reproduce
    the eliminated SynchronousSubtransientSP6 to integrator tolerance."""
    sim_ground = run(config.updated(testsystemfile="sp6_ground", **_COMMON))
    sim_dae = run(config.updated(testsystemfile="sp6_dae", **_COMMON))

    assert sim_ground.nx == sim_dae.nx
    assert sim_ground.n_priv == 0
    assert sim_dae.n_priv == 4  # id, iq, psid, psiq

    xg = np.array(sim_ground.x_full)
    xd = np.array(sim_dae.x_full)
    assert xg.shape == xd.shape
    max_diff = np.abs(xg - xd).max()
    assert max_diff < 1e-4, (
        f"SP6_DAE differential states diverged from eliminated SP6 by {max_diff:.3e}"
    )


def test_sp_dae_line_dyn_mixed_dae():
    """Under line_dyn=True the network (voltages + line currents) is differential
    and the device-private algebraics are the only algebraic block — a mixed DAE.
    SP_DAE must run in this mode and reproduce the eliminated SP (which is a pure
    ODE there). The match is near machine precision because both integrate the
    same differential network states; only the linear private solve differs."""
    ld_cfg = dict(_COMMON)
    ld_cfg.update(ts=0.001, T_end=2.0, line_dyn=True, skip_disturance=True)

    sim_g = run(config.updated(testsystemfile="sp_ground", **ld_cfg))
    sim_d = run(config.updated(testsystemfile="sp_dae", **ld_cfg))

    assert sim_g.n_priv == 0 and sim_d.n_priv == 2
    xg, xd = np.array(sim_g.x_full), np.array(sim_d.x_full)
    assert np.isfinite(xd).all()
    m = min(xg.shape[1], xd.shape[1])
    assert np.abs(xg[:, :m] - xd[:, :m]).max() < 1e-8


def _sorted_eig(sim):
    e = np.array(sim.eigenvalues)
    return e[np.argsort(e.real + 1j * e.imag)]


def test_eigenvalue_analysis_line_dyn_mixed():
    """Small-signal eigenvalue analysis for the mixed DAE (line_dyn=True with
    device-private algebraics). The privates are Schur-complemented out, leaving
    an nd = nx + nv + nl differential system. Because the eliminated ground model
    reduces to the same nd-dimensional system, the two spectra must coincide.
    Covers both SP_DAE (2 privates) and SP6_DAE (4 privates)."""
    ld_cfg = dict(_COMMON)
    # Re-enable the small-signal analysis (off by default via the conftest
    # fixture); it populates sim.eigenvalues, which this test reads.
    ld_cfg.update(
        ts=0.001,
        T_end=1.0,
        line_dyn=True,
        skip_disturance=True,
        small_signal_analysis=True,
    )

    for ground, dae, n_priv in [("sp_ground", "sp_dae", 2),
                                ("sp6_ground", "sp6_dae", 4)]:
        sim_g = run(config.updated(testsystemfile=ground, **ld_cfg))
        sim_d = run(config.updated(testsystemfile=dae, **ld_cfg))

        assert sim_d.n_priv == n_priv and sim_g.n_priv == 0
        nd = sim_d.nx + sim_d.nv + sim_d.nl
        eig_d = _sorted_eig(sim_d)
        eig_g = _sorted_eig(sim_g)

        # The DAE reduction yields exactly nd finite eigenvalues...
        assert eig_d.size == nd, f"{dae}: expected {nd} eigenvalues, got {eig_d.size}"
        assert np.isfinite(eig_d).all(), f"{dae}: non-finite eigenvalues"
        # ...and they match the eliminated ground model's spectrum.
        assert eig_g.size == eig_d.size
        assert np.abs(eig_g - eig_d).max() < 1e-6, (
            f"{dae}: Schur-reduced spectrum differs from eliminated {ground} by "
            f"{np.abs(eig_g - eig_d).max():.3e}"
        )
