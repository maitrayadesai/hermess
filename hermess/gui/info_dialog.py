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

"""The pop-up a double click in the topology opens: description, control
schematics and parameters of one component (or one bus)."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hermess.gui import theme
from hermess.gui.device_info import MODELS_DOC_URL

_DIAGRAM_SCALE = 1.35  # the SVGs are drawn compact for the docs page


class InfoDialog(QDialog):
    """Non-modal information pop-up; deleted when closed."""

    def __init__(
        self,
        title: str,
        description: "str | None",
        params: "dict[str, str] | None" = None,
        diagrams: "list[tuple[str, Path]] | None" = None,
        doc_link: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(600, 640)

        content = QWidget()
        column = QVBoxLayout(content)
        column.setSpacing(10)

        heading = QLabel(f"<h3>{html.escape(title)}</h3>")
        column.addWidget(heading)

        if description:
            text = QLabel(description)
            text.setWordWrap(True)
            text.setTextFormat(Qt.RichText)
            column.addWidget(text)

        for caption, path in diagrams or []:
            label = QLabel(f"<b>{html.escape(caption)}</b>")
            column.addWidget(label)
            svg = QSvgWidget(str(path))
            size = svg.renderer().defaultSize() * _DIAGRAM_SCALE
            svg.setFixedSize(size)
            svg.setStyleSheet(f"background: {theme.BACKGROUND};")
            column.addWidget(svg)

        if params:
            rows = "".join(
                f"<tr><td style='padding:1px 14px 1px 0'><code>{html.escape(k)}</code></td>"
                f"<td>{html.escape(v)}</td></tr>"
                for k, v in params.items()
            )
            table = QLabel(
                "<b>Parameters (from the system file)</b>"
                f"<table style='margin-top:4px'>{rows}</table>"
            )
            table.setTextFormat(Qt.RichText)
            table.setTextInteractionFlags(Qt.TextSelectableByMouse)
            column.addWidget(table)

        if doc_link:
            link = QLabel(
                f'<a href="{MODELS_DOC_URL}">Full model documentation '
                "(equations and symbol tables)</a>"
            )
            link.setOpenExternalLinks(True)
            column.addWidget(link)

        column.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(scroll)
