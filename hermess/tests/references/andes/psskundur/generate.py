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

"""ANDES reference for the PSSKundur case: the twin of ``system/sim_param.txt``.

The GENROU machines with the (validated) SEXS/SEXST exciter reduction and
one ANDES ST2CUT stabilizer per machine. ST2CUT reduces exactly to the
hermess PSSKundur, block for block and in the same order (gain -> washout ->
lead-lag -> lead-lag): MODE = 1 selects the speed deviation input, T1 = 0
removes the transducer lag (K1 stays as the gain; the zero-time-constant
state is algebraic in ANDES), K2 = 0 silences the second input channel,
T3 = T4 = Tw is the washout, T5/T6 and T7/T8 are the two lead-lags, the
third lead-lag is unity (T9 = T10), and the output limits are wide open.
State map: vw = WO_x, vl1 = LL1_x, vl2 = LL2_x; output Vs = vsout.

The reference spectrum carries decoupled artifact modes with no hermess
counterpart: per machine one SEXS lead-lag state (-815), the silenced second
channel (-818), the unity third lead-lag (-825), and the two states of the
ANDES voltage-derivative service (present in every ST2CUT, inert with
MODE != 6). The test tolerates these as unmatched extras (case.json).
Regenerate with::

    uv run --group validation python hermess/tests/references/andes/psskundur/generate.py
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
EXCITER = dict(K=50.0, TE=0.5, TATB=1.0, TB=1.0 / 815.0, EMIN=-99.0, EMAX=99.0)
EXCITERS = [
    dict(idx="EXC1", syn="SG1", **EXCITER),
    dict(idx="EXC2", syn="SG2", **EXCITER),
]
PSS = dict(
    MODE=1, MODE2=1, K1=10.0, K2=0.0, T1=0.0, T2=1.0 / 818.0,
    T3=10.0, T4=10.0, T5=0.05, T6=0.02, T7=0.05, T8=0.02,
    T9=1.0 / 825.0, T10=1.0 / 825.0, LSMAX=99.0, LSMIN=-99.0,
)
PSSS = [
    dict(idx="PSS1", avr="EXC1", **PSS),
    dict(idx="PSS2", avr="EXC2", **PSS),
]


def main() -> None:
    from _common import run_and_write

    run_and_write(
        CASE_DIR,
        description=(
            "PSSKundur speed-input stabilizer on GENROU + SEXST vs ANDES "
            "ST2CUT with T1 = 0 on SEXS, three-bus system, loss of line 3-1 "
            "at t = 1 s; constant mechanical power."
        ),
        machines=MACHINES,
        exciter_model="SEXS",
        exciters=EXCITERS,
        exciter_init_vars=("LAW_y", "LL_x", "vref"),
        pss_model="ST2CUT",
        psss=PSSS,
        pss_init_vars=("WO_x", "LL1_x", "LL2_x", "vsout"),
        notes=[
            "hermess state map: vw = WO_x, vl1 = LL1_x, vl2 = LL2_x (same "
            "chain order); Vs = vsout; Efd = SEXS LAW_y.",
            "Unmatched reference modes per machine: SEXS LL_x (-815), ST2CUT "
            "L2_y (-818, K2 = 0), LL3_x (-825, T9 = T10) and the two inert "
            "voltage-derivative states; see case.json "
            "allow_extra_reference_eigenvalues.",
        ],
    )


if __name__ == "__main__":
    main()
