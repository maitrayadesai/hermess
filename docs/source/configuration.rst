.. _configuration:

Configuration
=============

.. autoclass:: hermess.config.Config

.. autofunction:: hermess.config.Config.updated()

**Example:**

For every run of the simulator an object of class `Config` needs to be passed. Custom configurations can be created as follows:

.. code-block:: python

    from hermess.config import config
    new_config = config.updated(ts=0.001, T_end=12.0)


