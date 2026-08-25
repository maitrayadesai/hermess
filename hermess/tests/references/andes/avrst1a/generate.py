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

"""ANDES reference for the AVRST1A case: the twin of ``system/sim_param.txt``.

The GENROU machines of the genrou case with one ANDES EXST1 exciter per
machine. EXST1 reduces exactly to the hermess AVRST1A by removing its rate
feedback (KF = 0), its field-current limit coupling (KC = 0) and opening all
limits; the hermess second lead-lag is made unity (TC1 = TB1). Each side is
then left with one decoupled state (our Vll2, their washout WF_x); both are
placed at -820 rad/s (TB1 = TF = 1/820 s), so their eigenvalues pair with
each other and nothing needs dropping. State map: Vtr = LG_y (transducer),
Vll1 = LL_x (lead-lag lag state), Efd = LR_y (regulator lag output = vf).
Regenerate with::

    uv run --group validation python hermess/tests/references/andes/avrst1a/generate.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR.parent))

T_DECOUPLED = 1.0 / 820.0

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
EXCITER = dict(
    TR=0.01, TB=10.0, TC=1.0, KA=200.0, TA=0.05,
    KF=0.0, TF=T_DECOUPLED, KC=0.0,
    VIMAX=99.0, VIMIN=-99.0, VRMAX=99.0, VRMIN=-99.0,
)
EXCITERS = [
    dict(idx="EXC1", syn="SG1", **EXCITER),
    dict(idx="EXC2", syn="SG2", **EXCITER),
]


def main() -> None:
    from _common import run_and_write

    run_and_write(
        CASE_DIR,
        description=(
            "AVRST1A static exciter (transducer + transient-gain-reduction "
            "lead-lag + regulator lag) on GENROU machines vs ANDES EXST1 with "
            "KF = 0, three-bus system, loss of line 3-1 at t = 1 s; constant "
            "mechanical power."
        ),
        machines=MACHINES,
        exciter_model="EXST1",
        exciters=EXCITERS,
        exciter_init_vars=("LG_y", "LL_x", "LR_y", "WF_x", "vref"),
        notes=[
            "hermess state map: Vtr = LG_y, Vll1 = LL_x, Efd = LR_y (= vf); "
            "Vf_ref = vref.",
            "The decoupled pair (hermess Vll2 with TC1 = TB1, ANDES WF_x "
            f"with KF = 0) both sit at {-1.0 / T_DECOUPLED} rad/s and pair "
            "with each other in the eigenvalue test; no drops needed.",
        ],
    )


if __name__ == "__main__":
    main()
