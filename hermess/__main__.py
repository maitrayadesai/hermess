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

"""Command-line interface, installed as the ``hermess`` console script and
runnable as ``python -m hermess``. Thin wrapper around the package API
(:func:`hermess.list_systems`, :func:`hermess.simulate`); heavy imports happen
inside the subcommand handlers so ``hermess --help`` stays instant."""

import argparse
import json
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

try:
    __version__ = version("hermess")  # Must match the name in pyproject.toml
except PackageNotFoundError:  # running from source without an install
    __version__ = "1.6.1"


def _cmd_list(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import hermess

    for name in hermess.list_systems(args.system_root):
        print(name)
    return 0


def _config_overrides(
    pairs: "list[str]", parser: argparse.ArgumentParser
) -> "dict[str, object]":
    """Turn ``--set KEY=VALUE`` pairs into validated Config overrides."""
    from hermess.config import Config

    overrides: "dict[str, object]" = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            parser.error(f"--set expects KEY=VALUE, got {pair!r}")
        if key not in Config.model_fields:
            parser.error(
                f"unknown configuration field {key!r}; "
                "the valid fields are those of hermess.config.Config"
            )
        try:
            overrides[key] = json.loads(raw)  # numbers, true/false, lists, dicts
        except json.JSONDecodeError:
            overrides[key] = raw  # plain strings, e.g. --set omega_mode=coi
    return overrides


def _cmd_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import hermess

    settings: "dict[str, object]" = {
        "plot": not args.no_plot,
        "plot_voltage": not args.no_plot,
        "plot_diff": not args.no_plot,
    }
    if args.t_end is not None:
        settings["T_end"] = args.t_end
    if args.ts is not None:
        settings["ts"] = args.ts
    if args.small_signal:
        settings["small_signal_analysis"] = True
    settings.update(_config_overrides(args.set, parser))

    try:
        hermess.simulate(args.system, system_root=args.system_root, **settings)
    except FileNotFoundError as exc:
        print(
            f"error: system {args.system!r} not found ({exc}).\n"
            "Run `hermess list` to see the shipped systems, or pass "
            "--system-root for your own.",
            file=sys.stderr,
        )
        return 1
    print(f"Simulated {args.system}.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermess",
        description=(
            "HERMESS: time-domain dynamic simulation of power systems "
            "modeled by nonlinear differential-algebraic equations."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_list = sub.add_parser("list", help="list the runnable systems")
    p_list.add_argument(
        "--system-root",
        type=Path,
        default=None,
        help="directory holding the system folders (default: the systems "
        "shipped with the package)",
    )
    p_list.set_defaults(func=_cmd_list)

    p_run = sub.add_parser(
        "run",
        help="run a simulation",
        epilog="Any other field of hermess.config.Config is reachable with "
        "--set, e.g. --set line_dyn=false --set omega_mode=coi. Values are "
        "parsed as JSON, falling back to plain strings.",
    )
    p_run.add_argument("system", help="a system name from `hermess list`")
    p_run.add_argument(
        "--system-root",
        type=Path,
        default=None,
        help="directory holding the system folders (default: the systems "
        "shipped with the package)",
    )
    p_run.add_argument("--t-end", type=float, default=None, help="end time [s]")
    p_run.add_argument("--ts", type=float, default=None, help="time step [s]")
    p_run.add_argument(
        "--no-plot",
        action="store_true",
        help="skip the voltage and state figures",
    )
    p_run.add_argument(
        "--small-signal",
        action="store_true",
        help="run the small-signal analysis at the operating point",
    )
    p_run.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override any hermess.config.Config field (repeatable)",
    )
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args, parser)


if __name__ == "__main__":
    sys.exit(main())
