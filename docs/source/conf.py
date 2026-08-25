# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "HERMESS"
copyright = "2024-2026, ETH Zurich. Created by Milos Katanic and Maitraya Avadhut Desai"
author = "Milos Katanic, Maitraya Avadhut Desai"
release = "1.0.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration
# Use the Read the Docs theme
html_theme = "sphinx_rtd_theme"

# Optional: Configure theme options
html_theme_options = {
    "collapse_navigation": False,  # Keep the navigation expanded
    "sticky_navigation": True,  # Make the sidebar navigation sticky
    "navigation_depth": 4,  # Depth of the navigation tree
    "includehidden": True,  # Show hidden TOC entries
    "titles_only": False,  # Show full titles instead of short titles
}

html_title = "HERMESS Documentation"
napoleon_google_docstring = True
autodoc_typehints = "both"  # 'signature' or 'description' or 'both'
autosummary_generate = True

extensions = [
    "sphinx.ext.autodoc",
    "autoapi.extension",
    "sphinx.ext.autosummary",
    "sphinx_autodoc_typehints",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx.ext.mathjax",
    "nbsphinx",
]
autoapi_type = "python"
autoapi_dirs = ["../../hermess"]
# Hide methods, attributes, and functions by limiting the depth
autoapi_depth = 2  # Show modules and classes only, no deeper levels
# The test suite, the system-file folders and the benchmarks are not part of the
# public API; keeping them out leaves a reference to the modules a user calls.
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

# Optional: customize the output for the tree (e.g., you might want to adjust this)
autoapi_add_toctree_entry = True  # Auto add to the table of contents

templates_path = ["_templates"]
exclude_patterns = []

language = "EN"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_static_path = ["_static"]
html_css_files = ["custom.css"]


latex_elements = {
    "preamble": r"\usepackage{amsmath}",  # Add this line to include amsmath
}
html_context = {
    "mathjax_path": "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js",
}
# Ensure UTF-8 encoding is used
source_encoding = "utf-8"
