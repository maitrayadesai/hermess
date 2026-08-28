.. _models_avr:

Automatic voltage regulators
============================

The AVR strategy is plugged onto a machine with the ``avr`` keyword, for
example ``avr = "SEXST"``. It reads the terminal voltage and the stabilizing
signal :math:`V_s` of the PSS strategy and produces the field voltage
:math:`E_{fd}`.

.. hermess-model-table:: avr

.. figure:: /_static/schematics/avr_sexst.svg
   :alt: SEXST block diagram
   :width: 380px

   SEXST: first-order static exciter.

.. autoclass:: hermess.devices.avr.SEXST
   :no-index:

.. figure:: /_static/schematics/avr_ieeedc1a.svg
   :alt: IEEE DC1A block diagram
   :width: 480px

   IEEE DC1A: regulator, rotating exciter and stabilizing rate feedback.

.. autoclass:: hermess.devices.avr.IEEEDC1A
   :no-index:

.. figure:: /_static/schematics/avr_st1a.svg
   :alt: ST1A block diagram
   :width: 560px

   IEEE ST1A: transducer, two lead-lags and the regulator lag.

.. autoclass:: hermess.devices.avr.AVRST1A
   :no-index:

.. figure:: /_static/schematics/avr_ac1a.svg
   :alt: AC1A block diagram
   :width: 480px

   IEEE AC1A: regulator, rotating exciter and washout rate feedback.

.. autoclass:: hermess.devices.avr.AVRAC1A
   :no-index:

.. figure:: /_static/schematics/avr_kundur.svg
   :alt: Kundur AVR family block diagram
   :width: 520px

   The Kundur two-area AVR family: transducer, gain and
   transient-gain-reduction lead-lag, in four realizations.

.. autoclass:: hermess.devices.avr.AVRKundur
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_ODE
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_Filter
   :no-index:
.. autoclass:: hermess.devices.avr.AVRKundur_NoTGR
   :no-index:

Two minimal exciters close the family, useful as limiting cases and for
matching references without excitation dynamics. ``AVRCONST`` holds the
field voltage constant at its operating point, and ``AVRSimple`` integrates
the voltage error, :math:`\dot{E}_{fd} = K_v \left( V_{ref} - V_t \right)`.

.. autoclass:: hermess.devices.avr.AVRCONST
   :no-index:
.. autoclass:: hermess.devices.avr.AVRSimple
   :no-index:
