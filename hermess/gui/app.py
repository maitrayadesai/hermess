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

"""Application entry point: ``hermess-gui`` / ``python -m hermess.gui``."""

from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    # The worker uses the spawn context explicitly; freeze_support keeps a
    # frozen/installed entry point from re-running the GUI in the children.
    multiprocessing.freeze_support()

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit(
            "The HERMESS GUI needs the optional GUI dependencies.\n"
            "Install them with:  pip install hermess[gui]"
        ) from exc

    from hermess.gui import theme
    from hermess.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("HERMESS")
    app.setOrganizationName("ETH Zurich")
    theme.apply(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
