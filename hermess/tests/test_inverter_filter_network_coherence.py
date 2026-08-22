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

"""Filter/network coherence gate: warn-but-continue when an inverter's
output-filter realization does not match the network model -- a dynamic ``LCL``
on a quasi-static network (``line_dyn=False``), or a quasi-static ``LCL_static``
on a dynamic network (``line_dyn=True``).

The check (``run.warn_filter_network_mismatch``) reads only the filter strategy's
``algebs()`` and the device's ``bus``, so these tests drive it with lightweight
stubs rather than a full inverter + data-file context."""

import logging

from hermess.devices.inverter_filter import LCL, LCL_static
from hermess.run import warn_filter_network_mismatch


class _InverterStub:
    """Stand-in exposing only what the check reads: a filter strategy + bus list."""

    def __init__(self, filt, bus):
        self._filter = filt
        self.bus = bus


class _NonInverterStub:
    """A device without a pluggable filter (an SG / load): must be skipped."""

    def __init__(self, bus):
        self.bus = bus


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def test_static_filter_on_dynamic_network_warns(caplog):
    with caplog.at_level(logging.WARNING):
        warn_filter_network_mismatch([_InverterStub(LCL_static(), ["B7"])], line_dyn=True)
    msgs = _warnings(caplog)
    assert len(msgs) == 1
    assert "on a DYNAMIC network" in msgs[0]
    assert "LCL_static" in msgs[0] and "B7" in msgs[0]


def test_dynamic_filter_on_static_network_warns(caplog):
    with caplog.at_level(logging.WARNING):
        warn_filter_network_mismatch([_InverterStub(LCL(), ["B9"])], line_dyn=False)
    msgs = _warnings(caplog)
    assert len(msgs) == 1
    assert "on a QUASI-STATIC network" in msgs[0]
    assert "B9" in msgs[0]


def test_coherent_dynamic_is_silent(caplog):
    with caplog.at_level(logging.WARNING):
        warn_filter_network_mismatch([_InverterStub(LCL(), ["B1"])], line_dyn=True)
    assert _warnings(caplog) == []


def test_coherent_static_is_silent(caplog):
    with caplog.at_level(logging.WARNING):
        warn_filter_network_mismatch([_InverterStub(LCL_static(), ["B1"])], line_dyn=False)
    assert _warnings(caplog) == []


def test_mixed_list_flags_only_the_mismatch(caplog):
    # Dynamic network: the LCL is coherent (silent), only the LCL_static is flagged.
    with caplog.at_level(logging.WARNING):
        warn_filter_network_mismatch(
            [_InverterStub(LCL(), ["GFM"]), _InverterStub(LCL_static(), ["GFL"])],
            line_dyn=True,
        )
    msgs = _warnings(caplog)
    assert len(msgs) == 1
    assert "GFL" in msgs[0] and "GFM" not in msgs[0]


def test_non_inverter_devices_are_skipped(caplog):
    with caplog.at_level(logging.WARNING):
        warn_filter_network_mismatch(
            [_NonInverterStub(["B1"]), _InverterStub(LCL(), ["B2"])], line_dyn=True
        )
    assert _warnings(caplog) == []
