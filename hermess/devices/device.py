# © 2024-2026 ETH Zurich
# Original author: Milos Katanic
# Simulation-only fork & maintainer: Maitraya Avadhut Desai
#
# Licensed under the GNU General Public License v3.0 or later;
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     https://www.gnu.org/licenses/gpl-3.0.en.html
#
# This software is distributed "AS IS", WITHOUT WARRANTY OF ANY KIND,
# express or implied. See the License for specific language governing
# permissions and limitations under the License.
#
# Simulation-only fork of PowerDynamicEstimator
# (https://doi.org/10.5905/ethz-1007-842); dynamic state estimation removed.
# For inquiries, contact: mdesai@ethz.ch

from __future__ import annotations  # Postponed type evaluation
from typing import TYPE_CHECKING, Union, Any, Optional

if TYPE_CHECKING:
    from hermess.system import Dae, Grid, DaeSim, GridSim
import casadi as ca
import numpy as np
import scipy.sparse
import scipy.sparse.linalg
import logging

np.random.seed(30)
sin = np.sin
cos = np.cos
sqrt = np.sqrt


class Element:
    """Metaclass to be used for all elements to be added"""

    def __init__(self) -> None:
        self.n: int = 0  # number of devices
        self.u: list[bool] = []  # device status
        self.name: list[str] = []  # name of the device
        self._type: Optional[str] = None  # Device type
        self._name: Optional[str] = None  # Device name
        self.int: dict[
            str, Union[str, int]
        ] = (
            {}
        )  # Dictionary of unique identifiers for each device based on the variable "idx"
        self._data: dict[str, Any] = {"u": True}  # Default entries for lists
        self._params: dict[str, float] = {}  # Default entries for np.arrays params
        self._setpoints: dict[
            str, float
        ] = {}  # Default entries for np.arrays set points
        self._descr: dict[str, str] = {}  # Parameter and data explanation
        self._mand: list[str] = []  # mandatory attributes
        self.properties: dict[str, bool] = {
            "gcall": False,
            "fcall": False,
            "xinit": False,
            "fgcall": False,
            "call": False,
            "xy_index": False,
            "finit": False,
            "save_data": False,
            "fplot": False,
        }

    def add(
        self, idx: Optional[str] = None, name: Optional[str] = None, **kwargs
    ) -> None:
        """
        Add an element device

        Args:
        idx (str, optional): Unique identifier for the device. Generated if not provided.
        name (str, optional): Name of the device. Generated if not provided.
        **kwargs: Custom parameters to overwrite defaults.
        """
        # Generate unique identifiers if not provided
        idx = idx or f"{self._type}_{self.n + 1}"
        name = name or f"{self._name}_{self.n + 1}"

        self.int[idx] = self.n
        self.name.append(name)

        # check whether mandatory parameters have been set up

        for key in self._mand:
            if key not in kwargs:
                raise Exception("Mandatory parameter <%s> has not been set up" % key)
        self.n += 1
        # Set default values
        for key, default in {**self._params, **self._setpoints}.items():
            if key not in self.__dict__:
                logging.warning(
                    f"Attribute {key} not found in element - initializing as an empty array."
                )
                self.__dict__[key] = np.array([], dtype=type(default))
            self.__dict__[key] = np.append(self.__dict__[key], default)

        for key, default in self._data.items():
            if key not in self.__dict__:
                logging.warning(
                    f"Attribute {key} not found in element - initializing as an empty list."
                )
                self.__dict__[key] = []
            self.__dict__[key].append(default)

        # Overwrite custom values

        for key, value in kwargs.items():

            if key not in self.__dict__:
                logging.info(
                    "Element %s does not have parameter %s - ignoring"
                    % (self._name, key)
                )
                continue
            try:
                self.__dict__[key][-1] = value  # Attempt to update the last element
            except IndexError:
                raise IndexError(
                    f"Parameter/setpoint '{key}' not properly specified in the model definition. Check if it's properly listed and initialized when defining the class"
                )

        logging.info(f"Element {name} (ID: {idx}) added successfully.")


class BusInit(Element):
    def __init__(self) -> None:
        super().__init__()
        self._type = "Bus_init_or_unknwon"  # Element type
        self._name = "Bus_init_or_unknown"  # Element name
        self._data.update({"bus": None, "p": 0, "q": 0, "v": 1.0, "type": None})
        self.bus: list[Optional[str]] = []
        self.p: list[float] = []
        self.q: list[float] = []
        self.v: list[float] = []
        self.type: list[Optional[str]] = []


class Disturbance(Element):
    def __init__(self) -> None:
        super().__init__()
        self._type = "Disturbance"  # Element type
        self._name = "Disturbance"  # Element name
        # Default parameter values
        self._params.update(
            {
                "bus_i": None,
                "bus_j": None,
                "time": None,
                "type": None,
                "y": 10,
                "bus": None,
                "p_delta": 0,
                "q_delta": 0,
            }
        )

        self.type = np.array([], dtype=str)
        self.time = np.array([], dtype=float)
        self.bus_i = np.array([], dtype=str)
        self.bus_j = np.array([], dtype=str)
        self.y: np.ndarray = np.array([], dtype=float)
        self.bus = np.array([], dtype=str)
        self.p_delta = np.array([], dtype=float)
        self.q_delta = np.array([], dtype=float)

    def sort_chrono(self):
        sorted_indices = np.argsort(self.time)

        for key in self._params:
            setattr(self, key, getattr(self, key)[sorted_indices])


class Line(Element):
    r"""
    Parameters
    ----------
    r : ndarray[float]
        Series resistance value in per unit (p.u.).
    x : ndarray[float]
        Series reactance value in per unit (p.u.).
    g : ndarray[float]
        Total shunt conductance value in per unit (p.u.).
    b : ndarray[float]
        Total shunt susceptance value in per unit (p.u.).
    trafo : ndarray[float]
        Off-nominal line transformer ratio.
    bus_i : ndarray[str]
        Name of the sending-end bus.
    bus_j : ndarray[str]
        Name of the receiving-end bus.
    """

    def __init__(self) -> None:
        super().__init__()

        self._type = "Transmission_line"  # Element type
        self._name = "Transmission_line"  # Element name
        self._params.update(
            {
                "r": 0.001,
                "x": 0.001,
                "g": 0,
                "b": 0,
                "bus_i": None,
                "bus_j": None,
                "trafo": 1,
            }
        )
        self.states = ["i_ijr", "i_iji"]
        self.r = np.array([], dtype=float)
        self.x = np.array([], dtype=float)
        self.g = np.array([], dtype=float)
        self.b = np.array([], dtype=float)
        self.trafo = np.array([], dtype=float)
        self.bus_i = np.array([], dtype=object)
        self.bus_j = np.array([], dtype=object)

    def fcall(self, grid: GridSim, dae: DaeSim) -> None:
        r"""Call all differential equations for all lines. This function should be used
        only in case lines are modeled dynamically. If they are modeled statically they
        are automatically incorporated within grid class"""

        # TODO create separate multiplication factors for re and im because of phase shifters
        self.i_ijr = [i for i in range(2 * grid.nb) if i % 2 == 0]
        self.i_iji = [i for i in range(2 * grid.nb) if i % 2 != 0]

        omega_b = [2 * np.pi * dae.fn] * self.n

        # Update Reference Frequencies
        omega_ref_vec = (
            ca.SX.ones(self.n, 1) * dae.omega_net
        )  # initialization and fallback

        # Set reference frequency
        if getattr(dae, "omega_ref_lines", None) is not None:
            # Vector of reference frequencies at all lines
            omega_ref_vec = dae.omega_ref_lines

        # Transform nodal voltages into the line's reference frame so that all
        # quantities in each equation share one frame.
        Vi_re, Vi_im, Vj_re, Vj_im = grid.build_voltage_transformed_to_line_frame(dae)

        # d i_ijr / dt
        dae.fl[self.i_ijr] = (omega_b / (self.x * 1)) * (
            ((Vi_re / self.trafo) - Vj_re) - ((self.r * 1) * dae.xl[self.i_ijr])
        ) + omega_b * omega_ref_vec * dae.xl[self.i_iji]

        # d i_iji / dt
        dae.fl[self.i_iji] = (omega_b / (self.x * 1)) * (
            ((Vi_im / self.trafo) - Vj_im) - ((self.r * 1) * dae.xl[self.i_iji])
        ) - omega_b * omega_ref_vec * dae.xl[self.i_ijr]

        # Apply line switches: sl=0 deactivates opened lines (derivative → 0)
        dae.fl[self.i_ijr] *= dae.sl[self.i_ijr]
        dae.fl[self.i_iji] *= dae.sl[self.i_iji]

        # TODO add the rotation of current through phase shifts
        # Accumulate branch currents into the nodal current balance, transformed
        # into the bus frame. Handles multiple lines incident to one bus without
        # index-overwrite issues. The returned vector spans the 2*nn bus-voltage
        # block; device-private algebraics occupy dae.g[2*nn:] and are untouched.
        nv = 2 * grid.nn
        dae.g[:nv] += grid.build_linecurrents_transformed_to_bus_frame(dae)


class DeviceRect(Element):
    """
    Dynamic or static device modeled in rectangular coordinates. Used as a parent class
    for all devices modeled in rectangular coordinates.

    Attributes:
        properties (dict[str, bool]): Flags for method calls (e.g., 'gcall', 'fcall').
        xf (dict[str, np.ndarray]): Final state results for the simulation.
        xinit (dict[State, list[float]]): Initial state values for all devices of the instance.
        xmin (list[float]): Minimum limited state value.
        xmax (list[float]): Maximum limited state value.
        _params (dict[str, float]): Device parameters, such as rated voltage, power, and frequency and internal parameters.
        _data (dict[str, str]): Additional data which will be used in a list, one entry for each device of this object instance.
        bus (list[Optional[str]]): Buses where the device is connected. Each device has an entry in the list.
        states (list[States]): State variables.
        units (list[States]): Units of state variables.
        ns (float): Total number of states in the model.
        vre (list[float]): Order of the real voltage value for each device in the overall DAE model.
        vim (list[float]): Order of the real voltage value for each device in the overall DAE model.
        _algebs (list[str]): Algebraic variables ('vre', 'vim').
        _descr (dict[str, str]): Descriptions for key parameters.
    """

    #: Default initialization method for this device class. ``"joint"`` -> the
    #: one-shot Newton+LM solve in :meth:`_finit_joint` (e.g. the synchronous
    #: machine); ``"sequential"`` -> a staged init in :meth:`_finit_sequential`
    #: (e.g. the inverter).
    _init_method: str = "joint"

    def __init__(self) -> None:

        super().__init__()

        self.xf: dict[str, np.ndarray] = {}  # final state results or sim/est
        self.yf_int: dict[str, np.ndarray] = {}  # private algebraic trajectories
        self.xinit: dict[str, list[float]] = {}
        self.xmin: list[float] = []
        self.xmax: list[float] = []

        self._params.update({"Vn": 220, "fn": 50.0, "Sn": 100})
        self.Vn = np.array([], dtype=float)
        self.fn = np.array([], dtype=float)
        self.Sn = np.array([], dtype=float)

        self._data.update({"bus": None})
        self.bus: list[Optional[str]] = []  # at which bus

        self.states: list[str] = []  # list of state variables
        self.units: list[str] = []  # List of states' units
        self.ns: int = 0  # number of states
        self._algebs: list[str] = ["vre", "vim"]  # list of algebraic variables
        self.vre = np.array([], dtype=float)
        self.vim = np.array([], dtype=float)

        # Device-private (internal) algebraic variables. Unlike the shared,
        # grid-mapped node voltages vre/vim, each private algebraic is owned by
        # this device, gets a fresh dae.y/dae.g slot in xy_index, and is defined
        # by its own equation 0 = g written in fgcall. Used for device-local
        # algebraic constraints that cannot be symbolically eliminated.
        self._algebs_int: list[str] = []  # ordered names of private algebraics
        self._algebs_int_x0: dict[str, float] = {}  # init guess (Newton guess in finit)
        self._algebs_int_units: dict[str, str] = {}  # units, for labels/plotting

        self._x0: dict[
            str, float
        ] = (
            {}
        )  # default initial states, will be used as initial guess for the simulation initialization
        self._mand.extend(["bus"])
        self._descr = {
            "Sn": "rated power",
            "Vn": "rated voltage",
            "u": "connection status",
            "fn": "nominal frequency",
        }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Merge class-level _descrs if subclass adds its own
        full_descr = dict(getattr(cls, "_descr", {}))
        for base in cls.__bases__:
            full_descr.update(getattr(base, "_descr", {}))

        # Format as docstring section
        doc_lines = ["\nAttributes", "----------"]
        for key, val in full_descr.items():
            doc_lines.append(f"{key} : np.ndarray")
            doc_lines.append(f"    {val}")

        # Inject into class docstring
        cls.__doc__ = (cls.__doc__ or "") + "\n" + "\n".join(doc_lines)

    def _init_data(self) -> None:

        self.xinit = {state: [] for state in self.states}

    def xy_index(self, dae: Dae, grid: Grid) -> None:
        """Initializes indices for states, algebraic variables, unknown inputs, and switches.

        Args:
            dae (Dae): Object managing differential-algebraic equations.
            grid (Grid): Object managing the electrical grid and node indices.
        """

        zeros = [0] * self.n
        for item in self.states:
            self.__dict__[item] = zeros[:]
        for item in self._algebs:
            self.__dict__[item] = zeros[:]
        for item in self._algebs_int:
            self.__dict__[item] = zeros[:]

        for var in range(self.n):

            for item in self.states:
                self.__dict__[item][var] = dae.nx
                # Init with current state init value
                dae.xinit.append(self.xinit[item][var])
                # Add the corresponding state to the DAE
                dae.states.append(f"{self._name}_at_{self.bus[var]}_{item}")
                dae.nx += 1
                # Retrieve min and max state limits
                item_min = getattr(self, item + "_min", None)
                item_max = getattr(self, item + "_max", None)
                self.xmin.append(item_min[var] if item_min is not None else -np.inf)
                self.xmax.append(item_max[var] if item_max is not None else np.inf)
                dae.xmin.append(item_min[var] if item_min is not None else -np.inf)
                dae.xmax.append(item_max[var] if item_max is not None else np.inf)
        if self.n:
            # assign indices to real and imaginary voltage algebraic variables; first real value
            self.__dict__["vre"] = grid.get_node_index(self.bus)[1]
            self.__dict__["vim"] = grid.get_node_index(self.bus)[2]

        # Device-private algebraic variables: append fresh slots after the 2*nn
        # voltage block. grid.nn is final here, so the global index is
        # grid.nn*2 + dae.n_priv (a running counter across all devices). The
        # symbolic dae.y/dae.g vectors are sized to 2*nn + dae.n_priv later, in
        # Grid.init_symbolic (which runs after every device's xy_index).
        if self._algebs_int:
            base = grid.nn * 2
            for var in range(self.n):
                for item in self._algebs_int:
                    self.__dict__[item][var] = base + dae.n_priv
                    dae.algebs_int_names.append(
                        f"{self._name}_at_{self.bus[var]}_{item}"
                    )
                    dae.yinit_priv.append(self._algebs_int_x0.get(item, 0.0))
                    dae.n_priv += 1

    def add(self, idx=None, name=None, **kwargs) -> None:

        super().add(idx, name, **kwargs)

        # initialize initial states with some default values
        for item in self.states:
            self.xinit[item].append(self._x0[item])

    def save_data(self, dae: Dae) -> None:

        for item in self.states:
            self.xf[item] = np.zeros([self.n, dae.nts])
            self.xf[item][:, :] = dae.x_full[self.__dict__[item][:], :]

        # Persist device-private algebraic trajectories (from dae.y_full)
        # alongside the state trajectories.
        for item in self._algebs_int:
            self.yf_int[item] = dae.y_full[self.__dict__[item][:], :]

    def finit_anchor_residuals(self, dae: Dae) -> list:
        """Extra steady-state anchor residuals (each an n-vector that must equal 0)
        a device declares to keep its initialization Newton system square.

        The joint init pins each device's state ODEs (``f = 0``) plus two
        quantities through the bus-current balance (``g[vre]``/``g[vim]``), so a
        square system requires ``n_setpoints == 2`` (the SG: Pref + Vref). A
        device with more setpoints returns ``n_setpoints - 2`` anchor residuals
        to balance them. Empty by default.

        Example: the inverter has 3 setpoints (Pref/Qref/Vref) but the bus
        equations pin only 2; it returns one anchor (Qref = Qc) here.
        """
        return []

    def finit(self, dae: Dae) -> None:
        """Initialize the device, dispatching on :attr:`_init_method`
        (``"joint"`` -> :meth:`_finit_joint`,
        ``"sequential"`` -> :meth:`_finit_sequential`)."""
        if self._init_method == "sequential":
            self._finit_sequential(dae)
        elif self._init_method == "joint":
            self._finit_joint(dae)
        else:
            raise ValueError(
                f"Unknown _init_method {self._init_method!r} on {self._name}; "
                "expected 'joint' or 'sequential'."
            )

    def _finit_sequential(self, dae: Dae) -> None:
        """Staged, device-specific initialization. Devices that declare
        ``_init_method = 'sequential'`` implement this; the default has none."""
        raise NotImplementedError(
            f"{self._name} declares _init_method='sequential' but provides no "
            "_finit_sequential."
        )

    def finit_guess(self, dae: Dae):
        """Newton seed for the joint init, machine-major
        ``[states of inst 0 | states of inst 1 | ...]``, or None for the
        default (class-level ``_x0`` repeated per instance). Overrides may
        also refresh setpoint arrays (e.g. ``Pref``), which the joint solve
        consumes as setpoint guesses."""
        return None

    def _finit_joint(self, dae: Dae) -> None:
        """One-shot initialization: solve the device's steady state (states +
        setpoints + private algebraics, balanced by the bus equations and any
        device-declared anchor residuals) as a single Newton system, with a
        Levenberg-Marquardt fallback.

        Initialize the device by setting up setpoints, initial states based on the power flow solution.
        Args:
            dae (Dae): The DAE object used to simulate the system.
        """
        # Per-instance Newton seeds. The default guess repeats the class-level
        # _x0 for every instance; a device class may override finit_guess() to
        # compute operating-point-aware seeds (and refresh its setpoint arrays,
        # consumed as guesses just below). Operating-point-aware seeds keep
        # machines at large-angle buses off the mirror (saddle) equilibrium of
        # the machine equations.
        guess_x0 = self.finit_guess(dae)

        u = ca.SX.sym("", 0)
        u0 = []
        for item in self._setpoints:
            # Set the initial guess for the setpoint
            u0.append(self.__dict__[item])

            # Reset it to be a variable
            self.__dict__[item] = ca.SX.sym(item, self.n)
            # Stack the variable to a single vector
            u = ca.vertcat(u, self.__dict__[item])
        u0 = [item for sublist in u0 for item in sublist]  # flatten it

        # Now subtract the initial network currents from algebraic equations
        for alg in self._algebs:
            dae.g[self.__dict__[alg]] += dae.iinit[self.__dict__[alg]]

        # Fix algebraic variables to their init values, except this device's own
        # private algebraics, which stay symbolic so finit solves for their
        # consistent values together with the states. Build a mixed dae.y:
        # numeric voltages, symbolic privates. priv_global_idx / priv_syms /
        # priv_guess are item-major, instance-minor so the solution tail unpacks
        # in the same order below.
        priv_syms: list = []
        priv_global_idx: list = []
        priv_guess: list = []
        if self._algebs_int:
            y_mixed = ca.SX(dae.yinit)  # numeric voltages as SX constants
            for item in self._algebs_int:
                sym = ca.SX.sym(item, self.n)
                for var in range(self.n):
                    gidx = self.__dict__[item][var]
                    y_mixed[gidx] = sym[var]
                    priv_global_idx.append(gidx)
                    priv_guess.append(self._algebs_int_x0.get(item, 0.0))
                priv_syms.append(sym)
            dae.y = y_mixed
        else:
            dae.y = dae.yinit.copy()
        dae.s = np.ones(dae.nx)
        self.fgcall(dae)
        # Find the indices of differential equations for this type of generator
        diff = [self.__dict__[arg] for arg in self.states]
        diff_index = [item for sublist in np.transpose(diff) for item in sublist]

        # Stack private symbols as additional unknowns (after the setpoints) and
        # their defining equations dae.g[private] as additional residuals. This
        # keeps the Newton system square: +n*n_priv unknowns, +n*n_priv residuals.
        priv_stack = ca.SX.sym("", 0)
        for sym in priv_syms:
            priv_stack = ca.vertcat(priv_stack, sym)

        residuals = ca.vertcat(
            dae.f[diff_index],
            dae.g[self.__dict__["vre"]],
            dae.g[self.__dict__["vim"]],
        )
        if priv_global_idx:
            residuals = ca.vertcat(residuals, dae.g[priv_global_idx])

        # Device-declared anchor residuals balance setpoints not pinned by the
        # two bus-current equations (e.g. the inverter's Qref=Qc gauge fix).
        # Empty by default.
        for anchor in self.finit_anchor_residuals(dae):
            residuals = ca.vertcat(residuals, anchor)

        inputs = [ca.vertcat(dae.x[diff_index], u, priv_stack)]
        outputs = [residuals]

        W = [ca.vertcat(dae.omega_ref, dae.omega_ref_buses, dae.omega_ref_lines)]
        W_one = [ca.SX.ones(1 + dae.grid.nn + dae.grid.nb, 1)]
        outputs = ca.substitute(outputs, W, W_one)

        device_init = ca.Function("h", inputs, outputs)
        newton_init = ca.rootfinder("G", "newton", device_init)

        if guess_x0 is not None:
            x0 = np.asarray(guess_x0, dtype=float)
        else:
            x0 = np.array([self._x0[s] for s in self.states] * self.n)

        guess = ca.vertcat(x0, u0)
        if priv_guess:
            guess = ca.vertcat(guess, priv_guess)

        try:
            solution = np.array(newton_init(guess)).flatten()
        except RuntimeError:
            solution = np.full(int(inputs[0].numel()), np.nan)

        if not np.isfinite(solution).all():
            # Plain Newton can diverge when the per-device init Jacobian is
            # rank-deficient at the starting guess (a benign gauge in the d-axis
            # excitation/flux chain). Fall back to a damped Gauss-Newton
            # (Levenberg-Marquardt) iteration, which regularises the
            # rank-deficient Jacobian and converges to a consistent solution.
            h = ca.Function("h", inputs, outputs)
            Jh = ca.Function("Jh", inputs, [ca.jacobian(outputs[0], inputs[0])])
            z = np.array(guess).flatten().astype(float)
            lam = 1e-3
            r = np.array(h(z)).flatten()
            n_z = z.shape[0]
            ident = scipy.sparse.identity(n_z, format="csc")
            for _ in range(500):
                rn = np.linalg.norm(r)
                if rn < 1e-10:
                    break
                # The init Jacobian is block-diagonal across device instances;
                # keep it sparse. Densifying and solving with dense LAPACK is
                # O((n·n_states)³) and dominates init time for large fleets.
                J_dm = Jh(z)
                J_sp = J_dm.sparsity()
                J = scipy.sparse.csc_matrix(
                    (np.array(J_dm.nonzeros()), J_sp.row(), J_sp.colind()),
                    shape=J_dm.shape,
                )
                JtJ = (J.T @ J).tocsc()
                step = scipy.sparse.linalg.spsolve(JtJ + lam * ident, -(J.T @ r))
                z_new = z + step
                r_new = np.array(h(z_new)).flatten()
                if np.linalg.norm(r_new) < rn:
                    z, r = z_new, r_new
                    lam = max(lam * 0.5, 1e-12)
                else:
                    lam = min(lam * 2.0, 1e8)
            solution = z

        # Unpack the per-state init values from the machine-major solution
        # vector (states grouped per instance, n_states wide).
        index = 0
        for s in self.states:
            locat = []
            for n in range(self.n):
                locat.append(n * len(self.states) + index)
            self.xinit[s] = solution[locat]
            index += 1

        for idx, s in enumerate(self._setpoints):
            setpoint_range_start = (len(self.states) + idx) * self.n
            changed_setpoints = (
                u0[idx * self.n : (idx + 1) * self.n]
                != solution[setpoint_range_start : setpoint_range_start + self.n]
            )
            for i in range(self.n):
                if changed_setpoints[i]:
                    logging.info(
                        f"Setpoint '{s}' - {self._descr[s]} -  updated in device {self._name} at node {self.bus[i]} from {u0[idx * self.n + i]} to {solution[setpoint_range_start + i]} to match the initial power flow!"
                    )
            self.__dict__[s] = solution[
                setpoint_range_start : setpoint_range_start + self.n
            ]

        # Load the initial states into the DAE class so the simulation starts
        # from those values.
        dae.xinit[diff_index] = solution[: len(self.states) * self.n]

        # Write converged private algebraic values back into dae.yinit so the
        # time-domain start sits on the constraint manifold. The private block of
        # the solution begins after the states and setpoints, item-major
        # instance-minor (the order in which priv_global_idx was built).
        if self._algebs_int:
            k = (len(self.states) + len(self._setpoints)) * self.n
            for gidx in priv_global_idx:
                dae.yinit[gidx] = solution[k]
                k += 1

        # Clear the algebraic equations so fgcall can rebuild them from scratch.
        dae.g *= 0
        # Restore the voltages and switches as symbolic variables.
        dae.y = ca.SX.sym("y", dae.ny)
        dae.s = ca.SX.sym("s", dae.nx)

    def fgcall(self, dae: Dae) -> None:
        """
        A method that executes the differential and algebraic equations of the model
        and adds them to the appropriate places in the Dae class

        :param dae: an instance of a class Dae

        :type dae:

        :return: None

        :rtype: None
        """
        pass
