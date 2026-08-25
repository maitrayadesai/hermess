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

"""ANDES reference for the GENROU case: the twin of ``system/sim_param.txt``.

Two identical round-rotor GENROU machines with constant field voltage and
constant mechanical power (no exciter or governor attached in ANDES, which
then holds vf and tm at their initialized values; AVRCONST / GOVCONST on the
hermess side). Saturation is disabled (S10 = 0), as the hermess GENROU carries
none. Regenerate with::

    uv run --group validation python hermess/tests/references/andes/genrou/generate.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR.parent))

# One dict per machine; every entry mirrors the hermess sim_param.txt line.
MACHINE = dict(
    Sn=100, fn=50, M=13.0, D=2.0, ra=0.0025, xl=0.2,
    xd=1.8, xq=1.7, xd1=0.3, xq1=0.55, xd2=0.25, xq2=0.25,
    Td10=8.0, Tq10=0.4, Td20=0.03, Tq20=0.05, S10=0.0, S12=1.0,
)
MACHINES = [
    dict(idx="SG1", bus=1, gen="GS1", **MACHINE),
    dict(idx="SG2", bus=3, gen="GP3", **MACHINE),
]


def main() -> None:
    from _common import run_and_write

    run_and_write(
        CASE_DIR,
        description=(
            "GENROU machine model, three-bus system, loss of line 3-1 at "
            "t = 1 s; constant field voltage and mechanical power."
        ),
        machines=MACHINES,
        notes=[
            "hermess state map: e_qprim=e1q, e_dprim=e1d, psi_kd=e2d, "
            "psi_kq=e2q (identical K-coefficient form on both sides).",
            "M = 2H; hermess rotor friction f = 0 matches the absent term in "
            "ANDES.",
        ],
    )


if __name__ == "__main__":
    main()
