.. _models_converter_controls:

Converter control strategies
============================

The blocks plugged onto a converter, selected by keyword on the converter
line, for example ``filter = "LCL_static"``, ``angle = "Droop"``,
``pll = "SRF_PLL"``. How the five axes fit together is shown in
:ref:`models_converters`.

Output filters (``filter = ...``)
---------------------------------

.. hermess-model-table:: filter

.. figure:: /_static/schematics/lcl.svg
   :alt: LCL filter circuit
   :width: 520px

   The LCL output filter between the switching voltage and the bus.

.. autoclass:: hermess.devices.inverter_filter.LCL
   :no-index:
.. autoclass:: hermess.devices.inverter_filter.LCL_static
   :no-index:

Angle sources (``angle = ...``)
-------------------------------

The angle source fixes how the converter synchronizes. ``Droop`` is the
grid-forming active-power droop, and ``PLL`` adds the same droop on the
PLL frequency for a grid-supporting unit. ``VSM`` is a
virtual-synchronous-machine swing with virtual inertia, damped against the
PLL frequency. ``PLLPowerPI`` is the grid-following choice, which aliases
the converter frame to the PLL frame and turns the active-power error into
the d-axis current command.

.. hermess-model-table:: angle

.. autoclass:: hermess.devices.inverter_angle.DroopAngle
   :no-index:
.. autoclass:: hermess.devices.inverter_angle.PLLAngle
   :no-index:
.. autoclass:: hermess.devices.inverter_angle.VSMAngle
   :no-index:
.. autoclass:: hermess.devices.inverter_angle.PLLPowerPI
   :no-index:

Voltage control (``voltage = ...``)
-----------------------------------

``QVDroop`` turns the reactive-power error into the voltage-magnitude
command of the voltage-mode cascade. ``QPowerPI`` replaces it in the
current-injecting chain and produces the q-axis current command instead.

.. hermess-model-table:: voltage

.. autoclass:: hermess.devices.inverter_voltage.QVDroop
   :no-index:
.. autoclass:: hermess.devices.inverter_voltage.QPowerPI
   :no-index:

Inner control (``inner = ...``)
-------------------------------

``Cascaded`` closes the voltage and current loops of the voltage-mode
cascade, and ``CascadedDamped`` adds capacitor-voltage active damping on
top of it. ``CurrentPI`` is the current-mode loop of the grid-following
chain, tracking the commands of the power PIs directly.

.. hermess-model-table:: inner

.. autoclass:: hermess.devices.inverter_inner.Cascaded
   :no-index:
.. autoclass:: hermess.devices.inverter_inner.CascadedDamped
   :no-index:
.. autoclass:: hermess.devices.inverter_inner.CurrentPI
   :no-index:

Phase-locked loops (``pll = ...``)
----------------------------------

.. hermess-model-table:: pll

.. figure:: /_static/schematics/pll_srf.svg
   :alt: SRF-PLL block diagram
   :width: 520px

   Synchronous-reference-frame PLL: the q-component of the filter voltage is
   driven to zero, locking :math:`\delta_{pll}` to the filter-voltage phasor.

``SRF_PLL`` is the synchronous-reference-frame loop of the figure.
``ReducedPLL`` low-pass filters the measured q-voltage before the loop, and
``Kaura`` filters both axes and acts on the phase angle of the filtered
phasor.

.. autoclass:: hermess.devices.inverter_pll.SRF_PLL
   :no-index:
.. autoclass:: hermess.devices.inverter_pll.ReducedPLL
   :no-index:
.. autoclass:: hermess.devices.inverter_pll.KauraPLL
   :no-index:
