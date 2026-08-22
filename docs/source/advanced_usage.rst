.. _advanced_usage:

Advanced Usage
==============



Simulation Parameters
---------------------

Each test case is fully defined with two files:

- Simulation system parameters `./data/.../sim_param.txt`

- Simulated disturbances `./data/.../sim_dist.txt`

Together these specify the network, the dynamic and static components connected to it, the
initialization data used to solve the initial power flow, and the disturbances applied during the
time-domain simulation.

.. _sim_param:

Simulation parameters
^^^^^^^^^^^^^^^^^^^^^
**File:**  `./data/.../sim_param.txt`

In this file the following information is specified:

.. _grid_param:

1) Grid topology and parameters

Line, bus_i = "name", bus_j = "name", r = [p.u.], x = [p.u.], g = [p.u.], b = [p.u.], trafo = [p.u.]

Here all grid lines are specified. It is assumed that the values are already converted to the relative values, so the resistance, reactance,
susceptance, and conductance are to be specified in p.u. values. Trafos, are therefore, not necessary and here in the trafo field only an off-nominal transformation ration
of the trafo in the given branch should be specified. Ideally, this value is close to 1.0. See :ref:`models_static_line` for more details.

.. _dyn_param:

2) Dynamic models

SynchronousSubtransient, idx =  "index", bus = "name", Sn = [MW], ...

Here, the data of the employed dynamic models are defined. Some values re mandatory, such as the bus the model is connected to.
Other values can be omitted and the code will run with default values specified in the corresponding python class.
See :ref:`models` for details on available dynamic models.

.. _static_param:

3) Static models

StaticLoadPower, bus = "bus"

It is mandatory to define the nus at which the load is connected. P and Q can be specified but they will be overwritten once the
initialization is executed and replaced by values that guarantee steady state at t = 0 [s]. For details about available static models,
refer to :ref:`models_static`.

4) Initialization data

The simulation is initialized by running a power flow. The values
used for running the power flow are given in `./data/.../sim_param.txt` with the following keyword:

**Python name**

*BusInit*

Each and every bus is separately specified. There can only be one slack node.

- **BusInit**: A transmission bus to be included.

    **Parameters:**

    - **bus** (*str*) – Name of the bus.
    - **p** (*float*) – Injected active power in [MW]. Positive corresponds to consumption.
    - **q** (*float*) – Injected reactive power in [MVar]. Positive corresponds to consumption.
    - **v** (*float*) – Bus voltage magnitude in [p.u.]
    - **type** (*custom*) – "PQ", "PV", or "slack".

It needs to be specified as follows:

BusInit, bus = "name", v = [p.u.],	p = [MW],	q = [MW],	type ="type"

The bus name should be specified as a string. Supported types are = {"PQ", "PV", "slack"}.
Active and reactive power are given in absolute values. The specified voltage is given in relative values.


Simulation Disturbances
-----------------------

Simulation disturbances are specified in the `./data/.../sim_dist.txt` file. Currently, the package supports the following disturbances:

- **FAULT_LINE**: A 3-phase short circuit in the middle of a transmission line. The specified admittance (real value) will be added between the ground and the middle of the line
by converting the "T" to "PI" model of the line.

    **Parameters:**

    - **time** (*float*) – Time of disturbance in seconds.
    - **type** (*str*) – Must be ``"FAULT_LINE"``.
    - **bus_i** (*str*) – Name of the sending-end bus.
    - **bus_j** (*str*) – Name of the receiving-end bus.
    - **y** (*float*) – Fault admittance in per-unit.


- **FAULT_BUS:** A 3-phase short circuit at a specified bus. The specified admittance (real value) will be added to the shunt element of the node.

    **Parameters:**

    - **time** (*float*) – Time of disturbance in seconds.
    - **type** (*str*) – Must be ``"FAULT_BUS"``.
    - **bus** (*str*) – Name of the affected bus.
    - **y** (*float*) – Fault admittance in per-unit.



- **LOAD:** Load power change at the specified bus. The specified active and reactive power in absolut values will be added to the consumption. It should be specified in the
same units as Sb (default MW and MVAr).

    **Parameters:**

    - **time** (*float*) – Time of disturbance in seconds.
    - **type** (*str*) – Must be ``"LOAD"``.
    - **bus** (*str*) – Name of the affected bus.
    - **p_delta** (*float*) – Active power change in MW.
    - **q_delta** (*float*) – Reactive power change in MVAr.

- **CLEAR_FAULT_LINE**: Removing the short circuit on the line.

    **Parameters:**

    - **time** (*float*) – Time of disturbance in seconds.
    - **type** (*str*) – Must be ``"CLEAR_FAULT_LINE"``.
    - **bus_i** (*str*) – Name of the sending-end bus.
    - **bus_j** (*str*) – Name of the receiving-end bus.


- **CLEAR_FAULT_BUS**: Removing the short circuit at the bus.

    **Parameters:**

    - **time** (*float*) – Time of disturbance in seconds.
    - **type** (*str*) – Must be ``"CLEAR_FAULT_BUS"``.
    - **bus** (*str*) – Name of the bus.



- **OPEN_LINE**: Opening the line. If the line had a fault, the fault will be effectively neutralized.
    **Parameters:**

    - **time** (*float*) – Time of disturbance in seconds.
    - **type** (*str*) – Must be ``"OPEN_LINE"``.
    - **bus_i** (*str*) – Name of the sending-end bus.
    - **bus_j** (*str*) – Name of the receiving-end bus.


Refer to the working :ref:`examples` for more details.



Limitations
-----------

- Only one injector is allowed per power system node. The reason is the initialization ambiguity. Now, the initialization will overwrite all production and conumption values
to start at a steady-state. If you need another component at the same node, create another node with minimal admittance connected to the desired node.
