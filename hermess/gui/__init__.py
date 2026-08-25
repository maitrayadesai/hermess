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

"""Desktop GUI for hermess (optional, ``pip install hermess[gui]``).

Launch with ``hermess-gui`` or ``python -m hermess.gui``. The GUI is a Qt
shell over the same public API the CLI and scripts use; simulations run in a
worker process (see :mod:`hermess.gui.worker`) and only the plain-data
:class:`~hermess.results.SimulationResults` crosses back.

This package must stay importable without Qt: everything Qt-dependent is
imported inside :func:`hermess.gui.app.main`.
"""
