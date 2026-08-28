.. _models_converters:

Converters
==========

A converter is composed in exactly the same manner as a machine: the
**converter class implements the power path** (the voltage-source converter
behind its LCL output filter), and the control blocks are pluggable
strategies on five axes, the output filter, the angle source, the voltage
control, the inner control and the PLL (see :ref:`models_converter_controls`).
Three converter classes ship, differing in how they synchronize and in which
strategies they plug in by default.
:class:`~hermess.devices.inverter.GridForming` sets its own frequency and
voltage from an active-power droop.
:class:`~hermess.devices.inverter.GridSupporting` rides on a PLL and adds
the droop on the PLL frequency, keeping the full voltage-mode cascade.
:class:`~hermess.devices.inverter.GridFollowing` also rides on a PLL but
replaces that cascade by a current-injecting chain of power-PI and
current-PI controllers.

.. hermess-model-table:: devices:inverter

In the voltage-mode chain of the grid-forming and grid-supporting
converters, the filter strategy carries the plant states
:math:`v_f, i_f, i_t`; the angle source sets the converter frequency
:math:`\omega_c` and angle :math:`\delta_c` (from the active-power droop
for a grid-forming unit, from the PLL for a grid-supporting unit); the
voltage controller turns the reactive-power error into the voltage command
:math:`V_{cd}`; the inner controller closes the cascaded voltage and
current loops and produces the switching voltage :math:`v_{sw}^{*}`; and
the PLL tracks the filter-voltage phasor:

.. figure:: /_static/schematics/conv_structure.svg
   :alt: Converter composition, voltage-mode chain
   :width: 560px

   How a grid-forming or grid-supporting converter is composed: the
   converter class implements the power path; filter, angle source, voltage
   control, inner control and PLL are pluggable strategies selected by
   keyword on the converter line.

In the current-injecting chain of the grid-following converter, the
converter frame is the PLL frame itself. PI controllers on the filtered
active and reactive power occupy the angle and voltage slots and produce
the dq current commands, and a current-mode inner loop tracks them on the
same LCL filter:

.. figure:: /_static/schematics/conv_gfl.svg
   :alt: Converter composition, current-injecting chain
   :width: 560px

   How a grid-following converter is composed: the same power path, with
   the power-PI outers and the current-mode inner loop in the strategy
   slots and the PLL fixing the converter frame.

.. _metaclass_converter:

Converter base class
--------------------

The parent class of all converter models. It introduces the shared parameters
and the initialization procedure, and wires the five pluggable control blocks.

.. autoclass:: hermess.devices.inverter.Inverter
   :members:
   :no-index:

.. _grid_forming_converter:

Grid-forming converter
----------------------

A grid-forming converter, which sets its own frequency and voltage. The
small-signal behavior in low-inertia systems follows [2]_.

.. autoclass:: hermess.devices.inverter.GridForming
   :no-index:

.. _grid_supporting_converter:

Grid-supporting converter
-------------------------

A grid-supporting converter, which synchronizes to the grid through a PLL
and adds the active-power droop on the PLL frequency, keeping the full
voltage-mode cascade [2]_. The class was named ``GridFollowing`` before
v1.1, when that name moved to the current-injecting chain below.

.. autoclass:: hermess.devices.inverter.GridSupporting
   :no-index:

.. _grid_following_converter:

Grid-following converter
------------------------

A grid-following converter in the literature-standard current-injecting
form, matching the PowerSimulationsDynamics.jl reference model and its
PSCAD benchmarks: the frame rides on the PLL, power-PI outers produce the
current commands and a current-mode inner loop tracks them.

.. autoclass:: hermess.devices.inverter.GridFollowing
   :no-index:

References
----------

.. [2] U\. Markovic, O. Stanojev, P. Aristidou, E. Vrettos, D. Callaway, and G. Hug, *Understanding Small-Signal Stability of Low-Inertia Systems*, IEEE Transactions on Power Systems, vol. 36, no. 5, pp. 3997-4017, Sep. 2021, doi: 10.1109/TPWRS.2021.3061434.
