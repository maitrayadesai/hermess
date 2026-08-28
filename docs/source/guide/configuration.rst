.. _configuration:

Configuration
=============

Every run is controlled by a :class:`~hermess.config.Config` object. The
everyday way to set its fields is through keyword arguments of
:func:`hermess.simulate`, which accepts any field listed below:

.. code-block:: python

   dae = hermess.simulate("ieee39", ts=0.001, T_end=12.0, line_dyn=False)

For repeated runs, or to work with the shipped default scenario, build a
configuration object explicitly and derive variants from it:

.. code-block:: python

   from hermess.config import config          # the shipped default scenario

   new_config = config.updated(ts=0.001, T_end=12.0)

The fields, with their types and defaults:

.. autoclass:: hermess.config.Config
   :no-index:

.. autofunction:: hermess.config.Config.updated()
   :no-index:
