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

"""Simulation worker process for the GUI (no Qt in this module).

The GUI spawns one worker process per run: the core keeps the model in
module-level state and reloads it per run, so a fresh process gives a clean
model, an unblockable GUI and a hard cancellation path. The worker sends
tuple messages over a one-way pipe:

``("log", levelno, text)``
    A log record from the simulation.
``("progress", fraction)``
    Completed fraction of the time stepping in [0, 1], throttled.
``("done", SimulationResults)``
    The finished run's data; final message on success.
``("cancelled",)``
    The run was cancelled through the cancel event.
``("error", type_name, message, traceback_text)``
    The run failed; final message on failure.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from hermess.errors import SimulationCancelled


@dataclass
class RunRequest:
    """Everything the worker needs to run one simulation."""

    system: str  #: system name (folder under the root)
    system_root: "str | None" = None  #: root folder; None = shipped systems
    overrides: "dict[str, Any]" = field(default_factory=dict)  #: Config overrides


class _PipeLogHandler(logging.Handler):
    """Forwards log records over the pipe; drops them if the pipe is gone."""

    def __init__(self, conn):
        super().__init__()
        self._conn = conn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._conn.send(("log", record.levelno, self.format(record)))
        except (OSError, ValueError, BrokenPipeError):
            pass


class _PipeStdout:
    """Forwards the core's print() output (modal report, tables) line-wise to
    the pipe, so it reaches the GUI log instead of a terminal."""

    def __init__(self, conn):
        self._conn = conn
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            if line.strip():
                try:
                    self._conn.send(("log", logging.INFO, line))
                except (OSError, ValueError, BrokenPipeError):
                    pass
        return len(text)

    def flush(self) -> None:
        pass


# Minimum seconds between progress messages; 0 and 1 always pass.
PROGRESS_INTERVAL = 0.1


def simulation_worker(conn, request: RunRequest, cancel_event) -> None:
    """Process entry point: run one simulation and stream messages to ``conn``."""
    # Quiet the terminal-oriented output before hermess (and tqdm) load: the
    # GUI gets progress through the pipe, not through a progress bar.
    os.environ.setdefault("TQDM_DISABLE", "1")
    import matplotlib

    matplotlib.use("Agg", force=True)

    root = logging.getLogger()
    handler = _PipeLogHandler(conn)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root.addHandler(handler)
    original_stdout = sys.stdout
    sys.stdout = _PipeStdout(conn)

    try:
        from hermess.config import config as default_config
        from hermess.results import extract_results
        from hermess.run import run as run_simulation

        # Mirrors hermess.simulate(): quiet by default, every figure and
        # printout suppressed; the results container carries the data instead.
        settings: dict[str, Any] = dict(
            testsystemfile=request.system,
            system_root=request.system_root,
            plot=False,
            plot_voltage=False,
            plot_diff=False,
            print_power_flow=False,
            small_signal_figures=False,
        )
        settings.update(request.overrides)
        cfg = default_config.updated(**settings)
        root.setLevel(cfg.get_log_level())

        last_sent = 0.0

        def report(fraction: float):
            nonlocal last_sent
            now = time.monotonic()
            if fraction in (0.0, 1.0) or now - last_sent >= PROGRESS_INTERVAL:
                conn.send(("progress", float(fraction)))
                last_sent = now
            if cancel_event.is_set():
                return False

        dae = run_simulation(cfg, progress_callback=report)
        results = extract_results(dae, cfg)
        conn.send(("done", results))
    except SimulationCancelled:
        conn.send(("cancelled",))
    except Exception as exc:  # the final message must always arrive
        conn.send(("error", type(exc).__name__, str(exc), traceback.format_exc()))
    finally:
        sys.stdout = original_stdout
        root.removeHandler(handler)
        conn.close()
