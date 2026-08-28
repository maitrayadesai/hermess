.. _models:

Model library
=============

Everything dynamic in HERMESS is implemented in a **pluggable-strategy**
manner. A device class implements the physical core of a component and is
selected in a system file by its class name in the first column: for a
synchronous machine that core is the electromagnetic model, for a converter it
is the power path through the output filter. The controllers are separate
*strategy* objects plugged onto that core and chosen by keyword on the same
line of the system file::

   SynchronousSubtransientSP, idx = "SG1", bus = "1", Sn = 300, avr = "SEXST", governor = "TGOV1", ...
   GridForming, idx = "GFM1", bus = "3", Sn = 100, filter = "LCL_static", ...

Machines take an automatic voltage regulator, a governor, a power system
stabilizer and a shaft; converters take an output filter, an angle source, a
voltage controller, an inner controller and a PLL. Every combination composes,
the names accepted at any moment (shipped and user-registered together) are
returned by :func:`hermess.registered`, and a model of your own becomes
selectable once registered with :func:`hermess.register` (see
:ref:`user_models`).

The pages of this section describe what each model represents; the parameters
and defaults of every class are listed in the class documentation itself, which
is generated from the source, so it always matches the installed version. Each
class documents its equations exactly as implemented and a table mapping the
code parameter names to the mathematical symbols used in those equations. The
availability tables on each page are generated from the same registries the
simulator reads, so they always list what the installed version accepts.

.. toctree::
   :maxdepth: 1

   synchronous
   avr
   governor
   pss
   shaft
   converters
   converter_controls
   svc
   network

Base class
----------

All devices derive from ``Element``; devices that inject current into the
network in rectangular coordinates derive from ``DeviceRect``.

.. autoclass:: hermess.devices.device.DeviceRect
   :no-index:

The method that builds the differential and algebraic equations of a model is:

.. autofunction:: hermess.devices.device.DeviceRect.fgcall()
   :no-index:
