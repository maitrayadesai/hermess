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

"""Log panel: the worker's log stream, colored by level."""

from __future__ import annotations

import html
import logging

from PySide6.QtWidgets import QPlainTextEdit

from hermess.gui import theme

_LEVEL_COLORS = {
    logging.WARNING: theme.ETH_BRONZE,
    logging.ERROR: theme.ETH_RED,
    logging.CRITICAL: theme.ETH_RED,
}


class LogPanel(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        font = self.font()
        font.setFamily("Menlo")
        font.setStyleHint(font.StyleHint.Monospace)
        self.setFont(font)

    def append_record(self, levelno: int, text: str) -> None:
        color = _LEVEL_COLORS.get(levelno)
        escaped = html.escape(text)
        if color:
            self.appendHtml(f'<span style="color:{color}">{escaped}</span>')
        else:
            self.appendHtml(f'<span style="color:{theme.TEXT}">{escaped}</span>')

    def append_notice(self, text: str) -> None:
        """A message from the GUI itself (run started, finished, ...)."""
        self.appendHtml(
            f'<span style="color:{theme.ETH_BLUE}">{html.escape(text)}</span>'
        )
