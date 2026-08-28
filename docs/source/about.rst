.. _about:

About
=====

Overview
--------

`HERMESS` (Python package ``hermess``) is a power system dynamic simulator for
time-domain analysis of electromechanical and electromagnetic transients. It is
designed for nonlinear differential-algebraic equation (DAE) power system models
and integrates them with implicit and explicit schemes built on CasADi.

It models synchronous machines (transient, subtransient, Sauer-Pai and PSS/E
formulations) with pluggable AVR, governor, PSS and multi-mass shaft strategies,
grid-forming, grid-supporting and grid-following converters with composable control blocks, static
var compensators, static loads and an infinite bus, and quasi-static or fully
dynamic transmission lines. Faults, line switching and load steps can be applied
at scheduled times, and the operating point can be analyzed with a small-signal
eigenvalue and participation study.

HERMESS is the simulation-only fork of
`PowerDynamicEstimator <https://doi.org/10.5905/ethz-1007-842>`_, from which the
dynamic state estimation layer has been removed.

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
