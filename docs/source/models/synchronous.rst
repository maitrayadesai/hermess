.. _models_synchronous:

Synchronous machines
====================

A synchronous machine is specified with the **electromagnetic model as the
machine class**, and the various controller strategies are plugged onto it.
The electromagnetic model exchanges the air-gap power :math:`P_e` and the
rotor motion :math:`\delta, \omega` with the shaft strategy, reads the field
voltage :math:`E_{fd}` from the AVR strategy (which sums the stabilizing
signal :math:`V_s` of the PSS strategy into its voltage error) and the
mechanical power :math:`p_m` from the governor strategy, and injects its
stator current into the network:

.. figure:: /_static/schematics/sm_composition.svg
   :alt: Synchronous machine composition
   :width: 560px

   How a machine is composed: the machine class implements the
   electromagnetic model; shaft, governor, AVR and PSS are pluggable
   strategies selected by keyword on the machine line.

The shipped machine classes:

.. hermess-model-table:: devices:synchronous

.. _synchronous_generator_transient_model:

Transient (two-axis) model
--------------------------

A two-axis dynamic approximation of a synchronous generator, following [1]_.

.. autoclass:: hermess.devices.synchronous.SynchronousTransient
   :no-index:

.. _synchronous_generator_subtransient_model:

Subtransient model
------------------

A subtransient (Anderson-Fouad) approximation, following [1]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransient
   :no-index:

Sauer-Pai model, with stator dynamics
-------------------------------------

Extends the subtransient model with stator flux dynamics, following [3]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP
   :no-index:

Sauer-Pai model, without stator dynamics
----------------------------------------

The Sauer-Pai formulation with the stator transients neglected, a sixth-order
model [3]_.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP6
   :no-index:

Explicit-DAE variants
---------------------

The same two Sauer-Pai machines with the stator equations kept as algebraic
constraints instead of being eliminated. Useful when the stator algebraic
variables are needed explicitly, for instance together with dynamic line
models.

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP_DAE
   :no-index:

.. autoclass:: hermess.devices.synchronous.SynchronousSubtransientSP6DAE
   :no-index:

PSS/E-style machines
--------------------

Round-rotor and salient-pole machines in the PSS/E parameter convention, used
by the 14-generator South East Australian benchmark.

.. autoclass:: hermess.devices.synchronous.GENROU
   :no-index:

.. autoclass:: hermess.devices.synchronous.GENSAL
   :no-index:

Marconato model
---------------

The Milano/Marconato six-state machine with stator flux dynamics, the
counterpart of the PSID ``MarconatoMachine`` used by the PSCAD-benchmarked
multi-machine case.

.. autoclass:: hermess.devices.synchronous.Marconato
   :no-index:

References
----------

.. [1] Federico Milano, *Power System Modelling and Scripting*, Springer Berlin Heidelberg, 2010, Power Systems series. Available at: https://books.google.ch/books?id=MQu7IqoLrfYC.

.. [3] P\. W. Sauer and M. A. Pai, *Power System Dynamics and Stability*, University of Illinois at Urbana-Champaign, 1998.
