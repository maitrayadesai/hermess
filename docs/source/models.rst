.. _models:

Dynamic Models
==============

Below is the list of all dynamic models used in the system. The corresponding classes are located in the `./devices` directory.
The following documentation describes the mathematical equations and the python implementation. Detailed instructions on how to create user-defined models aro not yet available.

Metaclass
---------
All devices are derived from

.. autoclass:: hermess.devices.device.DeviceRect

The method for generating the differential and algebraic equations in each model is:

.. autofunction:: hermess.devices.device.DeviceRect.fgcall()

---


.. _synchronous_generator_transient_model:

Synchronous Generator Transient Model
-------------------------------------

The **Synchronous Generator Transient Model** provides a **two-axis dynamic approximation** of a synchronous generator. It is based on the formulation provided in [1]_.

Python Implementation
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.synchronous.SynchronousTransient



.. _synchronous_generator_subtransient_model:

Synchronous Generator Subtransient Model
----------------------------------------

The **Synchronous Generator Subransient Model** provides a **dynamic approximation** of a synchronous generator based on Anderson-Fauad's model. It is based on the formulation provided in [1]_.

Python Implementation
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransient


Synchronous Generator Subtransient Model (with Stator Dynamics)
---------------------------------------------------------------

The **Synchronous Generator Subtransient Model with Stator Dynamics** provides a **dynamic approximation** of a synchronous generator, including stator dynamics, based on the formulation by Sauer and Pai. It extends the standard subtransient model by incorporating additional stator field dynamics, as described in [3]_.

Python Implementation
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP


Synchronous Generator Subtransient Model (without Stator Dynamics)
---------------------------------------------------------------

The **Synchronous Generator Subtransient Model without Stator Dynamics** provides a **dynamic approximation** of a synchronous generator, based on the formulation by Sauer and Pai.
The stator dynamics are neglected making the model 6th order [3]_.

Python Implementation
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP6



.. _metaclass_converter:

Converter Metaclass
-------------------
This is the parent class for all inverter models. It introduces all necessary parameters and also stores the model initialization details with a custom script.


.. autoclass:: hermess.devices.inverter.Inverter
  :members:



.. _grid_following_converter:

Grid-Following Converter
------------------------

The **Grid-Following Converter Model** provides a **dynamic representation** of a grid-following inverter. It captures the small-signal stability behavior in low-inertia power systems, as described in [2]_.

Python Implementation
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.inverter.GridFollowing





.. _grid_forming_converter:

Grid-Forming Converter
----------------------

The **Grid-Forming Converter Model** provides a **dynamic representation** of a grid-forming inverter. It captures the small-signal stability behavior in low-inertia power systems, as described in [2]_.

Python Implementation
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: hermess.devices.inverter.GridForming





References
----------


.. [1] Federico Milano, *Power System Modelling and Scripting*, Springer Berlin Heidelberg, 2010, Power Systems series. Available at: https://books.google.ch/books?id=MQu7IqoLrfYC.


.. [2] U. Markovic, O. Stanojev, P. Aristidou, E. Vrettos, D. Callaway, and G. Hug, *Understanding Small-Signal Stability of Low-Inertia Systems*, IEEE Transactions on Power Systems, vol. 36, no. 5, pp. 3997–4017, Sep. 2021, doi: 10.1109/TPWRS.2021.3061434.


.. [3] P. W. Sauer and M. A. Pai, *Power System Dynamics and Stability*, The University of Illinois at Urbana-Champaign, 1406 W. Green St., Urbana, IL 61801.

