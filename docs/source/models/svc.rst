.. _models_svc:

Static var compensator
======================

.. figure:: /_static/schematics/svc.svg
   :alt: SVC block diagram
   :width: 470px

   The SVC voltage regulator: integrator with reactive droop; the susceptance
   :math:`B` is injected as a shunt at the bus.

.. autoclass:: hermess.devices.svc.SVC
   :no-index:
