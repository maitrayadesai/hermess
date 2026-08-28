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
