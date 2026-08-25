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

"""Qt-side controller of the simulation worker process."""

from __future__ import annotations

import logging
import multiprocessing as mp
import time

from PySide6.QtCore import QObject, QTimer, Signal

from hermess.gui.worker import RunRequest, simulation_worker

# Seconds to wait for cooperative cancellation before terminating the worker.
# Cancellation is only checked between integration calls, so a long
# disturbance-free interval can exceed this and gets the hard kill.
_CANCEL_GRACE = 5.0


class SimulationRunner(QObject):
    """Runs one simulation at a time in a worker process.

    The pipe is polled from the Qt event loop; no thread is involved on the
    GUI side.
    """

    progressed = Signal(float)  # completed fraction in [0, 1]
    logged = Signal(int, str)  # (levelno, text)
    finished = Signal(object)  # SimulationResults
    failed = Signal(str)  # readable error text
    cancelled = Signal()
    stateChanged = Signal(bool)  # True while a run is active

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = mp.get_context("spawn")
        self._process = None
        self._conn = None
        self._cancel_event = None
        self._cancel_at = None
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._poll)

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self, request: RunRequest) -> None:
        if self.running:
            raise RuntimeError("A simulation is already running.")
        recv_conn, send_conn = self._ctx.Pipe(duplex=False)
        self._conn = recv_conn
        self._cancel_event = self._ctx.Event()
        self._cancel_at = None
        self._process = self._ctx.Process(
            target=simulation_worker,
            args=(send_conn, request, self._cancel_event),
            daemon=True,
        )
        self._process.start()
        send_conn.close()  # keep only the child's handle on the send end
        self._timer.start()
        self.stateChanged.emit(True)

    def stop(self) -> None:
        """Request cancellation; escalates to terminate() after a grace period."""
        if not self.running:
            return
        self._cancel_event.set()
        self._cancel_at = time.monotonic()

    def shutdown(self) -> None:
        """Kill any running worker immediately (application exit)."""
        if self._process is not None:
            self._process.terminate()
            self._process.join(timeout=2.0)
        self._cleanup()

    def _poll(self) -> None:
        final = None
        try:
            while self._conn.poll():
                msg = self._conn.recv()
                kind = msg[0]
                if kind == "log":
                    self.logged.emit(msg[1], msg[2])
                elif kind == "progress":
                    self.progressed.emit(msg[1])
                elif kind in ("done", "cancelled", "error"):
                    final = msg
                    break
        except (EOFError, OSError):
            pass  # pipe closed; the liveness check below decides what happened

        if final is not None:
            self._process.join(timeout=2.0)
            self._cleanup()
            if final[0] == "done":
                self.finished.emit(final[1])
            elif final[0] == "cancelled":
                self.cancelled.emit()
            else:
                self.failed.emit(f"{final[1]}: {final[2]}\n\n{final[3]}")
            return

        if not self._process.is_alive():
            code = self._process.exitcode
            self._cleanup()
            self.failed.emit(
                f"The simulation process ended unexpectedly (exit code {code})."
            )
            return

        if self._cancel_at is not None and time.monotonic() - self._cancel_at > _CANCEL_GRACE:
            logging.warning("Worker ignored cancellation; terminating it.")
            self._process.terminate()
            self._process.join(timeout=2.0)
            self._cleanup()
            self.cancelled.emit()

    def _cleanup(self) -> None:
        self._timer.stop()
        if self._conn is not None:
            self._conn.close()
        self._process = None
        self._conn = None
        self._cancel_event = None
        self._cancel_at = None
        self.stateChanged.emit(False)
