.. _results:

Reading the results
===================

:func:`hermess.simulate` returns the finished
:class:`~hermess.system.DaeSim`, which holds both the symbolic model and the
trajectories:

.. code-block:: python

   dae = hermess.simulate("3bus", T_end=5.0, small_signal_analysis=True)

   dae.time_steps                       # the time grid
   dae.x_full, dae.y_full               # differential and algebraic trajectories
   dae.grid.yf                          # bus voltages
   dae.grid.power_flow_tables(dae)      # initial power flow as two pandas DataFrames

After a run with ``small_signal_analysis=True``:

.. code-block:: python

   dae.A                                # reduced state matrix at the operating point
   dae.eigenvalues                      # its spectrum
   dae.state_names                      # rows and columns of dae.A
   dae.participation_table(mode=1)      # participation factors of the least damped mode
   dae.print_modal_report()             # the same information as a text report
   dae.plot_eigenvalues()               # s-plane scatter

Individual devices keep their own states, so ``device.xf["omega"]`` gives the
trajectory of one state of one device.
