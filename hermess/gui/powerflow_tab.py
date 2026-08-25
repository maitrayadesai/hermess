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

"""Initial power flow of the shown run, as sortable bus and branch tables."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hermess.gui import theme


def _fill(table: QTableWidget, frame) -> None:
    table.setSortingEnabled(False)
    table.setRowCount(len(frame))
    table.setColumnCount(len(frame.columns))
    table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
    for row in range(len(frame)):
        for col, name in enumerate(frame.columns):
            value = frame.iloc[row, col]
            if isinstance(value, (float, np.floating)):
                item = QTableWidgetItem()
                # Numeric sort key with a rounded display.
                item.setData(Qt.EditRole, round(float(value), 4))
            else:
                item = QTableWidgetItem(str(value))
            table.setItem(row, col, item)
    table.resizeColumnsToContents()
    table.setSortingEnabled(True)


class PowerFlowTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._placeholder = QLabel("No run shown yet. The initial power flow of a run appears here.")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(f"color: {theme.ETH_GREY};")

        self._tabs = QTabWidget()
        self._bus_table = QTableWidget()
        self._branch_table = QTableWidget()
        for table in (self._bus_table, self._branch_table):
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.verticalHeader().setVisible(False)
        self._tabs.addTab(self._bus_table, "Buses")
        self._tabs.addTab(self._branch_table, "Branches")
        self._tabs.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._placeholder)
        layout.addWidget(self._tabs)

    def set_results(self, results) -> None:
        has_data = results is not None and results.power_flow_bus is not None
        self._tabs.setVisible(has_data)
        self._placeholder.setVisible(not has_data)
        if not has_data:
            return
        _fill(self._bus_table, results.power_flow_bus)
        if results.power_flow_branch is not None:
            _fill(self._branch_table, results.power_flow_branch)
        else:
            self._branch_table.setRowCount(0)
