.. _cli:

Command line
============

The package installs a ``hermess`` command (equivalently ``python -m hermess``):

.. code-block:: bash

   hermess list                             # the systems that ship with the package
   hermess run 3bus --t-end 5               # simulate one and plot the trajectories
   hermess run ieee39_conv --small-signal   # the shipped demo scenario

``hermess run`` plots the bus voltages and the internal states unless
``--no-plot`` is given, and takes ``--t-end``, ``--ts`` and, for systems of
your own, ``--system-root``. Every other simulation setting of
:class:`hermess.config.Config` is reachable with ``--set KEY=VALUE``, for
example ``--set line_dyn=false --set omega_mode=coi``.

The desktop GUI has its own entry point, ``hermess-gui``; see :ref:`gui`.

Reference
---------

The options below are generated from the parser itself, so they always match
the installed version.

.. argparse::
   :module: hermess.__main__
   :func: _build_parser
   :prog: hermess
