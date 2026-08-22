.. _usage:

Usage
=====

Basic Usage
------------

To run the simulation configured in ``hermess/config.py``, execute the package from the repository root:

.. code-block:: bash

  python -m hermess

Examples
--------

To get a feeling for different examples of the simulator, we prepared some short `./examples <https://github.com/maitrayadesai/hermess/tree/main/examples>`_
to help you get started.

Modifying Configuration
------------------------

To adjust simulation parameters, you can modify the configuration object located in `./config.py` by calling the appropriate method. See :ref:`configuration`
for details. See also the IEEE 39 bus test case modified to include renewable generation in
``examples/renewables/39bus_inv.ipynb``, and all available test cases in :ref:`test_cases`.





Advanced Usage
--------------

Refer to :ref:`advanced_usage` for more details regarding changing the system parameters or simulated disturbances.
