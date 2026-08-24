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

"""Shared pytest fixtures.

Two safeguards keep the suite headless:

1. The default ``config`` enables ``small_signal_analysis``, whose modal report
   ends in a blocking ``plt.show``. The autouse fixture forces the flag off; a
   test that needs the analysis opts back in via ``config.updated(...)``.

2. ``hermess.run.fplot`` selects an interactive backend when a run asks for the
   built-in pop-up figures, so the fixture re-forces the non-interactive Agg
   backend before every test. (Importing the package leaves the backend alone;
   see ``test_public_api.test_import_does_not_hijack_the_matplotlib_backend``.)
"""

import os

import matplotlib
import pytest

os.environ.setdefault("MPLBACKEND", "Agg")
matplotlib.use("Agg", force=True)

from hermess.config import config


@pytest.fixture(autouse=True)
def _headless_no_blocking_plots():
    matplotlib.use("Agg", force=True)
    config.small_signal_analysis = False
    yield
