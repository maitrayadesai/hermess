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

"""Pluggable rotor-shaft strategy test (multi-mass torsional shaft).

The rotor mechanics are a pluggable strategy. The default :class:`SingleMass`
reproduces the classic single rigid-mass swing equation (its byte-equivalence is
gated by the positional baselines in test_recur_sim). A multi-mass (torsional)
shaft keeps the generator mass on the canonical ``delta``/``omega`` names, leaving
the electromagnetic model, network injection, governor, PSS and initialisation
untouched, and adds further rotor masses ``delta_<name>``/``omega_<name>``.

This validates :class:`Shaft4Mass` (HP--IP--LP--GEN) and :class:`Shaft5Mass`
(HP--IP--LP--GEN--EXC):

1. Structural: each extra mass adds exactly two differential states and no
   private algebraics; the generator mass stays 'delta'/'omega' as states 0/1.
2. Steady state: every mass is synchronous (omega_i -> 1 p.u.) and the static
   shaft twist satisfies the torque balance -- each shaft section carries exactly
   the cumulative mechanical power of the turbine masses upstream of it.
3. The disturbance excites the torsional dynamics (the inter-mass twist
   oscillates), i.e. the elastic shaft is genuinely modelled.
"""

import numpy as np

from hermess.config import config
from hermess.run import run
from hermess.devices.shaft import Shaft4Mass, Shaft5Mass
from hermess.devices.synchronous import SynchronousSubtransientSP
from hermess.tests.test_avr_algebraic import _COMMON, _machine

_T_DIST = 3.0  # disturbance time in the shaft_4mass fixture (sim_dist.txt)


def test_shaft_structural():
    """A multi-mass shaft adds exactly two differential states per extra mass and
    no private algebraics; the generator mass stays 'delta'/'omega' as states 0,1."""
    single = SynchronousSubtransientSP()
    assert single.states[:2] == ["delta", "omega"]

    m4 = SynchronousSubtransientSP(shaft=Shaft4Mass())
    # gen stays first; HP/IP/LP add delta_*/omega_* (3 masses * 2 states = +6).
    assert m4.states[:2] == ["delta", "omega"]
    assert m4.ns == single.ns + 6
    for s in ("delta_hp", "omega_hp", "delta_ip", "omega_ip", "delta_lp", "omega_lp"):
        assert s in m4.states
    # The shaft declares per-mass / per-section / per-turbine parameters.
    for p in ("H_hp", "H_ip", "H_lp", "K_hp_ip", "K_ip_lp", "K_lp_gen",
              "F_hp", "F_ip", "F_lp"):
        assert p in m4._params

    m5 = SynchronousSubtransientSP(shaft=Shaft5Mass())
    assert m5.ns == single.ns + 8  # +1 EXC mass over the 4-mass shaft
    assert "delta_exc" in m5.states and "K_gen_exc" in m5._params


def test_shaft_steady_state_torque_balance():
    """At the pre-disturbance steady state every mass is synchronous and the
    static shaft twist carries the cumulative upstream mechanical power: a shaft
    section between masses a (upstream) and b transmits sum(F_upstream)*pm, so
    K_ab*(delta_a - delta_b) == sum(F_upstream)*pm."""
    sim = run(config.updated(testsystemfile="shaft_4mass", **_COMMON))
    m = _machine()

    assert sim.n_priv == 0  # the shaft introduces only differential states
    x = np.array(sim.x_full)
    assert np.isfinite(x).all(), "non-finite trajectory (init or integration diverged)"

    dt = (_COMMON["T_end"] - _COMMON["T_start"]) / (x.shape[1] - 1)
    i_pre = int(round((_T_DIST - 0.5) / dt))  # a settled column before the disturbance

    # Every mass synchronous at steady state (omega is ABSOLUTE p.u. speed).
    for s in ("omega", "omega_hp", "omega_ip", "omega_lp"):
        assert abs(x[getattr(m, s)[0]][i_pre] - 1.0) < 1e-6, f"{s} not synchronous"

    pm = x[m.pm[0]][i_pre]
    d_gen = x[m.delta[0]][i_pre]
    d_hp = x[m.delta_hp[0]][i_pre]
    d_ip = x[m.delta_ip[0]][i_pre]
    d_lp = x[m.delta_lp[0]][i_pre]
    K_hp_ip, K_ip_lp, K_lp_gen = m.K_hp_ip[0], m.K_ip_lp[0], m.K_lp_gen[0]
    F_hp, F_ip, F_lp = m.F_hp[0], m.F_ip[0], m.F_lp[0]

    # HP--IP carries F_hp*pm; IP--LP carries (F_hp+F_ip)*pm; LP--GEN carries pm.
    assert abs(K_hp_ip * (d_hp - d_ip) - F_hp * pm) < 1e-4
    assert abs(K_ip_lp * (d_ip - d_lp) - (F_hp + F_ip) * pm) < 1e-4
    assert abs(K_lp_gen * (d_lp - d_gen) - (F_hp + F_ip + F_lp) * pm) < 1e-4

    # Sanity: the turbine masses lead the generator (they push torque downstream).
    assert d_hp > d_ip > d_lp > d_gen


def test_shaft_torsional_excitation():
    """The disturbance excites the elastic shaft: the inter-mass twist is flat
    before the disturbance (rigid-body steady state) and oscillates afterwards."""
    sim = run(config.updated(testsystemfile="shaft_4mass", **_COMMON))
    m = _machine()
    x = np.array(sim.x_full)

    twist = x[m.delta_hp[0]] - x[m.delta[0]]  # HP-to-GEN shaft twist
    dt = (_COMMON["T_end"] - _COMMON["T_start"]) / (x.shape[1] - 1)
    i_dist = int(round(_T_DIST / dt))

    pre = twist[: i_dist - 1]
    post = twist[i_dist:]
    assert np.std(pre) < 1e-8, "shaft twist not steady before the disturbance"
    assert (post.max() - post.min()) > 1e-6, (
        "no torsional oscillation excited -- the shaft is behaving rigidly"
    )
