"""Sphinx directive that generates model-availability tables from the package.

``.. hermess-model-table:: <kind>`` renders a table of the models selectable in
a system file, sourced from the same registries the simulator uses, so the
docs cannot drift from the code.

* a strategy kind (``avr``, ``governor``, ``pss``, ``shaft``, ``filter``,
  ``angle``, ``voltage``, ``inner``, ``pll``) tabulates the registered
  keywords for that axis;
* ``devices:<module>`` (e.g. ``devices:synchronous``) tabulates the concrete
  device classes defined in ``hermess.devices.<module>``.
"""

import importlib
import inspect
import re

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.statemachine import ViewList
from sphinx.util.nodes import nested_parse_with_titles


def _summary(obj) -> str:
    doc = inspect.getdoc(obj) or ""
    paragraph = " ".join(doc.strip().split("\n\n", 1)[0].split())
    # First sentence of the first paragraph. A sentence boundary is a period
    # followed by whitespace and an uppercase letter, which keeps
    # abbreviations like "Fig. 5" intact.
    return re.split(r"(?<=\.)\s+(?=[A-Z])", paragraph)[0]


def _table_lines(kind: str) -> list[str]:
    from hermess import registry
    from hermess.devices.device import DeviceRect

    lines = [
        ".. list-table::",
        "   :header-rows: 1",
        "   :widths: 18 30 52",
        "",
    ]
    if kind.startswith("devices:"):
        modname = "hermess.devices." + kind.split(":", 1)[1]
        module = importlib.import_module(modname)
        lines[2] = "   :widths: 34 66"
        lines += [
            "   * - Class",
            "     - Description",
        ]
        for name, obj in vars(module).items():
            if (
                inspect.isclass(obj)
                and obj.__module__ == modname
                and not name.startswith("_")
                and issubclass(obj, DeviceRect)
                and not inspect.isabstract(obj)
            ):
                lines += [
                    f"   * - :class:`~{modname}.{name}`",
                    f"     - {_summary(obj)}",
                ]
    else:
        registries = registry._strategy_registries()
        if kind not in registries:
            raise ValueError(
                f"unknown model-table kind {kind!r}; "
                f"expected one of {sorted(registries)} or 'devices:<module>'"
            )
        _base, reg = registries[kind]
        lines += [
            f"   * - ``{kind} =``",
            "     - Class",
            "     - Description",
        ]
        for keyword in sorted(reg):
            cls = reg[keyword]
            lines += [
                f"   * - ``\"{keyword}\"``",
                f"     - :class:`~{cls.__module__}.{cls.__qualname__}`",
                f"     - {_summary(cls)}",
            ]
    lines.append("")
    return lines


class HermessModelTable(Directive):
    required_arguments = 1

    def run(self):
        kind = self.arguments[0].strip()
        content = ViewList()
        for i, line in enumerate(_table_lines(kind)):
            content.append(line, f"<hermess-model-table {kind}>", i)
        node = nodes.section()
        node.document = self.state.document
        nested_parse_with_titles(self.state, content, node)
        return node.children


def setup(app):
    app.add_directive("hermess-model-table", HermessModelTable)
    return {"parallel_read_safe": True, "parallel_write_safe": True}
