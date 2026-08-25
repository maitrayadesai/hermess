.. _gui:

Graphical interface
===================

HERMESS ships an optional desktop GUI for interactive work: pick a system,
adjust the simulation settings, run, and inspect the trajectories, the
small-signal modes and the initial power flow without writing a script. It is
aimed at exploratory research use and at teaching; batch work and paper
pipelines are better served by the Python API (:ref:`usage`).

.. image:: _static/gui_timedomain.png
   :width: 100%
   :alt: The HERMESS GUI after a run, showing the time-domain view.

Installation and launch
-----------------------

The GUI dependencies (PySide6, pyqtgraph) are an optional extra, so the core
package stays lightweight:

.. code-block:: bash

   pip install -e ".[gui]"     # or:  uv sync --extra gui

Launch it with either of:

.. code-block:: bash

   hermess-gui
   python -m hermess.gui

The window layout, the opened folders, the selected system and the simulation
options persist across sessions.

Layout
------

The window follows the classic desktop tool arrangement. The **Systems** panel
on the left lists the systems shipped with the package and any folders you
open, with an inspector showing the selected system's devices, lines, bus
initialization and disturbances, parsed read-only from its text files, plus
the raw files themselves. The central area holds four viewer tabs, described
below. The **Log** panel at the bottom receives the simulation log, the
initial power flow and the modal report. The toolbar carries Run (``F5``),
Stop, the options dialog, the CSV export and a selector over the finished
runs of the session (the last ten are kept).

Simulations execute in a separate worker process, so the interface stays
responsive during long runs and Stop cancels cleanly. Progress is reported in
the status bar; with disturbances and ``incl_lim`` off, cancellation takes
effect between disturbance intervals.

Running a simulation
--------------------

Select a system and press Run. The settings behind :func:`hermess.simulate`
are edited in the options dialog (Simulation → Options), which exposes the
fields of :class:`~hermess.config.Config`: end time, time step, integration
scheme and its options, reference-frame mode, dynamic or quasi-static lines,
limiters, and the small-signal analysis switch. Only values you change are
carried as overrides; everything else follows the shipped defaults.

To simulate systems of your own, use *Open folder…* and point it either at a
single system folder (containing ``sim_param.txt`` and optionally
``sim_dist.txt``) or at a directory holding several such folders. The GUI
never edits system files: change them in your editor, press *Reload*, and run
again.

Viewer tabs
-----------

Topology
^^^^^^^^

A one-line diagram of the selected system, available before any run. Buses
are laid out automatically and can be dragged; devices appear as glyphs
attached to their buses (circle for a synchronous machine, square for an
inverter, triangle for a load), and transformer branches are drawn in bronze.
After a run of the same system, every bus is annotated with its initialized
voltage magnitude and angle.

.. image:: _static/gui_topology_ieee39.png
   :width: 100%
   :alt: One-line diagram of the IEEE 39-bus system with converters.

Time domain
^^^^^^^^^^^

The trajectories of the shown run: bus voltage magnitudes, bus injections and
every device's differential states, selected in the tree and overlaid in one
interactive plot (zoom, pan, automatic downsampling for long records).

Small signal
^^^^^^^^^^^^

The modal analysis at the operating point, when ``small_signal_analysis`` is
enabled in the options. The table lists the physical modes (conjugate pairs
collapsed) with frequency and damping ratio, sorted most critical first; the
map shows the eigenvalues with constant-damping guide rays. Selecting a mode,
in the table or by clicking an eigenvalue, highlights it and shows its
normalized participation factors as a bar chart.

.. image:: _static/gui_smallsignal.png
   :width: 100%
   :alt: Small-signal view with the eigenvalue map and participation factors.

Power flow
^^^^^^^^^^

The initial power flow of the shown run as sortable bus and branch tables,
the same data :meth:`~hermess.system.GridSim.power_flow_tables` returns.

Exporting results
-----------------

*File → Export CSV…* writes the signals currently checked in the time-domain
tree as a plot-ready CSV (a ``t`` column plus one named column per signal,
with a header row), together with a ``.provenance.txt`` sidecar recording the
system, the settings, the package version and the date. This is the intended
bridge into a paper's ``data/`` directory. *File → Export figure…* saves the
current tab as a PNG for quick sharing; publication figures should be built
from the exported data instead.
