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

extensions = [
    "sphinx.ext.autodoc",
    "autoapi.extension",
    "sphinx_autodoc_typehints",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
    "sphinx_design",
    "sphinx_copybutton",
    "nbsphinx",
]

napoleon_google_docstring = True
autodoc_typehints = "both"  # 'signature' or 'description' or 'both'

autoapi_type = "python"
autoapi_dirs = ["../../hermess"]
# Hide methods, attributes, and functions by limiting the depth
autoapi_depth = 2  # Show modules and classes only, no deeper levels
# The test suite, the system-file folders, the benchmarks and the internal
# utils are not part of the public API; keeping them out leaves a reference to
# the modules a user calls.
autoapi_ignore = ["*/tests/*", "*/systems/*", "*/benchmarks/*", "*/utils/*"]
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

language = "en"

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
        {"title": "Install", "url": "installation"},
        {"title": "Models", "url": "models"},
        {"title": "Validation", "url": "validation"},
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
