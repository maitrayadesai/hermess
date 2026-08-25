.. _models_static:

Static Models
=============

Static models carry no internal states: they contribute only to the algebraic
network equations. They are declared in the system file
(``hermess/systems/<case>/sim_param.txt``) by class name, and their classes live
in ``hermess/devices/static.py``, except the transmission line, which is part of
``hermess/devices/device.py``.

All loads are initialized by the power flow: the powers given in the system file
are replaced by the values that make the operating point a steady state at
t = 0 s. See :ref:`advanced_usage` for the file format.

.. _models_static_line:

Transmission line
-----------------

Branches are declared with ``Line``. Parameters are in per unit on the system
base, so transformers are represented by the off-nominal tap ratio ``trafo`` of
the branch rather than by a separate model.

.. autoclass:: hermess.devices.device.Line
   :no-index:

ZIP load
--------

The general static load: a combination of constant-impedance, constant-current
and constant-power behavior, set by the shares ``z_share``, ``i_share`` and
``p_share``. This is the load model used by most of the shipped systems.

.. autoclass:: hermess.devices.static.StaticZIP
   :no-index:

Constant-power load
-------------------

A pure constant-power (PQ) load. Equivalent to a ZIP load with ``p_share = 1``,
kept as a separate class for system files that state it explicitly.

.. autoclass:: hermess.devices.static.StaticLoadPower
   :no-index:

.. note::

   A constant-power load has no equilibrium below the nose of the network's PV
   curve. If initialization fails at a heavily loaded bus, give the load some
   impedance share or move the operating point.

Constant-impedance load
-----------------------

A pure constant-impedance load, equivalent to a ZIP load with ``z_share = 1``.

.. autoclass:: hermess.devices.static.StaticLoadImpedance
   :no-index:

Infinite bus
------------

An ideal voltage source behind a specifiable resistance and reactance, with its
voltage set during initialization. Used to terminate a study system, as in the
``SMIB_check`` case.

.. autoclass:: hermess.devices.static.StaticInfiniteBus
   :no-index:
