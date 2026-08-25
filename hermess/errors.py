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

"""Exceptions raised by hermess.

Kept in their own module (outside :mod:`hermess.system`, which is reloaded on
every run) so that ``except`` clauses in long-lived callers keep matching
across runs.
"""


class SimulationCancelled(Exception):
    """Raised inside :meth:`hermess.system.DaeSim.simulate` when the progress
    callback requests cancellation (by returning ``False``)."""
