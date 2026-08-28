.. _quickstart:

Quickstart
==========

Install the package and run a shipped system:

.. code-block:: bash

   pip install hermess

.. code-block:: python

   import hermess

   hermess.list_systems()                      # the systems that ship with the package
   dae = hermess.simulate("3bus", T_end=5.0)   # run one and get the finished model back

The returned object holds the trajectories, so a first plot is three lines:

.. code-block:: python

   import matplotlib.pyplot as plt
   import numpy as np

   v = dae.grid.yf["1"]                        # bus 1 voltage, rectangular coordinates
   plt.plot(dae.time_steps, np.hypot(v[0], v[1]))
   plt.show()

Any simulation setting can be passed as a keyword argument, for example a
longer horizon, quasi-static lines or a small-signal study at the operating
point:

.. code-block:: python

   dae = hermess.simulate("ieee39", line_dyn=False, T_end=10.0,
                          small_signal_analysis=True)
   dae.print_modal_report()

From here:

- :ref:`usage` introduces the everyday entry points from Python.
- :ref:`cli` covers the same workflow from the command line.
- :ref:`test_cases` describes every shipped system.
- :ref:`sim_param` explains the system files, for cases of your own.
