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

"""Visual identity of the GUI: ETH Zürich palette, fonts, plot defaults.

The GUI commits to one light theme. The Fusion style plus a fully explicit
palette is used instead of the platform style: the native macOS/Windows styles
follow the system light/dark appearance, and any partial restyling on top of a
dark system palette produces illegible mixtures. Every color role is set here,
so nothing is inherited from the system.
"""

from __future__ import annotations

# ETH Zürich corporate colors.
ETH_BLUE = "#215CAF"
ETH_PETROL = "#007894"
ETH_GREEN = "#627313"
ETH_BRONZE = "#8E6713"
ETH_RED = "#B7352D"
ETH_PURPLE = "#A7117A"
ETH_GREY = "#6F6F6F"

#: Series order for plots, matching the paper figures.
SERIES = [ETH_BLUE, ETH_PETROL, ETH_RED, ETH_GREEN, ETH_BRONZE, ETH_PURPLE, ETH_GREY]

TEXT = "#222222"
BACKGROUND = "#FFFFFF"
PANEL = "#F2F3F6"
BORDER = "#D5D8DD"
DISABLED = "#9AA0A6"

# Accents only; all base coloring comes from the palette below.
_QSS = f"""
QToolBar {{ border-bottom: 1px solid {BORDER}; spacing: 4px; }}
QDockWidget::title {{ padding: 4px 8px; }}
QProgressBar {{
    border: 1px solid {BORDER}; border-radius: 2px; background: {PANEL};
    height: 12px; text-align: center; font-size: 10px;
}}
QProgressBar::chunk {{ background: {ETH_BLUE}; }}
"""


def series_color(i: int) -> str:
    """Color of the i-th plot series (cycles through the ETH order)."""
    return SERIES[i % len(SERIES)]


def _light_palette():
    """A complete light palette; no role is left to the system appearance."""
    from PySide6.QtGui import QColor, QPalette

    palette = QPalette()
    roles = {
        QPalette.Window: PANEL,
        QPalette.WindowText: TEXT,
        QPalette.Base: BACKGROUND,
        QPalette.AlternateBase: "#EBEEF3",
        QPalette.Text: TEXT,
        QPalette.Button: PANEL,
        QPalette.ButtonText: TEXT,
        QPalette.BrightText: BACKGROUND,
        QPalette.ToolTipBase: BACKGROUND,
        QPalette.ToolTipText: TEXT,
        QPalette.PlaceholderText: DISABLED,
        QPalette.Highlight: ETH_BLUE,
        QPalette.HighlightedText: BACKGROUND,
        QPalette.Link: ETH_BLUE,
        QPalette.LinkVisited: ETH_PURPLE,
        QPalette.Light: "#FFFFFF",
        QPalette.Midlight: "#E4E6EA",
        QPalette.Mid: "#C9CCD1",
        QPalette.Dark: "#B0B3B8",
        QPalette.Shadow: "#9A9DA2",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(DISABLED))
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor(PANEL))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#C9CCD1"))
    return palette


def apply(app) -> None:
    """Apply the theme to a running QApplication and to pyqtgraph."""
    from PySide6.QtGui import QFontDatabase
    import pyqtgraph as pg

    # Fusion renders from the palette alone, identically on every platform and
    # unaffected by the OS light/dark appearance.
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    app.setStyleSheet(_QSS)

    # Papers are set in Latin Modern; use it when installed so screenshots sit
    # naturally next to the figures, otherwise keep the platform font.
    font = app.font()
    families = set(QFontDatabase.families())
    for family in ("Latin Modern Roman", "CMU Serif"):
        if family in families:
            font.setFamily(family)
            font.setPointSize(max(font.pointSize(), 12))
            app.setFont(font)
            break

    pg.setConfigOptions(
        antialias=True,
        background=BACKGROUND,
        foreground=TEXT,
    )
