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

"""What the topology's double-click dialogs show: a short description of the
model (from the device class docstring) and the matching control schematics.

The schematics are the SVG block diagrams the documentation uses
(``docs/source/_static/schematics``); with an editable source install they are
found next to the package, otherwise the dialog falls back to a link to the
online model documentation.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path

MODELS_DOC_URL = "https://maitrayadesai.github.io/hermess/models.html"


def schematics_dir() -> "Path | None":
    """The local schematics folder, or None when not available (non-source
    install without the docs tree)."""
    import hermess

    path = (
        Path(hermess.__file__).parent.parent
        / "docs"
        / "source"
        / "_static"
        / "schematics"
    )
    return path if path.is_dir() else None


# ---- descriptions -----------------------------------------------------------

_CLASS_DOCS: "dict[str, str | None] | None" = None


_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "zeta": "ζ",
    "eta": "η", "theta": "θ", "lambda": "λ", "xi": "ξ", "pi": "π",
    "sigma": "σ", "tau": "τ", "phi": "φ", "psi": "ψ", "omega": "ω",
    "Delta": "Δ", "Omega": "Ω", "infty": "∞", "times": "×", "cdot": "·",
}


def _strip_rst(text: str) -> str:
    """Reduce an rst docstring paragraph to readable plain text."""
    text = re.sub(r":(?:mod|class|meth|attr|func|ref):`~?([^`]*)`", r"\1", text)
    text = re.sub(r":math:`([^`]*)`", r"\1", text)
    text = text.replace("``", "")
    # Light LaTeX cleanup for math that leaked into prose: greek letters and
    # brace-wrapped subscripts.
    text = re.sub(
        r"\\([A-Za-z]+)", lambda m: _GREEK.get(m.group(1), m.group(1)), text
    )
    text = re.sub(r"_\{([^{}]*)\}", r"_\1", text)
    return re.sub(r"\s+", " ", text).strip()


def class_description(kind: str) -> "str | None":
    """First docstring paragraph of the device class named ``kind``.

    Scans the ``hermess.devices`` modules once and caches the result; a class
    the scan does not find (e.g. a user-registered model) yields None.
    """
    global _CLASS_DOCS
    if _CLASS_DOCS is None:
        _CLASS_DOCS = {}
        package = importlib.import_module("hermess.devices")
        for module_info in pkgutil.iter_modules(package.__path__):
            try:
                module = importlib.import_module(
                    f"hermess.devices.{module_info.name}"
                )
            except Exception:
                continue
            for name, obj in vars(module).items():
                if isinstance(obj, type) and obj.__doc__ and name not in _CLASS_DOCS:
                    first = obj.__doc__.strip().split("\n\n")[0]
                    _CLASS_DOCS[name] = _strip_rst(first)
    return _CLASS_DOCS.get(kind)


# ---- schematic mapping ------------------------------------------------------

_AVR_SVG = {
    "IEEEDC1A": "avr_ieeedc1a.svg",
    "SEXST": "avr_sexst.svg",
    "AVRST1A": "avr_st1a.svg",
    "AVRAC1A": "avr_ac1a.svg",
    "AVRKundur": "avr_kundur.svg",
    "AVRKundur_Filter": "avr_kundur.svg",
    "AVRKundur_NoTGR": "avr_kundur.svg",
    "AVRKundur_ODE": "avr_kundur.svg",
}
_GOV_SVG = {"TGOV1": "gov_tgov1.svg", "TGTypeII": "gov_tgtype2.svg"}

_SM_PREFIXES = ("Synchronous", "GENROU", "GENSAL", "Marconato")
_INVERTER_PREFIXES = ("GridForming", "GridFollowing", "GridSupporting")


def schematics_for(entry) -> "list[tuple[str, str]]":
    """(caption, filename) pairs of the diagrams matching a parsed device
    entry: the family's structure diagram plus one per explicitly selected
    strategy that has a drawn schematic."""
    kind = entry.kind
    diagrams: list[tuple[str, str]] = []

    if kind.startswith(_SM_PREFIXES):
        diagrams.append(("Model composition", "sm_composition.svg"))
        avr = _AVR_SVG.get(entry.get("avr"))
        if avr:
            diagrams.append((f"AVR ({entry.get('avr')})", avr))
        gov = _GOV_SVG.get(entry.get("governor"))
        if gov:
            diagrams.append((f"Governor ({entry.get('governor')})", gov))
        if entry.get("pss"):
            diagrams.append((f"PSS ({entry.get('pss')})", "pss.svg"))
        if entry.get("shaft") not in ("", "SingleMass"):
            diagrams.append(
                (f"Multi-mass shaft ({entry.get('shaft')})", "shaft_chain.svg")
            )
    elif kind.startswith(_INVERTER_PREFIXES):
        diagrams.append(("Control structure", "conv_structure.svg"))
        if kind.startswith(("GridFollowing", "GridSupporting")):
            diagrams.append(("Grid-following loop", "conv_gfl.svg"))
            diagrams.append(("SRF PLL", "pll_srf.svg"))
        diagrams.append(("LCL output filter", "lcl.svg"))
    elif kind == "SVC":
        diagrams.append(("SVC control", "svc.svg"))

    return diagrams


def line_schematic() -> "tuple[str, str]":
    return ("Dynamic pi-section line", "line_pi.svg")
