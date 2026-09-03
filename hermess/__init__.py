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
"""HERMESS, a hybrid EMT/RMS power system dynamics simulator.

The public surface is small: :func:`simulate` runs a system and returns the
finished :class:`~hermess.system.DaeSim`; :func:`list_systems` names what can
be run; :func:`register`, :func:`registered` and :func:`unregister` manage
user models; :func:`extract_results` and :class:`SimulationResults` post-
process a run. Everything else is implementation.
"""

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
    __version__ = "1.7.2"


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


def _is_shipped(path) -> bool:
    """True when ``path`` lies inside the systems shipped with the package."""
    try:
        return Path(path).expanduser().resolve().is_relative_to(SYSTEMS_DIR.resolve())
    except (OSError, ValueError):
        return False


def _assert_not_shipped(path, what: str = "write to") -> Path:
    """Refuse a write into the systems shipped with the package.

    Every helper that writes system files (:func:`hermess.analysis.set_param`,
    :func:`hermess.analysis.set_disturbances`,
    :func:`hermess.analysis.copy_system`, the GUI's save) calls this first,
    so the installed package can never be edited by accident. Returns the
    expanded path; raises :class:`PermissionError` when it resolves to a
    location under :data:`SYSTEMS_DIR`.
    """
    path = Path(path).expanduser()
    if _is_shipped(path):
        raise PermissionError(
            f"Refusing to {what} {path}: it is inside the systems shipped with "
            f"the package ({SYSTEMS_DIR}). Work on a copy instead: "
            "hermess.analysis.copy_system(name, dest) makes one, and the "
            "returned path is the system_root to simulate from."
        )
    return path


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


def _system_defaults(system: str, system_root) -> dict:
    """Read the optional per-system defaults file ``<system>/sim_settings.txt``.

    One ``field = value`` per line (``#`` comments allowed), each field a
    :class:`~hermess.config.Config` name, values in JSON. A system ships the
    settings it needs to run out of the box, e.g. ``line_dyn = false`` for a
    network whose transformer branches carry no charging; anything passed to
    :func:`simulate` explicitly still wins. Only :func:`simulate` (and the
    command line, which uses it) reads this file; building a
    :class:`~hermess.config.Config` manually for :func:`hermess.run.run`
    keeps full manual control.
    """
    import json

    from hermess.config import Config

    root = (
        Path(system_root).expanduser()
        if system_root is not None
        else Path(__file__).parent / "systems"
    )
    path = root / system / "sim_settings.txt"
    if not path.exists():
        return {}
    defaults = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected 'field = value', got {raw!r}")
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in Config.model_fields:
            raise ValueError(
                f"{path}:{number}: {key!r} is not a configuration field"
            )
        try:
            defaults[key] = json.loads(value)
        except json.JSONDecodeError:
            lowered = value.lower()
            if lowered in ("true", "false"):
                defaults[key] = lowered == "true"
            else:
                defaults[key] = value.strip("\'\"")
    return defaults


def simulate(
    system: str,
    system_root: "str | Path | None" = None,
    progress_callback: Any = None,
    init_callback: Any = None,
    quiet: bool = False,
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
        the completed fraction in [0, 1]; a falsy return other than ``None``
        cancels the run by raising :class:`~hermess.errors.SimulationCancelled`.
    :param init_callback: Optional hook called once with the initialized model
        at the operating point, before the time stepping; a falsy return other
        than ``None`` cancels the run (e.g. after inspecting
        ``dae.eigenvalues``).
    :param quiet: Silence the run: no progress bar, warnings-only logging
        (``show_progress=False``, ``log_level="WARNING"``). An explicit
        override of either field still wins.
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
    settings.update(_system_defaults(system, settings["system_root"]))
    if quiet:
        settings.update(show_progress=False, log_level="WARNING")
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
