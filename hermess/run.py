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

from matplotlib import cm

from hermess.utils import data_loader
from hermess.config import Config
from hermess import parametric
import matplotlib.pyplot as plt
import importlib
from hermess import system
from pathlib import Path
import numpy as np
import logging
import sys
import os
import warnings

import matplotlib


def _use_interactive_backend() -> None:
    """Switch to the interactive TkAgg backend for the built-in pop-up figures.

    Called from :func:`fplot` (i.e. only when ``config.plot`` is set), never at
    import time: importing hermess must not take over the caller's backend, or
    inline figures in Jupyter stop rendering. Falls back to the non-interactive
    Agg backend in headless environments (e.g. CI) where Tk or a display is
    absent, and leaves an already-interactive backend alone.
    """
    if matplotlib.get_backend().lower() not in ("agg", "template"):
        return
    try:
        matplotlib.use("TkAgg")
    except Exception:
        matplotlib.use("Agg")


#: Pre-rename folder names of the shipped systems, mapped to the uniform
#: names introduced later; consulted (with a DeprecationWarning) when a
#: requested system folder does not exist.
_LEGACY_SYSTEM_NAMES = {
    "3_bus": "3bus",
    "3_bus_loadstep": "3bus_loadstep",
    "IEEE39_bus": "ieee39",
    "IEEE39_bus_ideal": "ieee39_ideal",
    "IEEE39_bus_inverter": "ieee39_conv",
    "IEEE39_bus_inverter_old": "ieee39_conv_old",
    "kundur_avr_newtest": "kundur",
    "kundur_converter": "kundur_conv",
    "SEA_14gen/SEA_case1": "sea14gen/case1",
    "SEA_14gen/SEA_case1_conv": "sea14gen/case1_conv",
    "SEA_14gen/SEA_case1_nopss": "sea14gen/case1_nopss",
    "SEA_14gen/SEA_case2": "sea14gen/case2",
    "SEA_14gen/SEA_case2_nopss": "sea14gen/case2_nopss",
    "SEA_14gen/SEA_case3": "sea14gen/case3",
    "SEA_14gen/SEA_case3_nopss": "sea14gen/case3_nopss",
    "SEA_14gen/SEA_case4": "sea14gen/case4",
    "SEA_14gen/SEA_case4_nopss": "sea14gen/case4_nopss",
    "SEA_14gen/SEA_case5": "sea14gen/case5",
    "SEA_14gen/SEA_case5_nopss": "sea14gen/case5_nopss",
    "SEA_14gen/SEA_case6": "sea14gen/case6",
    "SEA_14gen/SEA_case6_nopss": "sea14gen/case6_nopss",
    "SEA_14gen/SMIB_check": "sea14gen/smib",
}


def warn_filter_network_mismatch(device_list, line_dyn: bool) -> None:
    """Warn (but continue) when an inverter's output-filter realization is
    physically incoherent with the network model.

    A quasi-static filter (``LCL_static``, the six filter quantities as algebraic
    variables) zeroes the fast LCL dynamics and presumes a quasi-static network
    (``line_dyn=False``); a dynamic filter (``LCL``, those quantities as
    differential states) presumes a dynamic network (``line_dyn=True``). The
    crossed pairings are physically incoherent and flagged.

    The filter realization is read from the filter strategy's own ``algebs()``:
    a quasi-static realization declares its quantities as private algebraics, a
    dynamic one declares none. Non-inverter devices have no ``_filter`` and are
    skipped.
    """
    for dev in device_list:
        filt = getattr(dev, "_filter", None)
        if filt is None:
            continue
        static_filter = len(filt.algebs()) > 0
        if static_filter and line_dyn:
            logging.warning(
                "Inverter at bus(es) %s uses a quasi-static filter (%s) on a "
                "DYNAMIC network (line_dyn=True): the filter zeroes the fast LCL "
                "dynamics the network still carries -- physically incoherent. Use "
                "a dynamic filter (LCL) or set line_dyn=False.",
                list(dev.bus),
                type(filt).__name__,
            )
        elif not static_filter and not line_dyn:
            logging.warning(
                "Inverter at bus(es) %s uses a dynamic filter (%s) on a "
                "QUASI-STATIC network (line_dyn=False): the filter carries fast "
                "LCL dynamics the network has dropped -- physically incoherent. "
                "Use a quasi-static filter (LCL_static) or set line_dyn=True.",
                list(dev.bus),
                type(filt).__name__,
            )


def run(config: Config, progress_callback=None, init_callback=None) -> system.DaeSim:
    """Initialize and run the dynamic simulation.

    :param progress_callback: Optional hook called during the time stepping
        with the completed fraction in [0, 1]. Returning ``False`` cancels the
        run by raising :class:`~hermess.errors.SimulationCancelled`. See
        :attr:`hermess.system.DaeSim.progress_callback` for the granularity.
    :param init_callback: Optional hook called once with the initialized
        :class:`~hermess.system.DaeSim` at the operating point, after the
        small-signal analysis (when enabled) and before the time stepping.
        Returning ``False`` cancels the run by raising
        :class:`~hermess.errors.SimulationCancelled`.
    """

    clear_module("hermess.system")
    importlib.reload(system)

    # Set up logging
    logging.basicConfig(level=config.get_log_level())
    base_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    # The system folders were renamed to a uniform scheme; accept the old
    # names for a transition period so existing scripts keep working.
    legacy = _LEGACY_SYSTEM_NAMES.get(config.testsystemfile)
    if legacy is not None:
        root = (
            Path(config.system_root)
            if config.system_root is not None
            else Path(__file__).parent / "systems"
        )
        if not (root / config.testsystemfile).exists() and (root / legacy).exists():
            warnings.warn(
                f"system '{config.testsystemfile}' was renamed to '{legacy}'; "
                "update the name, the old one will stop working in a future release",
                DeprecationWarning,
                stacklevel=2,
            )
            config = config.updated(testsystemfile=legacy)

    system_root = (
        Path(config.system_root)
        if config.system_root is not None
        else base_dir / "systems"
    )
    simfile = system_root / config.testsystemfile / "sim_param.txt"

    if config.skip_disturance is False:
        simdistfile = system_root / config.testsystemfile / "sim_dist.txt"

    with open(simfile, "rt") as fid:
        data_loader.read(fid, "sim")

    if config.skip_disturance is False:
        with open(simdistfile, "rt") as fid:
            data_loader.read(fid, "sim")

    system.grid_sim.add_lines(system.line_sim)

    # Simulation
    for item in system.device_list_sim:
        if item.properties["xy_index"]:
            item.xy_index(system.dae_sim, system.grid_sim)

    system.dae_sim.t = config.ts

    # Attach grid, device list and bus_init before setup(), which sizes the
    # symbolic reference-frequency vectors from the grid and is also used by the
    # reference-frame methods that iterate the device list and bus_init.
    system.dae_sim.grid = system.grid_sim
    system.dae_sim.device_list = system.device_list_sim
    system.dae_sim.bus_init = system.bus_init_sim

    system.dae_sim.setup(**vars(config))

    # Warn-only coherence check: inverter filter realization vs network model.
    warn_filter_network_mismatch(system.device_list_sim, config.line_dyn)

    system.grid_sim.setup(dae=system.dae_sim, bus_init=system.bus_init_sim)

    if config.print_power_flow:
        system.grid_sim.print_init_power_flow(system.dae_sim)

    for item in system.device_list_sim:
        if item.properties["finit"]:
            item.finit(system.dae_sim)

    # Parametric build: initialization is finished (numeric), the equations
    # are not assembled yet, so the parameters can be swapped for symbols in
    # between without touching any model body. See hermess/parametric.py.
    registry = None
    if config.parametric:
        registry = parametric.swap_parameters(system.device_list_sim)

    for item in system.device_list_sim:
        if item.properties["fgcall"]:
            item.fgcall(system.dae_sim)

    system.grid_sim.gcall(system.dae_sim, line=system.line_sim)

    if registry is not None:
        # Stash the parametric expressions (dae_sim.parametric_model),
        # substitute the numeric values back in place and restore the numeric
        # device attributes; the rest of the run is the model as built today.
        parametric.finalize(system.dae_sim, registry)

    system.disturbance_sim.sort_chrono()

    system.dae_sim.progress_callback = progress_callback
    system.dae_sim.init_callback = init_callback

    system.dae_sim.check_initialization()

    if config.debug_check_init:
        system.dae_sim.debug_check_initialization()

    system.dae_sim.simulate(system.disturbance_sim)

    system.grid_sim.save_data(system.dae_sim)
    for item in system.device_list_sim:
        if item.properties["save_data"]:
            item.save_data(system.dae_sim)

    if config.plot:
        fplot(config)

    return system.dae_sim


def fplot(config: Config):
    """Plot voltage and differential states from the simulation."""
    logging.basicConfig(level=logging.WARNING)
    _use_interactive_backend()

    if config.plot_voltage:
        plt.figure(figsize=(15, 11))
        viridis = cm.get_cmap("viridis", system.dae_sim.grid.nn)

        for i, node in enumerate(system.dae_sim.grid.buses):
            try:
                sim_voltage = np.sqrt(
                    system.grid_sim.yf[node][0, :] ** 2
                    + system.grid_sim.yf[node][1, :] ** 2
                )
                plt.plot(
                    system.dae_sim.time_steps,
                    sim_voltage,
                    color=viridis(i),
                    label=f"{node}",
                )
            except KeyError:
                logging.warning(f"Node {node} cannot be plotted.")

        plt.legend()
        plt.title("Voltage Profiles", fontsize=16)
        plt.xlabel("Time [s]")
        plt.ylabel("Voltage Magnitude")

    if config.plot_diff:
        for device_plt in system.device_list_sim:
            if device_plt.properties["fplot"]:

                num_units = device_plt.n
                num_states = device_plt.ns

                figure, axis = plt.subplots(
                    num_units,
                    num_states,
                    sharex=True,
                    figsize=(num_states * 5, num_units * 5),
                )
                axis = np.atleast_2d(axis)
                figure.supxlabel("Time [s]", fontsize=15)

                # Align rotor angles to the first unit (taken as the reference).
                if "delta" in device_plt.states:
                    reference = device_plt.xf["delta"][0].copy()
                    for n in device_plt.int.values():
                        device_plt.xf["delta"][n] -= reference

                t_sim = np.arange(
                    system.dae_sim.T_start,
                    system.dae_sim.T_end,
                    system.dae_sim.t,
                )

                for idx, n_sim in device_plt.int.items():
                    for col, state in enumerate(device_plt.states):
                        try:
                            axis[n_sim, col].plot(
                                t_sim, device_plt.xf[state][n_sim], color="black"
                            )
                            axis[n_sim, col].tick_params(labelsize=15)

                            # Label the y-axis only in the first column
                            if col == 0:
                                axis[n_sim, col].set_ylabel(
                                    f"Device {idx}", fontsize=15
                                )

                            # Add a title to each column indicating the state
                            if n_sim == 0:
                                axis[n_sim, col].set_title(state, fontsize=15)

                        except KeyError:
                            logging.warning(
                                f"State '{state}' not found for unit {device_plt}."
                            )

                # Adjust layout for clarity
                figure.suptitle(
                    f"Differential States of {device_plt._name}",
                    fontsize=16,
                )

                plt.tight_layout(rect=[0, 0, 1, 0.95])

        logging.info("Simulation successful!")

    # Small-signal analysis (modal report + frequency-banded participation
    # figures) runs inside dae_sim.simulate() at the operating point, before the
    # time-stepping loop, when config.small_signal_analysis is True; its figures
    # are displayed here.
    plt.show(block=True)


def clear_module(module_name):
    """Remove all attributes from a module, preparing it for a clean reload."""
    if module_name in sys.modules:
        module = sys.modules[module_name]
        module_dict = module.__dict__
        to_delete = [
            name
            for name in module_dict
            if not name.startswith("__")  # Avoid special and built-in attributes
        ]
        for name in to_delete:
            del module_dict[name]
