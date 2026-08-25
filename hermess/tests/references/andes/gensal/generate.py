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

"""ANDES reference for the GENSAL case: the twin of ``system/sim_param.txt``.

ANDES ships no GENSAL, so the twin is GENROU degenerated to it by setting
xq1 = xq: the q-axis transient voltage e1d then has zero excitation
(XaqI1q = e1d), stays identically zero from its zero initial value, and the
remaining q-axis state obeys Tq20 e2q' = -e2q + (xq - xl) Iq, which maps onto
the GENSAL equation T''_q0 psi''_q' = -psi''_q + (xq - xq2) Iq through
psi''_q = (xq - xq2)/(xq - xl) e2q. The reduction is exact in floating point
(xq - xq1 == 0). The decoupled e1d contributes one spurious eigenvalue
-1/Tq10 per machine; Tq10 is set to 1/810 s so the pair sits far from every
genuine mode and can be dropped unambiguously by the test. Regenerate with::

    uv run --group validation python hermess/tests/references/andes/gensal/generate.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR.parent))

TQ10_SPURIOUS = 1.0 / 810.0

# One dict per machine; every entry mirrors the hermess sim_param.txt line
# (xq1 = xq and Tq10 are the reduction, not physical parameters).
MACHINE = dict(
    Sn=100, fn=50, M=10.0, D=2.0, ra=0.0025, xl=0.15,
    xd=1.1, xq=0.7, xd1=0.35, xq1=0.7, xd2=0.25, xq2=0.25,
    Td10=6.0, Tq10=TQ10_SPURIOUS, Td20=0.04, Tq20=0.06, S10=0.0, S12=1.0,
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
            "GENSAL machine model (via the ANDES GENROU reduction xq1 = xq), "
            "three-bus system, loss of line 3-1 at t = 1 s; constant field "
            "voltage and mechanical power."
        ),
        machines=MACHINES,
        notes=[
            "hermess state map: e_qprim=e1q, psi_kd=e2d, and psi_qsec=psi2q "
            "(the ANDES algebraic, equal to (xq-xq2)/(xq-xl)*e2q).",
            "e1d is identically zero (xq1 = xq); its two decoupled "
            f"eigenvalues at -1/Tq10 = {-1.0 / TQ10_SPURIOUS} are spurious "
            "and dropped by the test (see case.json).",
        ],
    )


if __name__ == "__main__":
    main()
