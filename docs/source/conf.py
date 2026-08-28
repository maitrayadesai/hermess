# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "HERMESS"
copyright = "2024-2026, ETH Zurich. Created by Milos Katanic and Maitraya Avadhut Desai"
author = "Milos Katanic, Maitraya Avadhut Desai"
try:  # single-source the version from the installed package metadata
    from importlib.metadata import version as _pkg_version

    release = _pkg_version("hermess")
except Exception:  # building docs without an installed hermess
    release = "1.2.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_ext"))

extensions = [
    "sphinx.ext.autodoc",
    "autoapi.extension",
    "sphinx_autodoc_typehints",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinx_reredirects",
    "sphinxarg.ext",
    "myst_parser",
    "nbsphinx",
    "hermess_models",
]

napoleon_google_docstring = True
# Render docstring "Attributes:" sections as :ivar: fields instead of
# .. attribute:: directives; autoapi already registers every attribute, and
# registering them twice raises duplicate-description warnings.
napoleon_use_ivar = True
autodoc_typehints = "both"  # 'signature' or 'description' or 'both'

autoapi_type = "python"
autoapi_dirs = ["../../hermess"]
# Hide methods, attributes, and functions by limiting the depth
autoapi_depth = 2  # Show modules and classes only, no deeper levels
# The test suite, the system-file folders and the benchmarks are not part of
# the public API; keeping them out leaves a reference to the modules a user
# calls.
autoapi_ignore = ["*/tests/*", "*/systems/*", "*/benchmarks/*"]
# Default autoapi options minus "private-members": underscore-prefixed helpers are
# implementation detail and do not belong in the published reference.
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
    "imported-members",
]
autoapi_keep_files = True  # Optional: keeps generated files in 'autoapi'
# The API reference is placed in the toctree by hand (index.rst), so its
# position in the sidebar is controlled.
autoapi_add_toctree_entry = False

templates_path = ["_templates"]
exclude_patterns = []

# Annotations like ``Dict[str, type]`` make the Python domain fuzzy-match the
# builtin ``type`` against the ``BusInit.type``/``Disturbance.type``
# attributes and warn about the ambiguity; that is a resolver artifact, not a
# documentation defect.
suppress_warnings = ["ref.python"]

language = "en"

# -- Notebooks ----------------------------------------------------------------
# The example notebooks live in examples/ at the repository root and are
# committed without outputs; they are copied next to the examples page and
# executed at build time, so the site always shows outputs of the installed
# version.

_EXAMPLE_FILES = [
    "examples/demo.ipynb",
    "examples/basic_usage/basic_usage.ipynb",
    "examples/renewables/39bus_inv.ipynb",
    "examples/neural_gfm_control/3bus_gfm_nn_control.ipynb",
]
# Gallery thumbnails must be inside a copied static dir, so the preview image
# goes to _static (gitignored there).
_EXAMPLE_THUMBS = ["examples/neural_gfm_control/preview_response.png"]

nbsphinx_execute = "auto"
nbsphinx_timeout = 900
# The notebook kernels inherit this process's environment. A forced
# MPLBACKEND=Agg (as older build scripts set) would override ipykernel's
# inline backend and break plt.show() inside the notebooks, so drop it; on a
# headless builder matplotlib falls back to Agg on its own.
os.environ.pop("MPLBACKEND", None)
nbsphinx_thumbnails = {
    "examples/39bus_inv": "_static/39network_inv.jpg",
    "examples/3bus_gfm_nn_control": "_static/preview_response.png",
}


def _copy_example_notebooks(app):
    import shutil

    repo = Path(__file__).resolve().parents[2]
    target = Path(__file__).parent / "examples"
    target.mkdir(exist_ok=True)
    for rel in _EXAMPLE_FILES:
        shutil.copy2(repo / rel, target / Path(rel).name)
    static = Path(__file__).parent / "_static"
    for rel in _EXAMPLE_THUMBS:
        shutil.copy2(repo / rel, static / Path(rel).name)


def setup(app):
    app.connect("builder-inited", _copy_example_notebooks)


# -- Redirects from the pre-2026 flat layout ---------------------------------

redirects = {
    "models": "models/index.html",
    "models_static": "models/network.html",
    "cases": "systems.html",
    "usage": "guide/simulating.html",
    "advanced_usage": "guide/system_files.html",
    "installation": "getting_started/installation.html",
    "configuration": "guide/configuration.html",
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "shibuya"
html_title = "HERMESS"
html_baseurl = "https://maitrayadesai.github.io/hermess/"

html_theme_options = {
    "accent_color": "blue",  # radix preset; the ETH Blue scale lives in hermess.css
    "color_mode": "light",  # light default, the toggle stays available
    "light_logo": "_static/schematics/logo_light.svg",
    "dark_logo": "_static/schematics/logo_dark.svg",
    "github_url": "https://github.com/maitrayadesai/hermess",
    "show_ai_links": False,
    "nav_links": [
        {"title": "Get started", "url": "getting_started/installation"},
        {"title": "Guide", "url": "guide/simulating"},
        {"title": "Models", "url": "models/index"},
        {"title": "Examples", "url": "examples/index"},
        {"title": "API", "url": "autoapi/hermess/index"},
        {
            "title": "PyPI",
            "url": "https://pypi.org/project/hermess/",
            "external": True,
        },
    ],
}

# "Edit this page" links in the right sidebar.
html_context = {
    "source_type": "github",
    "source_user": "maitrayadesai",
    "source_repo": "hermess",
    "source_version": "main",
    "source_docs_path": "/docs/source/",
}

html_static_path = ["_static"]
html_css_files = ["hermess.css"]
html_favicon = "_static/schematics/logo_light.svg"


latex_elements = {
    "preamble": r"\usepackage{amsmath}",  # Add this line to include amsmath
}
# Ensure UTF-8 encoding is used
source_encoding = "utf-8"
