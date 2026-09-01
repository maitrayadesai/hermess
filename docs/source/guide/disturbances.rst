.. _disturbances:

Disturbances
============

**File:** ``hermess/systems/<case>/sim_dist.txt``

Each line schedules one event:

::

   Disturbance, time = 7.0,  type = "FAULT_LINE", bus_i = "1", bus_j = "2", y = 30
   Disturbance, time = 7.04, type = "OPEN_LINE",  bus_i = "1", bus_j = "2"

The supported types are:

**FAULT_LINE** — a three-phase short circuit in the middle of a line. The
specified admittance is added between ground and the middle of the line by
converting the T model of the line to a PI model.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"FAULT_LINE"``.
- **bus_i** (*str*) – Name of the sending-end bus.
- **bus_j** (*str*) – Name of the receiving-end bus.
- **y** (*float*) – Fault admittance in per unit.

**CLEAR_FAULT_LINE** — removes a short circuit on a line.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"CLEAR_FAULT_LINE"``.
- **bus_i** (*str*) – Name of the sending-end bus.
- **bus_j** (*str*) – Name of the receiving-end bus.

**FAULT_BUS** — a three-phase short circuit at a bus. The specified admittance is
added to the shunt element of that bus.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"FAULT_BUS"``.
- **bus** (*str*) – Name of the affected bus.
- **y** (*float*) – Fault admittance in per unit.

**CLEAR_FAULT_BUS** — removes a short circuit at a bus.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"CLEAR_FAULT_BUS"``.
- **bus** (*str*) – Name of the bus.

**OPEN_LINE** — opens a line. If the line carried a fault, the fault is thereby
neutralized.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"OPEN_LINE"``.
- **bus_i** (*str*) – Name of the sending-end bus.
- **bus_j** (*str*) – Name of the receiving-end bus.

**LOAD** — a load change at a bus. The active and reactive power given are added
to the consumption, in the same units as ``Sb`` (MW and MVAr by default).

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"LOAD"``.
- **bus** (*str*) – Name of the affected bus.
- **p_delta** (*float*) – Active power change in MW.
- **q_delta** (*float*) – Reactive power change in MVAr.

**SETPOINT** — steps a device setpoint (a reference step, the standard control
test signal). The setpoint enters the model equations as a numeric constant,
so the equations are rebuilt at the event; the rebuild discards the extra
current injections of ``LOAD`` events executed earlier in the same run, so
schedule a ``SETPOINT`` before any ``LOAD`` step.

- **time** (*float*) – Time of the disturbance in seconds.
- **type** (*str*) – Must be ``"SETPOINT"``.
- **device** (*str*) – Id of the device whose setpoint is stepped (its ``idx``).
- **param** (*str*) – Name of the setpoint, e.g. ``Pref``.
- **value** (*float*) – New setpoint value, in device per unit.

Every row is validated when the system loads: an unknown type, a misspelled
field or a missing required field stops the run immediately with the list of
fields the type takes, their units and an example row.

The shipped systems in :ref:`test_cases` are worked examples of both files, and
the notebooks in :ref:`examples` walk through them step by step.

.. note::

   Give ``T_end`` at least one time step beyond the last disturbance. A segment
   shorter than one output step has nothing to integrate, and the simulator stops
   at the last disturbance rather than producing an empty result.
