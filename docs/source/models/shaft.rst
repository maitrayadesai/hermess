.. _models_shaft:

Shafts
======

The shaft strategy is plugged onto a machine with the ``shaft`` keyword, for
example ``shaft = "Shaft4Mass"``. It carries the rotor motion
:math:`\delta, \omega`, exchanging the air-gap power :math:`P_e` with the
electromagnetic model and the mechanical power :math:`p_m` with the governor.

.. hermess-model-table:: shaft

.. figure:: /_static/schematics/shaft_chain.svg
   :alt: Multi-mass shaft
   :width: 620px

   The torsional shaft as a chain of rotor masses coupled by stiffness
   :math:`K_{ij}`; the single-mass default keeps only the GEN mass.

.. autoclass:: hermess.devices.shaft.SingleMass
   :no-index:
.. autoclass:: hermess.devices.shaft.Shaft4Mass
   :no-index:
.. autoclass:: hermess.devices.shaft.Shaft5Mass
   :no-index:
