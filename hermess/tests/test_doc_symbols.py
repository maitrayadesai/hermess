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

"""The model documentation cannot drift from the code.

Every model class documents its equations (``.. math::``) and a symbols table
mapping the code names to mathematical symbols. These tests pin that structure:
each parameter, state, private algebraic and setpoint a model actually declares
must appear as ````name```` in its class docstring (or an ancestor's, for
models that inherit their parameter set), and every model must carry equations
and a table somewhere in its hierarchy. The auto-generated "Attributes" section
(``DeviceRect.__init_subclass__``) uses no backticks, so it cannot satisfy the
check; only the hand-written tables can.
"""

import inspect

import pytest

from hermess.registry import _strategy_registries


def _mro_doc(cls) -> str:
    return "\n".join(inspect.getdoc(k) or "" for k in cls.__mro__)


def _assert_documented(cls, names, doc=None):
    doc = doc if doc is not None else _mro_doc(cls)
    missing = [n for n in names if f"``{n}``" not in doc]
    assert not missing, (
        f"{cls.__name__}: not in any symbols table of the class hierarchy: {missing}"
    )
    assert ".. math::" in doc or "**Model.**" in doc, f"{cls.__name__}: no model equations"
    assert "csv-table" in doc, f"{cls.__name__}: no symbols table"


def _strategy_cases():
    for kind, (_base, reg) in _strategy_registries().items():
        for name, cls in reg.items():
            yield pytest.param(kind, cls, id=f"{kind}-{name}")


@pytest.mark.parametrize("kind, cls", list(_strategy_cases()))
def test_strategy_symbols_tables_match_the_api(kind, cls):
    inst = cls()
    # Not every strategy axis declares every hook (shafts have no algebs()).
    names = list(inst.params()) + list(inst.states())
    names += list(getattr(inst, "algebs", list)())
    names += list(getattr(inst, "setpoints", dict)() or {})
    _assert_documented(cls, names)


def _device_cases():
    from hermess.devices import inverter, static, svc, synchronous
    from hermess.devices.device import BusInit, Disturbance, Line

    for cls in (
        synchronous.SynchronousTransient,
        synchronous.SynchronousSubtransient,
        synchronous.SynchronousSubtransientSP,
        synchronous.SynchronousSubtransientSP6,
        synchronous.SynchronousSubtransientSP6DAE,
        synchronous.SynchronousSubtransientSP_DAE,
        synchronous.GENROU,
        synchronous.GENSAL,
        inverter.GridForming,
        inverter.GridFollowing,
        svc.SVC,
        static.StaticZIP,
        static.StaticLoadPower,
        static.StaticLoadImpedance,
        static.StaticInfiniteBus,
        Line,
        BusInit,
        Disturbance,
    ):
        yield pytest.param(cls, id=cls.__name__)


@pytest.mark.parametrize("cls", list(_device_cases()))
def test_device_symbols_tables_cover_every_parameter(cls):
    inst = cls()
    # Parameters live on the instance; strategy-owned parameters are documented
    # in the strategy classes, so exclude them for the composed devices.
    names = set(inst._params)
    for strat in ("_avr", "_governor", "_pss", "_shaft",
                  "_filter", "_angle", "_voltage", "_inner", "_pll"):
        obj = getattr(inst, strat, None)
        if obj is not None:
            names -= set(obj.params())
    doc = _mro_doc(cls)
    missing = [n for n in sorted(names) if f"``{n}``" not in doc]
    assert not missing, (
        f"{cls.__name__}: parameters missing from the symbols tables: {missing}"
    )
    assert "csv-table" in doc, f"{cls.__name__}: no symbols table"
