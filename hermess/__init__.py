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

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("hermess")  # Must match the name in pyproject.toml
except PackageNotFoundError:  # running from source without an install
    __version__ = "1.0.0"


def help() -> None:
    """
    Prints an overview of the hermess package and usage instructions.
    """
    print(
        r"""
    📦 hermess — Power System Dynamic Simulator
    ------------------------------------------------------
    Time-domain dynamic simulation of power systems modeled by nonlinear
    differential-algebraic equations (DAEs).

    🔧 Key Modules:
    - run.py     : Simulation execution
    - system.py  : DAE system model

    🚀 Usage:
    >>> import hermess
    >>> hermess.help()

    🧾 License:
    GNU General Public License v3.0 or later (GPL-3.0-or-later)
    https://www.gnu.org/licenses/gpl-3.0.en.html

    ℹ️ Provenance:
    Simulation-only fork of PowerDynamicEstimator
    (https://doi.org/10.5905/ethz-1007-842); dynamic state estimation removed.
    Contact: mdesai@ethz.ch
    """
    )
