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

from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hermess.errors import SimulationCancelled
from hermess.registry import register, registered, unregister

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from hermess.results import SimulationResults
    from hermess.system import DaeSim

try:
    __version__ = version("hermess")  # Must match the name in pyproject.toml
except PackageNotFoundError:  # running from source without an install
    __version__ = "1.0.0"


__all__ = [
    "__version__",
    "SYSTEMS_DIR",
    "list_systems",
    "simulate",
    "register",
    "registered",
    "unregister",
    "extract_results",
    "SimulationResults",
    "SimulationCancelled",
    "help",
]

SYSTEMS_DIR = Path(__file__).parent / "systems"


def __getattr__(name: str) -> Any:
    # Lazy re-exports of the results container, so `import hermess` does not
    # pull pandas until results are actually extracted.
    if name in ("extract_results", "SimulationResults"):
        from hermess import results as _results

        return getattr(_results, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def list_systems(root: "str | Path | None" = None) -> list:
    """Names of the ready-made systems, usable as the first argument of
    :func:`simulate` (or as ``testsystemfile`` in a :class:`~hermess.config.Config`)."""
    root = Path(root).expanduser() if root is not None else SYSTEMS_DIR
    return sorted(str(p.parent.relative_to(root)) for p in root.rglob("sim_param.txt"))


def simulate(
    system: str,
    system_root: "str | Path | None" = None,
    progress_callback: Any = None,
    init_callback: Any = None,
    **overrides: Any,
) -> "DaeSim":
    """Run one simulation and return the finished :class:`~hermess.system.DaeSim`.

    The short form of ``config.updated(...)`` followed by
    :func:`hermess.run.run`, for the common case of "simulate this system with a
    few settings changed"::

        import hermess
        dae = hermess.simulate("3bus_loadstep", T_end=5.0)
        dae = hermess.simulate("ieee39", line_dyn=False, T_end=10.0, plot=True)

    :param system: A system name from :func:`list_systems`, or a folder name under
        ``system_root``.
    :param system_root: Where to look for the system folder (default: the systems
        shipped with the package). Point it at your own directory to run a system
        you wrote or edited.
    :param progress_callback: Optional hook called during the time stepping with
        the completed fraction in [0, 1]; returning ``False`` cancels the run by
        raising :class:`~hermess.errors.SimulationCancelled`.
    :param init_callback: Optional hook called once with the initialized model
        at the operating point, before the time stepping; returning ``False``
        cancels the run (e.g. after inspecting ``dae.eigenvalues``).
    :param overrides: Any field of :class:`~hermess.config.Config`
        (``T_end``, ``ts``, ``line_dyn``, ``omega_mode``, ``small_signal_analysis``,
        ``plot``, ...). Plotting is off by default here, unlike the shipped
        configuration, so the call returns quietly and you plot what you want from
        the returned object.
    :returns: The :class:`~hermess.system.DaeSim` holding the symbolic model and
        the trajectories.
    """
    from hermess.config import config as _default_config
    from hermess.run import run as _run

    settings = dict(
        testsystemfile=system,
        system_root=Path(system_root).expanduser() if system_root is not None else None,
        plot=False,
        plot_voltage=False,
        plot_diff=False,
        print_power_flow=False,
        small_signal_analysis=False,
    )
    settings.update(overrides)
    return _run(
        _default_config.updated(**settings),
        progress_callback=progress_callback,
        init_callback=init_callback,
    )


def help() -> None:
    """
    Prints an overview of the hermess package and usage instructions.
    """
    print(
        r"""
    📦 hermess — Power System Dynamic Simulator
    ------------------------------------------------------
    Time-domain dynamic simulation of power systems modeled by nonlinear
    differential-algebraic equations (DAEs).

    🔧 Key Modules:
    - run.py      : Simulation execution
    - system.py   : DAE system model
    - config.py   : Simulation settings
    - registry.py : Registration of user-defined models

    🚀 Usage:
    >>> import hermess
    >>> hermess.list_systems()                       # what is available
    >>> dae = hermess.simulate("3bus", T_end=5.0)   # run one
    >>> hermess.registered("angle")                  # selectable strategies
    >>> hermess.register(MyAngleSource, "VSM")       # add your own

    🧾 License:
    GNU General Public License v3.0 or later (GPL-3.0-or-later)
    https://www.gnu.org/licenses/gpl-3.0.en.html

    ℹ️ Provenance:
    Simulation-only fork of PowerDynamicEstimator
    (https://doi.org/10.5905/ethz-1007-842); dynamic state estimation removed.
    Contact: mdesai@ethz.ch
    """
    )
