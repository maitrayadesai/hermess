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
"""Simulation settings.

:class:`Config` declares every knob of a run (horizon, step, solver, line
model, reference frame, analyses) with validation; the module-level
``config`` instance carries the shipped default scenario. Keyword arguments
of :func:`hermess.simulate` map directly onto these fields.
"""

from pathlib import Path
from typing import Any
from typing import Literal
import logging
from pydantic import BaseModel

IntegrationSchemeSim = Literal["idas", "collocation", "cvodes", "rk"]

Frequency = Literal[50, 60]
Levels = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Reference = Literal["coi", "single", "nom", "dist"]


class Config(BaseModel):
    """Holds all attributes controlling a simulation run."""

    testsystemfile: str
    system_root: Path | None = (
        None  # absolute path to a system-definitions root; None → repo's hermess/systems/
    )
    omega_mode: Reference
    omega_single_idx: str | None = (
        None  # reference device for single-mode (None → use slack bus)
    )
    fn: Frequency  # 50 or 60
    Sb: int  # parameters in .txt table are assumed to be given for 100 MW
    # General input data
    ts: float  # Simulation time step
    T_start: float  # It has to be 0.0
    T_end: float

    int_scheme_sim: IntegrationSchemeSim
    int_scheme_sim_options: dict = (
        {}
    )  # Options passed to ca.integrator(), e.g. {"abstol": 1e-10}

    plot: bool
    plot_voltage: bool
    plot_diff: bool

    incl_lim: bool
    line_dyn: bool  # Simulate with dynamic line models (differential equations)
    skip_disturance: bool  # Run only simulation
    debug_check_init: bool  # Run only simulation
    print_power_flow: bool  # Print initial power flow to output
    small_signal_analysis: bool = (
        False  # Run small-signal eigenvalue/participation analysis at the
        # operating point (before the simulation) and show the figures
    )
    small_signal_figures: bool = (
        True  # Show the small-signal figures (eigenvalue map, participation
        # bands) when small_signal_analysis is set; False computes the data
        # only, for headless or embedded (GUI) use
    )
    parametric: bool = (
        False  # Build the equations with device parameters as CasADi symbols
        # and stash the parametric model as dae.parametric_model (the numeric
        # model is recovered by substitution, so the run itself is unchanged
        # up to floating point rounding). See hermess/parametric.py.
    )
    show_progress: bool = (
        True  # Show the tqdm progress bar during the time stepping; turn off
        # for batch runs and notebooks.
    )
    log_level: Levels

    def updated(self, **kwargs: Any) -> "Config":
        """Return a copy of this config with the given fields overridden.

        :param testsystemfile: The path to the system test case.
        :type testsystemfile: str

        :param fn: System frequency (currently only tested for 50 Hz).
        :type fn: float

        :param omega_mode: Reference frequency mode used in the simulation. Must be `'coi'`, `'single'`, `'nom'` or `'dist'`.
        :type omega_mode: str

        :param omega_single_idx: Reference device identifier (e.g. `"SG1"`) used only if `omega_mode='single'` (None → slack bus).
        :type omega_single_idx: str or None

        :param Sb: Base power of the grid in [MW]. Line parameters are assumed to be calculated using this base power.
        :type Sb: float

        :param ts: Simulation time step.
        :type ts: float

        :param T_start: Simulation start time (must currently be 0).
        :type T_start: float

        :param T_end: End time of the simulation.
        :type T_end: float

        :param plot: Enable or disable plotting.
        :type plot: bool

        :param plot_voltage: Whether to plot voltage data.
        :type plot_voltage: bool

        :param plot_diff: Whether to plot differential state data.
        :type plot_diff: bool

        :param incl_lim: If state limiters should be included in the simulation. If `False`, the simulation will be much faster.
        :type incl_lim: bool

        :param line_dyn: Simulate with line dynamic models (differential equations).
        :type line_dyn: bool

        :param skip_disturance: Skip disturbance simulation.
        :type skip_disturance: bool

        :param debug_check_init: Enable debug check for initialization of DAE system.
        :type debug_check_init: bool

        :param print_power_flow: Print initial power flow to output.
        :type print_power_flow: bool

        :param system_root: Directory holding the system folders. ``None`` uses the
            systems shipped with the package (``hermess/systems``); point it at a
            directory of your own to run a system you wrote.
        :type system_root: Path or None
        :param int_scheme_sim: Integration scheme. ``'idas'`` (default) and
            ``'cvodes'`` are the SUNDIALS variable-step solvers and are the right
            choice for stiff models; ``'collocation'`` and ``'rk'`` are fixed-step
            schemes, faster on smooth problems but less robust.
        :type int_scheme_sim: str
        :param int_scheme_sim_options: Extra options passed to the CasADi
            integrator, e.g. ``{'abstol': 1e-8, 'reltol': 1e-8}``.
        :type int_scheme_sim_options: dict
        :param log_level: Logging verbosity: ``'DEBUG'``, ``'INFO'``,
            ``'WARNING'``, ``'ERROR'`` or ``'CRITICAL'``.
        :type log_level: str
        :param small_signal_analysis: Run the small-signal eigenvalue/participation
            analysis at the operating point (before the simulation) and show the
            frequency-banded participation figures plus the modal report.
        :type small_signal_analysis: bool
        :param small_signal_figures: Show the small-signal figures when
            ``small_signal_analysis`` is set. ``False`` computes the data only
            (``eigenvalues``, ``modes``, participation factors on the returned
            model), for headless or embedded use.
        :type small_signal_figures: bool
        :param parametric: Build the equations with device parameters as
            CasADi symbols, so trajectories and functionals can be
            differentiated with respect to them. The parametric expressions
            are stashed as ``dae.parametric_model``; the run itself uses the
            numeric model recovered by substitution and is unchanged up to
            floating point rounding. See :mod:`hermess.parametric`.
        :type parametric: bool

        :returns: A new instance of the :class:`Config` class configured with the provided parameters.
        :rtype: Config
        """
        return self.model_copy(update=kwargs)

    def get_log_level(self):
        """Returns the log level."""
        valid_levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return valid_levels[self.log_level]


config = Config(
    testsystemfile="ieee39_conv",
    # testsystemfile="3bus",
    omega_mode="nom",
    omega_single_idx="GFMI2",  # reference device for single-mode (None → uses slack bus)
    fn=50,
    Sb=100,  # parameters in .txt table are assumed to be given for 100 MW
    ts=0.0001,  # Simulation time step
    T_start=0.0,  # It has to be 0.0
    T_end=10,
    int_scheme_sim="idas",
    int_scheme_sim_options={
        # "abstol": 1e-12,          # Absolute tolerance (default 1e-8)
        "reltol": 1e-14,  # Relative tolerance (default 1e-6)
        "max_num_steps": 10000,  # Max internal steps between output points
        "max_step_size": 0.01,  # Max internal step size (0 = no limit)
        "jit": True,  # Whether to JIT compile the integrator (requires CasADi with JIT support)
    },
    # #########Plot###############
    plot=True,
    plot_voltage=True,
    plot_diff=True,
    log_level="WARNING",
    incl_lim=False,
    line_dyn=True,
    skip_disturance=False,
    debug_check_init=False,
    print_power_flow=True,
    small_signal_analysis=True,
)
