.. _user_models:

Using your own models
=====================

A model written outside the package, a device class or one of the pluggable
strategies (AVR, governor, PSS, shaft, and the converter's filter, angle,
voltage, inner and PLL blocks), becomes selectable from a system file once it is
registered. The kind is inferred from the base class, so one call covers
devices and every strategy axis:

.. code-block:: python

   import hermess
   from hermess.devices.inverter_angle import AngleSource

   class VSMAngle(AngleSource):
       """Virtual synchronous machine angle dynamics."""
       ...

   hermess.register(VSMAngle, "VSM")   # now:  angle = "VSM"  in sim_param.txt
   hermess.registered("angle")         # what can be selected today

A registered *device* is addressed by its class name in the first column of the
system file; a registered *strategy* by the name given to
:func:`hermess.register`. Registering the same name twice replaces the earlier
entry, which is convenient while iterating on a model in a notebook, and
:func:`hermess.unregister` removes one again.

The shipped models are documented in :ref:`models`, and the base classes to
derive from live next to them (:class:`~hermess.devices.device.DeviceRect` for
devices, and the abstract strategy classes such as
:class:`~hermess.devices.avr.AVR` or
:class:`~hermess.devices.inverter_angle.AngleSource` for the strategy axes).
