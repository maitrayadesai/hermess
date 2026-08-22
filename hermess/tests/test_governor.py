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

"""Pluggable-governor test (governor-side counterpart of test_avr_algebraic).

The governor is a pluggable strategy, symmetric to the AVR: its mechanical-
power coupling 'pm' may be a differential state (TGOV1, turbine lag dynamics) or
a device-private algebraic variable (Droop, instantaneous primary frequency
response). This validates:

1. The Droop governor's algebraic 'pm' satisfies its defining equation
   pm = Pref - omega/Rd along the trajectory (internal consistency).
2. Droop (algebraic 'pm') reproduces TGOV1 with small turbine time constants in
   the Tch,Tsv -> 0 singular-perturbation limit (Droop is that quasi-steady-state
   limit), proving the state-vs-algebraic 'pm' coupling is interchangeable.

(Byte-equivalence of the TGOV1 extraction itself is covered by the positional
baselines in test_recur_sim.)
"""

import numpy as np

from hermess.config import config
from hermess.run import run
from hermess.tests.test_avr_algebraic import _COMMON, _machine


def test_droop_constraint_holds():
    """The Droop governor's algebraic mechanical power must satisfy its defining
    equation along the whole trajectory: the recovered pm (in y_full) equals
    Pref - (omega - omega_net)/Rd evaluated on the state. Note `omega` is the
    ABSOLUTE per-unit speed, so the droop acts on the deviation (omega_net=1)."""
    sim = run(config.updated(testsystemfile="gov_droop", **_COMMON))
    m = _machine()

    assert sim.n_priv == 1  # pm only
    x = np.array(sim.x_full)
    y = np.array(sim.y_full)

    pm = y[m.pm[0]]  # algebraic, recovered from the DAE solve
    omega = x[m.omega[0]]
    Pref, Rd = m.Pref[0], m.Rd[0]
    expr = Pref - (omega - 1.0) / Rd  # omega_net = 1 p.u.

    assert np.abs(pm - expr).max() < 1e-6, (
        f"pm violates its droop defining equation by "
        f"{np.abs(pm - expr).max():.3e} (expected < 1e-6)."
    )


def test_droop_matches_tgov1_fast_limit():
    """Droop (pm algebraic) must reproduce TGOV1 with small turbine time constants
    (pm a state behind the valve+chest lags) in the Tch,Tsv -> 0 limit. The
    gov_tgov1_fast fixture uses Tch = Tsv = 1e-3, so the machine response must
    agree to O(Tch,Tsv)."""
    sim_g = run(config.updated(testsystemfile="gov_tgov1_fast", **_COMMON))
    mg = _machine()
    xg = np.array(sim_g.x_full)
    pm_g = xg[mg.pm[0]]  # pm is a STATE in TGOV1
    delta_g = xg[mg.delta[0]]
    omega_g = xg[mg.omega[0]]

    sim_d = run(config.updated(testsystemfile="gov_droop", **_COMMON))
    md = _machine()
    xd = np.array(sim_d.x_full)
    yd = np.array(sim_d.y_full)
    pm_d = yd[md.pm[0]]  # pm is ALGEBRAIC in Droop
    delta_d = xd[md.delta[0]]
    omega_d = xd[md.omega[0]]

    # Structural difference: Droop has no turbine states (psv, pm) but adds pm as
    # a private algebraic -> two fewer states, one more private.
    assert sim_g.n_priv == 0 and sim_d.n_priv == 1
    assert sim_d.nx == sim_g.nx - 2
    assert sim_d.ny == sim_g.ny + 1

    n = min(xg.shape[1], xd.shape[1])
    assert np.isfinite(pm_d).all()
    # Machine dynamics (slow states) are essentially identical...
    assert np.abs(delta_g[:n] - delta_d[:n]).max() < 1e-3
    assert np.abs(omega_g[:n] - omega_d[:n]).max() < 1e-4
    # ...and the mechanical power agrees to the turbine-time-constant order.
    assert np.abs(pm_g[:n] - pm_d[:n]).max() < 5e-3, (
        f"Algebraic pm differs from the Tch,Tsv->0 TGOV1 pm by "
        f"{np.abs(pm_g[:n] - pm_d[:n]).max():.3e} (expected O(Tch,Tsv), < 5e-3)."
    )
