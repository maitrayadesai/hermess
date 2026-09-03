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

"""eigenvalue_analysis() after a run describes the initial operating point.

Every disturbance rebuilds the symbolic equations in place, while the initial
operating point (xinit, yinit, ...) stays. A post-run analysis used to pair
the post-disturbance equations with the pre-disturbance point, which is not
an equilibrium of those equations: the modes moved and a spurious real
eigenvalue near zero appeared. The analysis must give the modes of the
system the run started from, identical to the pre-run analysis.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

import hermess
from hermess import analysis as an


def _run(**overrides):
    settings = dict(
        T_end=1.5,
        ts=1e-3,
        quiet=True,
        incl_lim=False,
        int_scheme_sim_options={"reltol": 1e-8, "abstol": 1e-10},
    )
    settings.update(overrides)
    dae = hermess.simulate("3bus_loadstep", **settings)
    plt.close("all")
    return dae


def _sorted(eigs):
    return np.sort_complex(np.asarray(eigs))


def _spurious_zero_modes(eigs):
    return [e for e in np.asarray(eigs) if abs(e.real) < 1e-6 and e.imag == 0]


@pytest.mark.parametrize("line_dyn", [True, False])
def test_post_run_analysis_equals_initial_analysis(line_dyn):
    # The shipped 3bus_loadstep carries a +10 MW load step at t = 1 s.
    disturbed = _run(line_dyn=line_dyn)
    assert any(kind == "LOAD" for _, kind, _ in disturbed.events)
    disturbed.eigenvalue_analysis()
    eig_after = _sorted(disturbed.eigenvalues)

    # The same system analyzed before any stepping, with no disturbance at all.
    clean = _run(line_dyn=line_dyn, skip_disturance=True, small_signal_analysis=True)
    eig_clean = _sorted(clean.eigenvalues)
    assert eig_after.shape == eig_clean.shape
    assert np.allclose(eig_after, eig_clean, rtol=1e-9, atol=1e-9)

    # And the pre-run analysis of the disturbed run itself.
    reported = _run(line_dyn=line_dyn, small_signal_analysis=True)
    eig_pre = _sorted(reported.eigenvalues)
    assert np.allclose(eig_after, eig_pre, rtol=1e-9, atol=1e-9)

    # Re-running the analysis on that object after the load step must not
    # move it either.
    reported.eigenvalue_analysis()
    assert np.allclose(_sorted(reported.eigenvalues), eig_pre, rtol=1e-9, atol=1e-9)

    # No spurious zero mode from a non-equilibrium linearization.
    assert len(_spurious_zero_modes(eig_after)) == len(_spurious_zero_modes(eig_clean))


def test_analysis_helpers_after_disturbance_use_initial_point():
    disturbed = _run(line_dyn=True)
    clean = _run(line_dyn=True, skip_disturance=True)

    # modal_table / participation_table / state_matrix all go through
    # small_signal(), which runs the analysis lazily on first use.
    table = an.modal_table(disturbed, n=None)
    assert len(table) == len(an.modal_table(clean, n=None))
    modes_after = an.small_signal(disturbed)
    modes_clean = an.small_signal(clean)
    for m_after, m_clean in zip(modes_after, modes_clean):
        assert np.isclose(m_after["freq_hz"], m_clean["freq_hz"], atol=1e-9)
        assert np.isclose(m_after["zeta"], m_clean["zeta"], atol=1e-9)
    assert np.allclose(an.state_matrix(disturbed), an.state_matrix(clean), atol=1e-9)
    assert disturbed.state_names == clean.state_names
