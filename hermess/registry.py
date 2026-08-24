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

"""Registration of user-defined models, so they can be selected from a system file.

Every model in hermess is either a **device** (a class in ``hermess.devices``
addressed by its class name in the first column of ``sim_param.txt``) or a
**strategy** (an AVR, governor, PSS, shaft, or one of the converter's filter /
angle / voltage / inner / PLL blocks, addressed by a keyword such as
``avr = "SEXST"`` or ``angle = "Droop"``).

A model written outside the package -- in a script, a notebook, or another
library -- becomes selectable in exactly the same way once it is registered::

    import hermess

    class VSMAngle(AngleSource):
        ...

    hermess.register(VSMAngle, "VSM")     # now: angle = "VSM" in sim_param.txt

The kind is inferred from the base class, so a single call covers every model
type. :func:`registered` lists what is currently available, shipped and
user-defined together.
"""

from __future__ import annotations

from typing import Iterable

# Device classes registered by users. ``hermess.utils.data_loader`` consults this
# first, before scanning the modules of ``hermess.devices``, so a class defined in
# a notebook is found by name like any shipped device.
DEVICE_REGISTRY: dict[str, type] = {}


def _strategy_registries() -> dict[str, tuple]:
    """Map ``kind -> (base class, registry dict)``, imported lazily to keep this
    module free of import cycles."""
    from hermess.devices.avr import AVR, AVR_REGISTRY
    from hermess.devices.governor import Governor, GOVERNOR_REGISTRY
    from hermess.devices.inverter_angle import AngleSource, ANGLE_REGISTRY
    from hermess.devices.inverter_filter import Filter, FILTER_REGISTRY
    from hermess.devices.inverter_inner import InnerControl, INNER_REGISTRY
    from hermess.devices.inverter_pll import PLL, PLL_REGISTRY
    from hermess.devices.inverter_voltage import VoltageControl, VOLTAGE_REGISTRY
    from hermess.devices.pss import PSS, PSS_REGISTRY
    from hermess.devices.shaft import Shaft, SHAFT_REGISTRY

    return {
        "avr": (AVR, AVR_REGISTRY),
        "governor": (Governor, GOVERNOR_REGISTRY),
        "pss": (PSS, PSS_REGISTRY),
        "shaft": (Shaft, SHAFT_REGISTRY),
        "filter": (Filter, FILTER_REGISTRY),
        "angle": (AngleSource, ANGLE_REGISTRY),
        "voltage": (VoltageControl, VOLTAGE_REGISTRY),
        "inner": (InnerControl, INNER_REGISTRY),
        "pll": (PLL, PLL_REGISTRY),
    }


def register(cls: type, name: str | None = None, kind: str | None = None) -> type:
    """Make a user-defined model selectable from a system file.

    :param cls: The class to register: a device (subclass of
        :class:`~hermess.devices.device.Element`) or a strategy (subclass of
        ``AVR``, ``Governor``, ``PSS``, ``Shaft``, ``Filter``, ``AngleSource``,
        ``VoltageControl``, ``InnerControl`` or ``PLL``).
    :param name: The keyword to select it by. Defaults to the class name; for a
        device the class name is the only accepted spelling, so ``name`` is
        ignored there.
    :param kind: Normally inferred from the base class. Pass it only to force a
        registry (e.g. for a class that subclasses several bases).
    :returns: ``cls``, so :func:`register` can be used as a decorator.

    Registering the same name twice replaces the earlier entry, which is what you
    want while iterating on a model in a notebook.

    Example::

        @hermess.register            # a device: selected as  MyLoad, bus = "2"
        class MyLoad(DeviceRect):
            ...

        hermess.register(VSMAngle, "VSM")   # a strategy: selected as  angle = "VSM"
    """
    from hermess.devices.device import Element

    if kind is not None:
        registries = _strategy_registries()
        if kind == "device":
            DEVICE_REGISTRY[cls.__name__] = cls
            return cls
        if kind not in registries:
            raise KeyError(f"unknown kind {kind!r}; expected 'device' or one of {sorted(registries)}")
        registries[kind][1][name or cls.__name__] = cls
        return cls

    for k, (base, reg) in _strategy_registries().items():
        if issubclass(cls, base):
            reg[name or cls.__name__] = cls
            return cls

    if issubclass(cls, Element):
        DEVICE_REGISTRY[cls.__name__] = cls
        return cls

    raise TypeError(
        f"{cls.__name__} is neither a device (subclass of Element) nor a known strategy; "
        f"subclass one of the strategy base classes or pass kind= explicitly."
    )


def registered(kind: str | None = None) -> dict[str, list[str]]:
    """What can be selected from a system file today, shipped and user-defined.

    ``registered()`` returns ``{kind: [names]}`` for every strategy axis plus the
    user-registered devices; ``registered("angle")`` narrows it to one axis.
    """
    out: dict[str, list[str]] = {k: sorted(reg) for k, (_, reg) in _strategy_registries().items()}
    out["device (user-registered)"] = sorted(DEVICE_REGISTRY)
    if kind is None:
        return out
    matches = [k for k in out if k == kind or k.startswith(kind)]
    if not matches:
        raise KeyError(f"unknown kind {kind!r}; expected one of {sorted(out)}")
    return {k: out[k] for k in matches}


def unregister(name: str, kind: str) -> None:
    """Remove a previously registered model (mostly useful in tests)."""
    if kind == "device":
        DEVICE_REGISTRY.pop(name, None)
        return
    registries = _strategy_registries()
    if kind not in registries:
        raise KeyError(f"unknown kind {kind!r}; expected 'device' or one of {sorted(registries)}")
    registries[kind][1].pop(name, None)


def _iter_kinds() -> Iterable[str]:
    return list(_strategy_registries()) + ["device"]
