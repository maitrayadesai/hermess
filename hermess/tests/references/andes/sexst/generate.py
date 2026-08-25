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

"""ANDES reference for the SEXST case: the twin of ``system/sim_param.txt``.

The GENROU machines of the genrou case with one ANDES SEXS exciter per
machine, its lead-lag disabled (TATB = 1) so that what remains is the single
lag K/(1 + s TE) of the hermess SEXST. The then-decoupled lead-lag state
LL_x contributes one spurious eigenvalue -1/TB per machine; TB = 1/815 s
places the pair at -815 rad/s, far from every genuine mode, so the test drops
it unambiguously (case.json). Regenerate with::

    uv run --group validation python hermess/tests/references/andes/sexst/generate.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR.parent))

TB_SPURIOUS = 1.0 / 815.0

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
EXCITER = dict(K=50.0, TE=0.5, TATB=1.0, TB=TB_SPURIOUS, EMIN=-99.0, EMAX=99.0)
EXCITERS = [
    dict(idx="EXC1", syn="SG1", **EXCITER),
    dict(idx="EXC2", syn="SG2", **EXCITER),
]


def main() -> None:
    from _common import run_and_write

    run_and_write(
        CASE_DIR,
        description=(
            "SEXST simplified static exciter on GENROU machines (via the "
            "ANDES SEXS reduction TATB = 1), three-bus system, loss of line "
            "3-1 at t = 1 s; constant mechanical power."
        ),
        machines=MACHINES,
        exciter_model="SEXS",
        exciters=EXCITERS,
        exciter_init_vars=("LAW_y", "LL_x", "vref"),
        notes=[
            "hermess state map: Efd = LAW_y (the anti-windup lag output, "
            "= vout = vf); Vf_ref = vref.",
            "LL_x is decoupled (TATB = 1); its two eigenvalues at "
            f"-1/TB = {-1.0 / TB_SPURIOUS} are spurious and dropped by the "
            "test (see case.json).",
        ],
    )


if __name__ == "__main__":
    main()
