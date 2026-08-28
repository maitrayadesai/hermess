.. _examples:

Examples
========

Five notebooks, one aspect of the simulator each. They are executed when the
documentation is built, so every output below comes from the installed
version; the sources live in
`examples/ <https://github.com/maitrayadesai/hermess/tree/main/examples>`_
in the repository.

- **Getting started**: run a shipped system, read the power flow, plot the
  trajectories.
- **Disturbances**: the scheduled-event machinery, read off the Kundur
  two-area inter-area oscillation.
- **One system, RMS and EMT**: a machine and a grid-forming converter under
  the quasi-static and the dynamic network model, with the output filter
  swapped to its quasi-static variant.
- **Small-signal analysis**: eigenvalues, modal report and participation
  factors of the IEEE 39-bus system.
- **Parametric sensitivities**: the gradient of a trajectory functional with
  respect to every device parameter, checked against finite differences.

.. nbgallery::

   getting_started
   disturbances
   hybrid_network
   small_signal
   sensitivities
