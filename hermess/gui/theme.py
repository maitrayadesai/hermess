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
BORDER_SOFT = "#E3E5EA"
DISABLED = "#9AA0A6"
HOVER = "#EDF2FA"  # a light tint of ETH Blue for hover states
PRESSED = "#DDE7F5"
MUTED = "#5A5E66"  # secondary text (dock titles, tab labels, group titles)

# The complete look: base colors come from the palette, everything visual
# (borders, radii, hover/focus states) from this sheet. Purely cosmetic; no
# rule may hide or resize a control in a way behavior depends on.
_QSS = f"""
QMainWindow, QDialog {{ background: {PANEL}; }}

/* Tabs: underline style instead of boxes. */
QTabWidget::pane {{
    border: 1px solid {BORDER_SOFT}; border-radius: 6px;
    background: {BACKGROUND}; top: -1px;
}}
QTabBar::tab {{
    background: transparent; border: none; color: {MUTED};
    padding: 6px 14px; margin-right: 2px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ETH_BLUE}; border-bottom: 2px solid {ETH_BLUE}; font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

/* Buttons. */
QPushButton, QToolButton {{
    background: {BACKGROUND}; border: 1px solid #C9CCD1;
    border-radius: 5px; padding: 4px 12px;
}}
QPushButton:hover, QToolButton:hover {{
    background: {HOVER}; border-color: #A9C3E4;
}}
QPushButton:pressed, QToolButton:pressed {{ background: {PRESSED}; }}
QPushButton:disabled, QToolButton:disabled {{
    color: {DISABLED}; background: {PANEL}; border-color: {BORDER_SOFT};
}}
QToolButton:checked, QPushButton:checked {{
    background: {ETH_BLUE}; color: white; border-color: {ETH_BLUE};
}}
QToolButton::menu-indicator {{ image: none; }}

/* Toolbar: flat buttons that light up on hover. */
QToolBar {{
    background: {BACKGROUND}; border-bottom: 1px solid {BORDER};
    spacing: 4px; padding: 3px 6px;
}}
QToolBar QToolButton {{
    background: transparent; border: 1px solid transparent; padding: 4px 10px;
}}
QToolBar QToolButton:hover {{ background: {HOVER}; border-color: {BORDER_SOFT}; }}
QToolBar QToolButton:pressed {{ background: {PRESSED}; }}
QToolBar QToolButton:disabled {{ background: transparent; }}

/* Inputs. */
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {BACKGROUND}; border: 1px solid #C9CCD1;
    border-radius: 4px; padding: 3px 7px;
    selection-background-color: {ETH_BLUE}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {ETH_BLUE};
}}
QLineEdit:disabled, QComboBox:disabled {{ background: {PANEL}; color: {DISABLED}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}

/* Item views. */
QTreeWidget, QTreeView, QTableWidget, QTableView, QListWidget {{
    background: {BACKGROUND}; border: 1px solid {BORDER_SOFT};
    border-radius: 6px; alternate-background-color: #F7F8FA;
}}
QHeaderView::section {{
    background: {PANEL}; color: {MUTED}; font-weight: 600;
    border: none; border-bottom: 1px solid {BORDER}; padding: 5px 8px;
}}
QTreeView::item, QListWidget::item {{ padding: 2px; }}

/* Panels. */
QDockWidget::title {{
    background: {PANEL}; color: {MUTED}; font-weight: 600;
    padding: 5px 10px; border-bottom: 1px solid {BORDER};
}}
QGroupBox {{
    border: 1px solid {BORDER_SOFT}; border-radius: 6px;
    margin-top: 10px; padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED};
}}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
QSplitter::handle {{ background: transparent; }}

/* Context menus (the macOS menu bar itself stays native). */
QMenu {{
    background: {BACKGROUND}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 4px;
}}
QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ETH_BLUE}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER_SOFT}; margin: 4px 8px; }}

/* Slim scrollbars. */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: #C4C8CE; border-radius: 3px; }}
QScrollBar::handle:hover {{ background: #A8ADB5; }}
QScrollBar::handle:vertical {{ min-height: 30px; }}
QScrollBar::handle:horizontal {{ min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{
    border: 1px solid {BORDER}; border-radius: 5px; background: {PANEL};
    height: 12px; text-align: center; font-size: 10px;
}}
QProgressBar::chunk {{ background: {ETH_BLUE}; border-radius: 4px; }}
"""


def series_color(i: int) -> str:
    """Color of the i-th plot series (cycles through the ETH order)."""
    return SERIES[i % len(SERIES)]


def style_plot(plot_widget) -> None:
    """Soften a pyqtgraph plot to match the chrome: light axis lines, muted
    tick labels. Purely cosmetic."""
    import pyqtgraph as pg

    for side in ("left", "bottom"):
        axis = plot_widget.getPlotItem().getAxis(side)
        axis.setPen(pg.mkPen(BORDER))
        axis.setTextPen(pg.mkPen(MUTED))


_ICONS: dict = {}


def icon(name: str):
    """Small vector icons drawn in code (no asset files): 'run', 'stop',
    'options', 'export'. Cached; requires a running QApplication."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

    if name in _ICONS:
        return _ICONS[name]
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    line_pen = QPen(QColor(MUTED), 3)
    line_pen.setCapStyle(Qt.RoundCap)

    if name == "run":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(ETH_BLUE))
        painter.drawPolygon(
            QPolygonF([QPointF(10, 6), QPointF(10, 26), QPointF(27, 16)])
        )
    elif name == "stop":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(ETH_RED))
        painter.drawRoundedRect(QRectF(8, 8, 16, 16), 3, 3)
    elif name == "options":
        # Three slider rails with knobs.
        painter.setPen(line_pen)
        knobs = [(9, 21), (16, 12), (23, 24)]
        for y, _x in knobs:
            painter.drawLine(6, y, 26, y)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(ETH_BLUE))
        for y, x in knobs:
            painter.drawEllipse(QPointF(x, y), 3.4, 3.4)
    elif name == "export":
        # An arrow into a tray.
        painter.setPen(line_pen)
        painter.drawLine(16, 6, 16, 18)
        painter.drawLine(10, 13, 16, 19)
        painter.drawLine(22, 13, 16, 19)
        painter.drawLine(7, 24, 25, 24)
    painter.end()
    _ICONS[name] = QIcon(pixmap)
    return _ICONS[name]


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
