.. _models_static:

Static Models
=============

Static models are models with no internal states. All static models are to be included in `./data/.../sim_param.txt`. Their corresponding classes
are defined in `./devices/static.py`.

.. _models_static_line:

Transmission line
-----------------

The line is added as follows with the necessary specified parameters:

.. autoclass:: hermess.devices.device.Line




.. figure:: _static/line.png
   :alt: Example PDF Page 1
   :width: 600px

   Figure 1: Transmission line with its parameters.





ZIP Load
--------

.. autoclass:: hermess.devices.static.StaticZIP


Infinite bus
------------



This model implements an infinite bus with a specifiable internal resistance and reactance.
Its voltage is set during the initialization.

.. autoclass:: hermess.devices.static.StaticInfiniteBus
