.. _test_cases:

Test Cases
==========


The existing power system test cases are stored in `./hermess/systems <https://github.com/maitrayadesai/hermess/tree/main/hermess/systems>`_
subfolder. The list of current examples includes:

- :ref:`IEEE39_bus`
- :ref:`IEEE39_bus_ideal`
- :ref:`IEEE39_bus_inverter`

.. _IEEE39_bus:

IEEE39_bus
----------

The IEEE39 bus test case is shown in Figure 1. It is simulated in the time domain to study its
electromechanical response to a sequence of disturbances.

Used dynamic models:
    - Subtransient synchronous generators

Simulated disturbances:
    - Short circuit on branch 5-8 (t = 7.00 s)
    - Short circuit cleared by opening the branch on both ends (t = 7.04 s)
    - Load change at node 5 (t = 9.00 s)


.. figure:: _static/39network.png
   :alt: Example PDF Page 1
   :width: 600px

   Figure 1: IEEE_39bus.


.. _IEEE39_bus_ideal:

IEEE39_bus_ideal
----------------

This test case is very similar to the previous one and is intended mainly for functional testing,
to verify that the simulator reproduces the expected response under idealized conditions.

.. _examples_git: https://www.python.org


.. _IEEE39_bus_inverter:

IEEE39_bus_inverter
----------------

This test case represents a renewable-penetrated IEEE 39 bus test case. It comprises three grid-following converters and two grid-forming converters in addition to the synchronous machines.

.. figure:: _static/39network_inv.jpg
   :alt: Example PDF Page 2
   :width: 600px

   Figure 1: IEEE_39bus with grid-forming and grid-following inverters.
