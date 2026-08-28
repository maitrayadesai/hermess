.. _usage:

Running simulations
===================

To run a system from a script or a notebook, without touching ``config.py``:

.. code-block:: python

   import hermess

   hermess.list_systems()                              # what is available
   dae = hermess.simulate("3bus", T_end=5.0)          # run one, get the finished model back
   dae = hermess.simulate("ieee39", line_dyn=False, T_end=10.0, small_signal_analysis=True)

Any field of :class:`~hermess.config.Config` can be passed as a keyword argument
(see :ref:`configuration` for the full list), and ``system_root`` points at a
directory of systems of your own:

.. code-block:: python

   dae = hermess.simulate("my_case", system_root="~/my_systems", T_end=10.0)

Plotting is off by default in :func:`hermess.simulate`, unlike the shipped
configuration, so the call returns quietly and you plot what you want from the
returned object; see :ref:`results`.

Examples
--------

The notebooks in :ref:`examples` each work through one aspect of the
simulator: a first run, scheduled disturbances, the hybrid EMT/RMS network,
small-signal analysis and parametric sensitivities. The systems that ship
with the package are described in :ref:`test_cases`.

Next steps
----------

:ref:`configuration` lists every simulation setting, :ref:`sim_param` describes
the system-file format, :ref:`disturbances` the events that can be scheduled,
and :ref:`results` the analysis outputs.
