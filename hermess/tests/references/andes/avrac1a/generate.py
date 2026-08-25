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

"""ANDES reference for the AVRAC1A case: the twin of ``system/sim_param.txt``.

The hermess AVRAC1A is the AC1A in its small-signal form: no saturation,
armature reaction or rectifier regulation (KC = KD = 0) and a unity lead-lag,
which leaves the same regulator-lag / rate-feedback / exciter-integrator
chain as the DC1A. The twin is therefore the same ANDES IEEET1 reduction as
in the ieeedc1a case (TR = 0, saturation inert, limits open), at the AC1A
parameter set of the South East Australian benchmark family. State map:
Vr = LA_y, Efd = INT_y, Vfb = KF/TF * WF_x. Regenerate with::

    uv run --group validation python hermess/tests/references/andes/avrac1a/generate.py
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
    TR=0.0, KA=400.0, TA=0.02, KE=1.0, TE=1.0, KF=0.03, TF=1.0,
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
            "AVRAC1A exciter (AC1A small-signal form) on GENROU machines vs "
            "ANDES IEEET1 with TR = 0, three-bus system, loss of line 3-1 at "
            "t = 1 s; constant mechanical power."
        ),
        machines=MACHINES,
        exciter_model="IEEET1",
        exciters=EXCITERS,
        exciter_init_vars=("LA_y", "INT_y", "WF_x", "vref"),
        notes=[
            "hermess state map: Vr = LA_y, Efd = INT_y (= vf), "
            "Vfb = KF/TF * WF_x; Vf_ref = vref.",
            "Same IEEET1 reduction as the ieeedc1a case; without saturation "
            "and rectifier terms the AC1A and DC1A chains coincide, so the "
            "two cases differ only in the parameter regime (high-gain fast "
            "regulator with a slow rotating exciter here).",
        ],
    )


if __name__ == "__main__":
    main()
