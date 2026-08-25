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

"""Regenerate the result figures shown on the installation page.

Runs the scenario shipped in ``hermess/config.py`` (the one ``python -m
hermess`` executes) and saves the two figures the built-in plotting produces,
in the same style as :func:`hermess.run.fplot`:

- ``docs/source/_static/voltage.png`` — bus voltage magnitudes,
- ``docs/source/_static/diffstates.png`` — the differential states of the
  synchronous machines.

Run from the repository root::

   MPLBACKEND=Agg python docs/gen_result_figures.py

The default scenario integrates 10 s of the IEEE 39-bus converter system with
dynamic lines at a 0.1 ms step, so expect a runtime of minutes.
"""

import pickle
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

OUT = Path(__file__).resolve().parent / "source" / "_static"


def collect() -> dict:
    """Run the shipped default scenario and collect the trajectories."""
    warnings.filterwarnings("ignore")
    from hermess.config import config
    from hermess.run import run

    cfg = config.updated(
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        small_signal_analysis=False,
        print_power_flow=False,
        log_level="ERROR",
    )
    dae = run(cfg)
    return {
        "t": dae.time_steps,
        "buses": list(dae.grid.buses),
        "yf": {b: dae.grid.yf[b] for b in dae.grid.buses},
        "devices": [
            {
                "name": type(d).__name__,
                "long_name": d._name,
                "int": dict(d.int),
                "states": list(d.states),
                "xf": {s: np.asarray(d.xf[s]) for s in d.states},
            }
            for d in dae.device_list
            if d.properties.get("fplot")
        ],
    }


def plot_voltage(data: dict) -> None:
    """Bus voltage magnitudes, in the style of hermess.run.fplot."""
    plt.figure(figsize=(9, 5.5))
    viridis = plt.get_cmap("viridis", len(data["buses"]))
    for i, node in enumerate(data["buses"]):
        y = data["yf"][node]
        v = np.sqrt(y[0, :] ** 2 + y[1, :] ** 2)
        plt.plot(data["t"], v, color=viridis(i), linewidth=0.9)
    plt.title("Voltage Profiles", fontsize=14)
    plt.xlabel("Time [s]")
    plt.ylabel("Voltage Magnitude [p.u.]")
    # The electromagnetic fault transient spikes far beyond the quasi-static
    # band for a few milliseconds; clip the axis so the trajectories stay
    # readable.
    plt.ylim(0.5, 1.15)
    plt.tight_layout()
    plt.savefig(OUT / "voltage.png", dpi=110)
    plt.close()


def plot_diffstates(data: dict) -> None:
    """Differential states of the synchronous machines, one row per machine,
    one column per state, in the style of hermess.run.fplot."""
    dev = next(d for d in data["devices"] if d["name"].startswith("Synchronous"))
    units, states = len(dev["int"]), dev["states"]
    fig, axis = plt.subplots(
        units, len(states), sharex=True,
        figsize=(len(states) * 2.4, units * 1.9),
    )
    axis = np.atleast_2d(axis)
    # Align rotor angles to the first unit (taken as the reference).
    xf = {s: dev["xf"][s].copy() for s in states}
    if "delta" in states:
        xf["delta"] = xf["delta"] - xf["delta"][0]
    for idx, row in dev["int"].items():
        for col, state in enumerate(states):
            axis[row, col].plot(data["t"], np.asarray(xf[state])[row], color="black",
                                linewidth=0.8)
            axis[row, col].tick_params(labelsize=7)
            if col == 0:
                axis[row, col].set_ylabel(f"Device {idx}", fontsize=9)
            if row == 0:
                axis[row, col].set_title(state, fontsize=10)
    fig.supxlabel("Time [s]", fontsize=11)
    fig.suptitle(f"Differential States of {dev['long_name']}", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(OUT / "diffstates.png", dpi=110)
    plt.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:  # plot from a previously collected pickle
        with open(sys.argv[1], "rb") as f:
            data = pickle.load(f)
    else:
        data = collect()
    plot_voltage(data)
    plot_diffstates(data)
    print(f"wrote {OUT / 'voltage.png'} and {OUT / 'diffstates.png'}")
