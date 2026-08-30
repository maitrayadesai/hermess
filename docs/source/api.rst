.. _api:

Public API
==========

The public surface of the package is the handful of names below; everything
else is implementation. The full generated reference for every module is in
:doc:`autoapi/hermess/index`.

Running
-------

.. autofunction:: hermess.simulate
   :no-index:

.. autofunction:: hermess.list_systems
   :no-index:

The returned model is a :class:`~hermess.system.DaeSim`; see :ref:`results`
for the reading guide. ``hermess.SYSTEMS_DIR`` points at the folder of
shipped systems.

Results
-------

``extract_results`` and ``SimulationResults`` are importable from
``hermess`` directly (loaded lazily, so pandas stays off the import path
until used).

.. autofunction:: hermess.results.extract_results
   :no-index:

.. autoclass:: hermess.results.SimulationResults
   :no-index:

.. _api_analysis:

Analysis
--------

Everything in ``hermess.analysis`` (see :ref:`the guide <analysis>`); one
star-import gives a notebook the whole workflow, including
:func:`hermess.simulate` and the model registry.

.. autofunction:: hermess.analysis.signals
   :no-index:
.. autofunction:: hermess.analysis.signal_names
   :no-index:
.. autofunction:: hermess.analysis.get
   :no-index:
.. autofunction:: hermess.analysis.to_dataframe
   :no-index:
.. autofunction:: hermess.analysis.to_csv
   :no-index:
.. autofunction:: hermess.analysis.metrics
   :no-index:
.. autofunction:: hermess.analysis.summary
   :no-index:
.. autofunction:: hermess.analysis.plot
   :no-index:
.. autofunction:: hermess.analysis.plot_states
   :no-index:
.. autofunction:: hermess.analysis.compare
   :no-index:
.. autofunction:: hermess.analysis.plot_frequency
   :no-index:
.. autofunction:: hermess.analysis.plot_voltages
   :no-index:
.. autofunction:: hermess.analysis.plot_active_power
   :no-index:
.. autofunction:: hermess.analysis.plot_modes
   :no-index:
.. autofunction:: hermess.analysis.plot_system
   :no-index:
.. autofunction:: hermess.analysis.mark_events
   :no-index:
.. autofunction:: hermess.analysis.get_device
   :no-index:
.. autofunction:: hermess.analysis.device_label
   :no-index:
.. autofunction:: hermess.analysis.frequency_hz
   :no-index:
.. autofunction:: hermess.analysis.bus_voltage
   :no-index:
.. autofunction:: hermess.analysis.state_index
   :no-index:
.. autofunction:: hermess.analysis.small_signal
   :no-index:
.. autofunction:: hermess.analysis.modal_table
   :no-index:
.. autofunction:: hermess.analysis.participation_table
   :no-index:
.. autofunction:: hermess.analysis.state_matrix
   :no-index:
.. autofunction:: hermess.analysis.power_flow_table
   :no-index:
.. autofunction:: hermess.analysis.copy_system
   :no-index:
.. autofunction:: hermess.analysis.show_system
   :no-index:
.. autofunction:: hermess.analysis.set_param
   :no-index:
.. autofunction:: hermess.analysis.set_disturbances
   :no-index:
.. autofunction:: hermess.analysis.read_events
   :no-index:

User models
-----------

.. autofunction:: hermess.register
   :no-index:

.. autofunction:: hermess.registered
   :no-index:

.. autofunction:: hermess.unregister
   :no-index:

Errors
------

.. autoclass:: hermess.SimulationCancelled
   :no-index:

Interactive help
----------------

.. autofunction:: hermess.help
   :no-index:
