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

"""Controller-side parity test for the device-private algebraic-equation mechanism.

The generalized AVR strategy protocol lets an exciter expose its field voltage
``Efd`` as *either* a differential state (pure-lag exciter) *or* a device-private
algebraic variable (direct-feedthrough / lead-lag exciter). This test exercises
the latter via ``AVRKundur`` -- the Kundur transducer+lead-lag AVR with
``Efd`` as the lead's algebraic output -- and validates it two ways:

1. The recovered ``Efd`` (in ``dae.y``) exactly satisfies its defining equation
   along the trajectory (internal consistency of the private-algebraic solve).
2. The lead-lag (algebraic ``Efd``) reproduces ``AVRKundur_Filter`` -- the same
   exciter with a parasitic output filter that fakes ``Efd`` into a state -- in
   the ``Tfd -> 0`` singular-perturbation limit. The ``avr_filter`` fixture uses
   a small ``Tfd``, so the two systems must agree to ``O(Tfd)``.
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


def _machine():
    """The synchronous-machine device from the most recent run.

    ``run`` resets ``system`` (clear_module) on entry, so this must be called
    immediately after a run and before the next one.
    """
    from hermess import system as _sys

    return next(
        d
        for d in _sys.device_list_sim
        if getattr(d, "_name", "").startswith("Synchronous")
    )


def test_avr_leadlag_constraint_holds():
    """The lead-lag's algebraic field voltage must satisfy its defining equation
    along the whole trajectory: the recovered Efd (in y_full) equals
    Vl*(1 - TA/TB) + (TA/TB)*KA*(Vf_ref - Vtr) evaluated on the states."""
    sim = run(config.updated(testsystemfile="avr_leadlag", **_COMMON))
    m = _machine()

    assert sim.n_priv == 1  # Efd only
    x = np.array(sim.x_full)
    y = np.array(sim.y_full)

    efd = y[m.Efd[0]]  # algebraic, recovered from the DAE solve
    Vl = x[m.Vl[0]]
    Vtr = x[m.Vtr[0]]
    TA, TB, KA, Vfr = m.TA[0], m.TB[0], m.KA[0], m.Vf_ref[0]
    expr = Vl * (1 - TA / TB) + (TA / TB) * KA * (Vfr - Vtr)

    assert np.abs(efd - expr).max() < 1e-6, (
        f"Efd violates its lead-lag defining equation by "
        f"{np.abs(efd - expr).max():.3e} (expected < 1e-6)."
    )


def test_avr_leadlag_matches_filtered_limit():
    """AVRKundur (Efd algebraic) must reproduce AVRKundur_Filter (Efd a
    state behind a fast parasitic filter) in the Tfd -> 0 limit. The avr_filter
    fixture uses Tfd = 1e-3, so the machine response must agree to O(Tfd)."""
    sim_f = run(config.updated(testsystemfile="avr_filter", **_COMMON))
    mf = _machine()
    xf = np.array(sim_f.x_full)
    efd_f = xf[mf.Efd[0]]  # Efd is a STATE in the filtered model
    delta_f = xf[mf.delta[0]]
    omega_f = xf[mf.omega[0]]

    sim_l = run(config.updated(testsystemfile="avr_leadlag", **_COMMON))
    ml = _machine()
    xl = np.array(sim_l.x_full)
    yl = np.array(sim_l.y_full)
    efd_l = yl[ml.Efd[0]]  # Efd is ALGEBRAIC in the lead-lag model
    delta_l = xl[ml.delta[0]]
    omega_l = xl[ml.omega[0]]

    # Structural difference: removing the filter drops one differential state
    # (Efd) and adds one private algebraic.
    assert sim_f.n_priv == 0 and sim_l.n_priv == 1
    assert sim_l.nx == sim_f.nx - 1
    assert sim_l.ny == sim_f.ny + 1

    n = min(xf.shape[1], xl.shape[1])
    assert np.isfinite(efd_l).all()
    # Machine dynamics (slow states) are essentially identical...
    assert np.abs(delta_f[:n] - delta_l[:n]).max() < 1e-3
    assert np.abs(omega_f[:n] - omega_l[:n]).max() < 1e-4
    # ...and the field voltage agrees to the filter-time-constant order (Tfd=1e-3).
    assert np.abs(efd_f[:n] - efd_l[:n]).max() < 5e-3, (
        f"Algebraic Efd differs from the Tfd->0 filtered Efd by "
        f"{np.abs(efd_f[:n] - efd_l[:n]).max():.3e} (expected O(Tfd), < 5e-3)."
    )
