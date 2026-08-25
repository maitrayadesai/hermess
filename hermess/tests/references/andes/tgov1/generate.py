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

"""ANDES reference for the TGOV1 case: the twin of ``system/sim_param.txt``.

The GENROU machines of the genrou case (with D = 0, so the governors are the
only speed feedback) closed by one TGOV1 per machine. The ANDES TGOV1 reduces
exactly to the hermess two-lag TGOV1 with the lead-lag disabled: R = Rd,
T1 = Tsv (valve lag), T2 = 0 (no lead), T3 = Tch (steam-chest lag), Dt = 0,
and the valve limits wide open (hermess runs with incl_lim = False). State
map: LAG_y = psv, LL_x = pm. Regenerate with::

    uv run --group validation python hermess/tests/references/andes/tgov1/generate.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR.parent))

# One dict per machine; every entry mirrors the hermess sim_param.txt line.
MACHINE = dict(
    Sn=100, fn=50, M=13.0, D=0.0, ra=0.0025, xl=0.2,
    xd=1.8, xq=1.7, xd1=0.3, xq1=0.55, xd2=0.25, xq2=0.25,
    Td10=8.0, Tq10=0.4, Td20=0.03, Tq20=0.05, S10=0.0, S12=1.0,
)
MACHINES = [
    dict(idx="SG1", bus=1, gen="GS1", **MACHINE),
    dict(idx="SG2", bus=3, gen="GP3", **MACHINE),
]
GOVERNOR = dict(R=0.05, T1=0.5, T2=0.0, T3=1.0, Dt=0.0, VMAX=10.0, VMIN=-10.0)
GOVERNORS = [
    dict(idx="GOV1", syn="SG1", **GOVERNOR),
    dict(idx="GOV2", syn="SG2", **GOVERNOR),
]


def main() -> None:
    from _common import run_and_write

    run_and_write(
        CASE_DIR,
        description=(
            "TGOV1 turbine governor on GENROU machines, three-bus system, "
            "loss of line 3-1 at t = 1 s; constant field voltage."
        ),
        machines=MACHINES,
        governors=GOVERNORS,
        notes=[
            "hermess state map: psv=LAG_y, pm=LL_x (T2 = 0 turns the ANDES "
            "lead-lag into the pure steam-chest lag T3 = Tch).",
            "hermess incl_lim = False matches VMAX/VMIN = +/-10 (never "
            "reached).",
        ],
    )


if __name__ == "__main__":
    main()
