.. _models_governor:

Governors
=========

The turbine-governor strategy is plugged onto a machine with the ``governor``
keyword, for example ``governor = "TGOV1"``. It reads the rotor speed and
produces the mechanical power :math:`p_m` for the shaft.

.. hermess-model-table:: governor

.. figure:: /_static/schematics/gov_tgov1.svg
   :alt: TGOV1 block diagram
   :width: 470px

   TGOV1: droop, servo and reheater lags (``GOVCONST`` holds :math:`p_m`
   constant; ``Droop`` keeps only the droop).

.. autoclass:: hermess.devices.governor.GOVCONST
   :no-index:
.. autoclass:: hermess.devices.governor.Droop
   :no-index:
.. autoclass:: hermess.devices.governor.TGOV1
   :no-index:

.. figure:: /_static/schematics/gov_tgtype2.svg
   :alt: Type II governor block diagram
   :width: 420px

   Type II governor: the frequency deviation acts through the droop and one
   lead-lag, added to the constant reference power.

.. autoclass:: hermess.devices.governor.TGTypeII
   :no-index:
