.. HERMESS documentation master file.

HERMESS
=======

*Hybrid EMT/RMS Modern Electric power System Simulator*

`HERMESS` (Python package ``hermess``) is a power system dynamic simulator for time-domain analysis of
electromechanical transients. It is the simulation-only fork of
`PowerDynamicEstimator <https://doi.org/10.5905/ethz-1007-842>`_ (dynamic state estimation removed). It is designed for nonlinear differential-algebraic equation (DAE)
power system models and integrates them through robust implicit and explicit schemes.

It models synchronous machines (transient, subtransient, and Sauer-Pai formulations) together with
pluggable AVR, governor, PSS, and shaft strategies, grid-forming and grid-following inverters, static
loads, and dynamic or quasi-static transmission lines. Disturbances such as faults, line switching, and
load steps can be applied at user-defined times, and the operating point can additionally be analyzed
with a small-signal eigenvalue/participation study.

.. admonition:: Key features
   :class: note

   - **Nonlinear DAE time-domain simulation** – Integrates the full nonlinear DAE system with implicit and explicit schemes (idas, cvodes, collocation, rk).
   - **Detailed machine models** – Transient, subtransient, and Sauer-Pai synchronous machines with AVR, governor, PSS, and multi-mass shaft strategies.
   - **Renewables included** – Grid-following and grid-forming inverter models included.
   - **Disturbances** – Bus/line faults, line opening, and load steps applied at scheduled times.
   - **Reference-frame modes** – Center-of-inertia, single-machine, nominal, and distributed reference options.
   - **Small-signal analysis** – Optional eigenvalue and participation-factor study at the operating point.
   - **Flexible model handling** – Allows straightforward **dynamic and static model updates** and easy **test configuration changes**.

For technical background on the underlying models, see our `Paper <https://arxiv.org/abs/2305.10065v2>`_.

Refer to the :ref:`installation` section to get started!



.. toctree::
   :maxdepth: 1
   :caption: Contents

   installation
   usage
   advanced_usage
   configuration
   cases
   models
   models_static
   license

Project Structure
=================

.. literalinclude:: project_tree.txt
   :language: none
   :encoding: utf-8

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Authors and Copyright
=====================

© 2024-2026 ETH Zurich

Created by: Milos Katanic (original author of ``PowerDynamicEstimator``) and
Maitraya Avadhut Desai (simulation-only fork and maintainer).

HERMESS is a simulation-only fork of ``PowerDynamicEstimator``
(https://doi.org/10.5905/ethz-1007-842); the dynamic state estimation has been
removed. The software is released under the GNU General Public License v3.0 or
later, see :ref:`license`.

Contact and Contributing
========================

If you have any questions, want to signal an error or contribute to the project,
feel free to reach out to Maitraya Avadhut Desai via email: mdesai@ethz.ch
