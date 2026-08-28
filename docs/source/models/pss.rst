.. _models_pss:

Power system stabilizers
========================

The stabilizer strategy is plugged onto a machine with the ``pss`` keyword,
for example ``pss = "PSSKundur"``. It reads the speed deviation and produces
the stabilizing signal :math:`V_s`, which the AVR sums into its voltage error.

.. hermess-model-table:: pss

.. figure:: /_static/schematics/pss.svg
   :alt: PSS block diagram
   :width: 520px

   Speed-input stabilizer: gain, washout and lead-lag stages.

.. autoclass:: hermess.devices.pss.PSSKundur
   :no-index:
.. autoclass:: hermess.devices.pss.PSSSEA
   :no-index:
