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

"""ANDES reference for the IEEEDC1A case: the twin of ``system/sim_param.txt``.

The GENROU machines of the genrou case with one ANDES IEEET1 exciter per
machine. IEEET1 reduces exactly to the hermess IEEEDC1A: TR = 0 removes the
transducer (ANDES turns a zero-time-constant lag state into an algebraic
variable and excludes it from the eigenvalue analysis), the saturation is
inert at the defaults (SE1 = 0 makes Se identically zero), and the regulator
limits are wide open. State map: Vr = LA_y, Efd = INT_y, and
Rf = KF/TF * WF_x (ANDES realizes the rate feedback s KF/(1+s TF) as a
washout on vf; hermess folds the KF/TF factor into its Rf state).
Regenerate with::

    uv run --group validation python hermess/tests/references/andes/ieeedc1a/generate.py
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
EXCITER = dict(
    TR=0.0, KA=20.0, TA=0.2, KE=1.0, TE=0.314, KF=0.063, TF=0.35,
    VRMAX=99.0, VRMIN=-99.0, E1=0.0, SE1=0.0, E2=1.0, SE2=1.0,
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
            "IEEEDC1A rotating exciter on GENROU machines vs ANDES IEEET1 "
            "with TR = 0, three-bus system, loss of line 3-1 at t = 1 s; "
            "constant mechanical power."
        ),
        machines=MACHINES,
        exciter_model="IEEET1",
        exciters=EXCITERS,
        exciter_init_vars=("LA_y", "INT_y", "WF_x", "vref"),
        notes=[
            "hermess state map: Vr = LA_y, Efd = INT_y (= vf), "
            "Rf = KF/TF * WF_x; Vf_ref = vref.",
            "TR = 0: the transducer state becomes algebraic (LG_y = v) and "
            "is excluded from the ANDES eigenvalue analysis, so the state "
            "counts match with no drops.",
            "Saturation inert: SE1 = 0 gives Se = 0 identically.",
        ],
    )


if __name__ == "__main__":
    main()
