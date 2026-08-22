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

"""Pluggable-PSS test (the inter-strategy coupling case).

The power system stabilizer is a pluggable strategy whose output 'Vs' is summed
into the AVR voltage error -- a strategy-to-strategy coupling kept host-mediated
(`Synchronous.pss_signal` returns the 'Vs' symbol, or 0 when no PSS is present;
each AVR reads it). 'Vs' is a device-private algebraic (washout + lead-lag has
direct feedthrough on the speed deviation). This validates:

1. The PSSKundur output satisfies its defining equation along the trajectory.
2. The washout blocks DC: 'Vs' is ~0 at steady state and only acts on the
   post-disturbance transient.
3. The PSS measurably changes the machine dynamics versus no PSS (the
   host-mediated PSS -> AVR -> machine coupling works), and adds exactly its
   three states + one private algebraic.

(Byte-equivalence of the no-PSS path is covered by the positional baselines in
test_recur_sim.)
"""

import numpy as np

from hermess.config import config
from hermess.run import run
from hermess.tests.test_avr_algebraic import _COMMON, _machine

_T_DIST = 3.0  # disturbance time in the pss_on / pss_off fixtures (sim_dist.txt)


def test_pss_constraint_holds():
    """The PSS's algebraic output must satisfy its defining equation along the
    whole trajectory: Vs == vl2*(1-T3/T4) + (T3/T4)*y1, with
    y1 = vl1*(1-T1/T2) + (T1/T2)*w and washout output w = K_stab*(omega-1) - vw.
    Note `omega` is the ABSOLUTE per-unit speed, so the PSS input is the deviation
    omega - omega_net (omega_net = 1 p.u.)."""
    sim = run(config.updated(testsystemfile="pss_on", **_COMMON))
    m = _machine()

    assert sim.n_priv == 1  # Vs only
    x = np.array(sim.x_full)
    y = np.array(sim.y_full)

    Vs = y[m.Vs[0]]
    omega = x[m.omega[0]]
    vw, vl1, vl2 = x[m.vw[0]], x[m.vl1[0]], x[m.vl2[0]]
    K, T1, T2, T3, T4 = m.K_stab[0], m.T1[0], m.T2[0], m.T3[0], m.T4[0]

    w = K * (omega - 1.0) - vw  # omega_net = 1 p.u.
    y1 = vl1 * (1 - T1 / T2) + (T1 / T2) * w
    expr = vl2 * (1 - T3 / T4) + (T3 / T4) * y1

    assert np.abs(Vs - expr).max() < 1e-6, (
        f"Vs violates its PSS defining equation by {np.abs(Vs - expr).max():.3e} "
        f"(expected < 1e-6)."
    )


def test_pss_washout_and_coupling():
    """The PSS adds its three states + one private algebraic; its washout blocks
    DC (Vs ~ 0 at the pre-disturbance steady state, active afterwards); and it
    measurably changes the machine dynamics versus the no-PSS reference."""
    sim_off = run(config.updated(testsystemfile="pss_off", **_COMMON))
    m_off = _machine()
    omega_off = np.array(sim_off.x_full)[m_off.omega[0]]

    sim_on = run(config.updated(testsystemfile="pss_on", **_COMMON))
    m_on = _machine()
    x = np.array(sim_on.x_full)
    y = np.array(sim_on.y_full)
    Vs = y[m_on.Vs[0]]
    omega_on = x[m_on.omega[0]]

    # Structural: PSS adds 3 differential states (vw, vl1, vl2) and 1 private (Vs).
    assert sim_off.n_priv == 0 and sim_on.n_priv == 1
    assert sim_on.nx == sim_off.nx + 3
    assert sim_on.ny == sim_off.ny + 1

    # Locate the disturbance column.
    n = Vs.shape[0]
    dt = (_COMMON["T_end"] - _COMMON["T_start"]) / (n - 1)
    i_dist = int(round(_T_DIST / dt))

    # Washout / DC block: Vs is ~0 in the (settled) pre-disturbance window...
    pre = Vs[: i_dist]
    assert np.abs(pre).max() < 1e-9, (
        f"Vs is not ~0 at steady state (washout should block DC); "
        f"max|Vs_pre| = {np.abs(pre).max():.3e}"
    )
    # ...and genuinely active after the disturbance.
    post = Vs[i_dist:]
    assert np.abs(post).max() > 1e-4, "PSS produced no signal after the disturbance"

    # Coupling works: the PSS measurably changes the rotor-speed response.
    mlen = min(omega_off.shape[0], omega_on.shape[0])
    assert np.abs(omega_on[:mlen] - omega_off[:mlen]).max() > 1e-6, (
        "PSS had no effect on the machine dynamics -- the PSS->AVR coupling is "
        "not taking effect"
    )


def test_pss_per_machine_vectorization():
    """With multiple machines in one vectorized device group, each PSS must use
    its OWN absolute speed minus the common nominal (omega_i - omega_net) and its
    OWN parameters -- not machine 0's. Two SGs carry PSSKundur with different
    K_stab/Tw/T*; each machine's Vs must satisfy its own defining equation."""
    sim = run(config.updated(testsystemfile="pss_two_machine", **_COMMON))
    m = _machine()

    assert m.n == 2, "expected a 2-machine vectorized device group"
    assert sim.n_priv == 2  # one Vs per machine
    # Distinct per-machine parameters (rules out accidental aliasing of params).
    assert m.K_stab[0] != m.K_stab[1]

    x = np.array(sim.x_full)
    y = np.array(sim.y_full)

    # The two machines must actually have distinct speed trajectories, otherwise
    # the "own omega" check below would be vacuous.
    assert np.abs(x[m.omega[0]] - x[m.omega[1]]).max() > 1e-6

    for i in range(m.n):
        omega = x[m.omega[i]]
        vw, vl1, vl2 = x[m.vw[i]], x[m.vl1[i]], x[m.vl2[i]]
        Vs = y[m.Vs[i]]
        K, Tw, T1, T2, T3, T4 = (
            m.K_stab[i], m.Tw[i], m.T1[i], m.T2[i], m.T3[i], m.T4[i]
        )
        w = K * (omega - 1.0) - vw  # omega_net = 1 p.u., each machine's own omega
        y1 = vl1 * (1 - T1 / T2) + (T1 / T2) * w
        expr = vl2 * (1 - T3 / T4) + (T3 / T4) * y1
        assert np.abs(Vs - expr).max() < 1e-6, (
            f"machine {i}: Vs does not satisfy its own PSS equation "
            f"(uses its own omega/params); max err {np.abs(Vs - expr).max():.3e}"
        )
