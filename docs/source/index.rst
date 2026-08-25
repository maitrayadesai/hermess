.. HERMESS documentation master file.

HERMESS
=======

*Hybrid EMT/RMS Modern Electric power System Simulator*

`HERMESS` (Python package ``hermess``) is a power system dynamic simulator for
time-domain analysis of electromechanical and electromagnetic transients. It is
designed for nonlinear differential-algebraic equation (DAE) power system models
and integrates them with implicit and explicit schemes built on CasADi.

It models synchronous machines (transient, subtransient, Sauer-Pai and PSS/E
formulations) with pluggable AVR, governor, PSS and multi-mass shaft strategies,
grid-forming and grid-following converters with composable control blocks, static
var compensators, static loads and an infinite bus, and quasi-static or fully
dynamic transmission lines. Faults, line switching and load steps can be applied
at scheduled times, and the operating point can be analyzed with a small-signal
eigenvalue and participation study.

HERMESS is the simulation-only fork of
`PowerDynamicEstimator <https://doi.org/10.5905/ethz-1007-842>`_, from which the
dynamic state estimation layer has been removed.

.. admonition:: Key features
   :class: note

   - **Nonlinear DAE time-domain simulation** — the full nonlinear DAE system, integrated with ``idas``, ``cvodes``, ``collocation`` or ``rk``.
   - **Detailed machine models** — transient, subtransient, Sauer-Pai and PSS/E (``GENROU``, ``GENSAL``) machines, with AVR, governor, PSS and multi-mass shaft strategies.
   - **Converters** — grid-forming and grid-following models composed from filter, angle, voltage, inner-control and PLL blocks.
   - **Hybrid EMT/RMS network** — quasi-static or fully dynamic (electromagnetic) line models, selected per run.
   - **Disturbances** — bus and line faults and their clearing, line opening, and load steps, applied at scheduled times.
   - **Reference-frame modes** — center-of-inertia, single-machine, nominal and distributed.
   - **Small-signal analysis** — eigenvalues, the reduced state matrix and participation factors at the operating point.
   - **Extensible** — user-written devices and control strategies become selectable from a system file through :func:`hermess.register`.
   - **Graphical interface** — an optional desktop GUI (``hermess-gui``) for interactive runs, topology, time-domain, small-signal and power-flow views; see :ref:`gui`.
   - **Benchmarks included** — IEEE 39-bus (with converter variants), Kundur two-area, and the 14-generator South East Australian system.

Getting started
---------------

.. code-block:: bash

   pip install -e .

.. code-block:: python

   import hermess

   hermess.list_systems()                       # the systems that ship with the package
   dae = hermess.simulate("3bus", T_end=5.0)   # run one and get the finished model back

See :ref:`installation` to set up, :ref:`usage` for the everyday entry points and
:ref:`advanced_usage` for the system-file format and the analysis outputs.

.. toctree::
   :maxdepth: 1
   :caption: Contents

   installation
   usage
   gui
   advanced_usage
   configuration
   cases
   models
   models_static
   validation
   license

Background
----------

For the modeling background and the DAE formulation the simulator is built on,
see M. Katanic, J. Lygeros and G. Hug, *Recursive dynamic state estimation for
power systems with an incomplete nonlinear DAE model*, IET Generation,
Transmission & Distribution, 18(22), 3657-3668, 2024,
`doi:10.1049/gtd2.13308 <https://doi.org/10.1049/gtd2.13308>`_.

Citing
------

If you use HERMESS in academic work, please cite the software release together
with the paper above:

   M. A. Desai, M. Katanic and G. Hug, *HERMESS: Hybrid EMT/RMS Modern Electric
   power System Simulator*, version 1.0.0, ETH Zurich Research Collection, 2026,
   `doi:10.3929/ethz-c-000805609 <https://doi.org/10.3929/ethz-c-000805609>`_.

The repository also carries a ``CITATION.cff`` with the same metadata.

Project Structure
-----------------

.. literalinclude:: project_tree.txt
   :language: none
   :encoding: utf-8

Authors and Copyright
---------------------

© 2024-2026 ETH Zurich

Created by: Milos Katanic (original author of ``PowerDynamicEstimator``) and
Maitraya Avadhut Desai (simulation-only fork and maintainer).

The software is released under the GNU General Public License v3.0 or later, see
:ref:`license`.

Contact and Contributing
------------------------

Questions, bug reports and contributions are welcome through the
`issue tracker <https://github.com/maitrayadesai/hermess/issues>`_ and pull
requests; see ``CONTRIBUTING.md`` in the repository. You can also reach the
maintainer, Maitraya Avadhut Desai, at mdesai@ethz.ch.

Indices and Tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
