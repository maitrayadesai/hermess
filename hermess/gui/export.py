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

"""CSV export of selected signals, in the plot-ready paper-data format:
``t`` plus one named column per signal, comma-separated with a header row.
A ``<name>.provenance.txt`` sidecar records where the data came from, so the
CSV itself stays clean for pgfplots."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def export_csv(path: "str | Path", results, signals: "list[tuple[str, np.ndarray]]") -> Path:
    """Write ``t`` + the given (name, trajectory) columns to ``path``.

    Returns the path of the provenance sidecar written next to it.
    """
    path = Path(path)
    t = results.t
    n = min([len(t)] + [len(traj) for _, traj in signals])
    columns = [t[:n]] + [np.real_if_close(traj[:n]) for _, traj in signals]
    names = ["t"] + [name for name, _ in signals]

    with open(path, "w", newline="") as fid:
        writer = csv.writer(fid)
        writer.writerow(names)
        writer.writerows(np.column_stack(columns))

    sidecar = path.with_suffix(path.suffix + ".provenance.txt")
    overrides = {
        key: value
        for key, value in results.config.items()
        if key in ("T_end", "ts", "line_dyn", "omega_mode", "int_scheme_sim")
    }
    sidecar.write_text(
        f"file: {path.name}\n"
        f"sim: hermess {results.hermess_version} (GUI)\n"
        f"system: {results.system}\n"
        f"settings: {overrides}\n"
        f"date: {results.created}\n"
        f"signals: {', '.join(name for name, _ in signals)}\n"
    )
    return sidecar
