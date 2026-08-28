:layout: landing
:description: HERMESS is a hybrid EMT/RMS power system dynamics simulator built on CasADi.

HERMESS
=======

.. rst-class:: lead

   A hybrid EMT/RMS simulator for power system dynamics. Nonlinear DAE models,
   implicit and explicit integration built on CasADi, and gradients of full
   trajectories with respect to parameters.

.. container:: buttons

   :doc:`Get started <installation>`
   `GitHub <https://github.com/maitrayadesai/hermess>`_
   `PyPI <https://pypi.org/project/hermess/>`_

.. figure:: _static/hero.png
   :alt: Bus voltage magnitudes of the IEEE 39-bus converter system through a fault and its clearing
   :width: 760px
   :align: center

   IEEE 39-bus converter benchmark with dynamic lines: bus voltages through a
   fault and its clearing, electromagnetic transient included.

.. grid:: 1 1 2 3
   :gutter: 2
   :padding: 0
   :class-row: surface

   .. grid-item-card:: :octicon:`pulse` Hybrid EMT/RMS
      :link: models_static
      :link-type: doc

      Quasi-static or fully dynamic (electromagnetic) line models, selected
      per run, in one DAE formulation.

   .. grid-item-card:: :octicon:`sliders` Differentiable
      :link: advanced_usage
      :link-type: doc

      Parametric sensitivities of full trajectories through CasADi, for
      optimization and learning-based control.

   .. grid-item-card:: :octicon:`verified` Cross-validated
      :link: validation
      :link-type: doc

      Benchmarked against ANDES, PSS/E, PowerSimulationsDynamics.jl and
      PSCAD.

   .. grid-item-card:: :octicon:`stack` Model library
      :link: models
      :link-type: doc

      Machines, AVRs, governors, PSS and shafts, and grid-forming,
      grid-supporting and grid-following converters as pluggable strategies.

   .. grid-item-card:: :octicon:`device-desktop` Desktop GUI
      :link: gui
      :link-type: doc

      Topology, time-domain, small-signal and power-flow views with
      ``hermess-gui``.

   .. grid-item-card:: :octicon:`beaker` Test systems
      :link: cases
      :link-type: doc

      IEEE 39-bus with converter variants, Kundur two-area, and the
      14-generator South East Australian system.

In a nutshell
-------------

.. code-block:: bash

   pip install hermess

.. code-block:: python

   import hermess

   hermess.list_systems()                       # the systems that ship with the package
   dae = hermess.simulate("3bus", T_end=5.0)    # run one and get the finished model back

See :ref:`installation` to set up, :ref:`usage` for the everyday entry points
and :ref:`advanced_usage` for the system-file format and the analysis outputs.

.. toctree::
   :maxdepth: 1
   :caption: Getting started
   :hidden:

   installation
   usage

.. toctree::
   :maxdepth: 1
   :caption: User guide
   :hidden:

   advanced_usage
   configuration
   gui

.. toctree::
   :maxdepth: 1
   :caption: Reference
   :hidden:

   models
   models_static
   cases
   validation

.. toctree::
   :maxdepth: 1
   :caption: API reference
   :hidden:

   autoapi/hermess/index

.. toctree::
   :maxdepth: 1
   :caption: Project
   :hidden:

   about
   license
