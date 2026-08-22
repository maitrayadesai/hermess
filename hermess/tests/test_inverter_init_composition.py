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

"""The strategy-composed sequential init: each strategy owns its stage, the host
orchestrates by name. Byte-identity of the composed init is covered by the
recur/selector/init-method gates; here we lock the two composition guarantees:

1. **Compatibility warning** -- if the inner controller needs a plant capability
   the filter doesn't provide, the host warns (but continues).
2. **Init guard** -- a strategy that provides no ``finit_sequential`` raises a
   clear error instead of silently mis-initializing.
"""

import logging

import pytest

from hermess.devices.inverter import GridForming
from hermess.devices.inverter_inner import Cascaded
from hermess.devices.inverter_voltage import QVDroop, VoltageControl


def test_default_combo_no_warning(caplog):
    """The default LCL + Cascaded combo is compatible (capacitor provided)."""
    with caplog.at_level(logging.WARNING):
        GridForming()
    assert not any(
        "strategy mismatch" in r.getMessage().lower() for r in caplog.records
    )


def test_capability_mismatch_warns(caplog, monkeypatch):
    """An inner controller requiring a plant feature the filter lacks warns."""
    monkeypatch.setattr(Cascaded, "requires", lambda self: {"flux_capacitor"})
    with caplog.at_level(logging.WARNING):
        GridForming()
    msgs = [r.getMessage() for r in caplog.records]
    assert any("flux_capacitor" in m and "Cascaded" in m for m in msgs), msgs


def test_sequential_init_guard(monkeypatch):
    """A strategy with no sequential init raises a clear error (rather than
    silently solving the wrong equations)."""
    # Make QVDroop fall back to the abstract base (no finit_sequential).
    monkeypatch.setattr(QVDroop, "finit_sequential", VoltageControl.finit_sequential)
    with pytest.raises(NotImplementedError, match="sequential voltage init"):
        QVDroop().finit_sequential(None, None, None, None)
