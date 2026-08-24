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
from typing import TYPE_CHECKING

import logging

if TYPE_CHECKING:
    from hermess.system import Dae
from hermess.devices.device import DeviceRect
from hermess.devices.inverter_filter import Filter, LCL
from hermess.devices.inverter_pll import PLL, SRF_PLL
from hermess.devices.inverter_angle import AngleSource, DroopAngle, PLLAngle
from hermess.devices.inverter_voltage import VoltageControl, QVDroop
from hermess.devices.inverter_inner import InnerControl, Cascaded
import casadi as ca
import numpy as np


class Inverter(DeviceRect):
    """Metaclass for inverters"""

    # Default init is the staged sequential solve (_finit_sequential). Set to
    # "joint" for the one-shot Newton+LM solve (_finit_joint) plus
    # finit_anchor_residuals.
    _init_method = "sequential"

    def __init__(
        self, filter=None, pll=None, angle=None, voltage=None, inner=None
    ):
        super().__init__()

        # Filter (electrical-plant) strategy. Registered first so its states
        # occupy the leading block (0..nf-1) of the state vector.
        self._filter: Filter = filter or LCL()

        # Angle-source strategy is mandatory: the forming-vs-following choice has
        # no safe silent default. GridForming/GridFollowing supply theirs; a bare
        # Inverter row must pass angle=. Registered after the filter so its states
        # (Pc_tilde, delta_c) follow.
        if angle is None:
            raise ValueError(
                "An inverter requires an explicit angle source (the forming-vs-"
                "following choice). Pass angle=Droop / PLL / ... or use a "
                "GridForming / GridFollowing device."
            )
        self._angle: AngleSource = angle

        # Outer voltage-control strategy (Q-V droop). Registered after the angle
        # source so its state (Qc_tilde) follows.
        self._voltage: VoltageControl = voltage or QVDroop()

        # Inner control strategy (cascaded V/I + virtual impedance). Registered
        # after the voltage loop so its states (xi/gamma) follow.
        self._inner: InnerControl = inner or Cascaded()

        # PLL (frequency-estimator) strategy, or None. Separate from the angle
        # source (host-mediated, PSS-style); registered last so its states occupy
        # the trailing block of the state vector.
        self._pll: PLL = pll

        # The host owns only the power-measurement filter cut-off omega_f, shared
        # by the angle and voltage power filters (whose equations the host writes).
        # All other params/states/setpoints are owned by the strategies.
        self._params.update(
            {
                "omega_f": 2 * np.pi * 5,
            }
        )
        self._params.update(self._filter.params())

        self._descr.update(
            {
                "Pref": "Active power set point",
                "Qref": "Reactive power set point",
                "Vref": "Voltage set point",
                "Kp": "Droop coefficient for P-f",
                "Kq": "Droop coefficient for Q-V",
                "Pc_tilde": "Filtered internal active power",
                "Qc_tilde": "Filtered internal reactive power",
                "xi_d": "Integrator state of the d-component of the internal voltage",
                "xi_q": "Integrator state of the q-component of the internal voltage",
                "gamma_d": "Integrator state of the d-component of the internal current",
                "gamma_q": "Integrator state of the q-component of the internal current",
                "omega_f": "cut-off frequency for the low pass filter",
                "Kpc": "Proportional gain for current controller",
                "Kic": "Integral gain for current controller",
                "Kffc": "Feed-forward gain of current controller",
                "Kpv": "Proportional gain for voltage controller",
                "Kiv": "Integral gain for voltage controller",
                "Kffv": "Feed-forward gain of voltage controller",
                "Rv": "Virtual impedance resistance",
                "Lv": "Virtual impedance inductance",
                "Pc": "Unfiltered internal active power",
                "Qc": "Unfiltered internal reactive power",
            }
        )
        self._descr.update(self._filter.descriptions())

        # Host parameter array (power-filter cut-off).
        self.omega_f = np.array([], dtype=float)
        # Filter parameter arrays (filled by the data loader, read by the strategy).
        for param_name in self._filter.params():
            setattr(self, param_name, np.array([], dtype=float))

        # States: filter block first, then the inline control states.
        self.ns = 0
        filter_states = self._filter.states()
        self.ns += len(filter_states)
        self.states.extend(filter_states)
        self.units.extend(self._filter.units())
        for name in filter_states:
            setattr(self, name, np.array([], dtype=float))
        self._x0.update(self._filter.x0())

        # Filter private algebraics: a quasi-static realization (e.g. LCL_static)
        # declares its filter quantities here instead of as states, and var_sym
        # resolves them to dae.y. Empty for the dynamic LCL.
        filter_algebs = self._filter.algebs()
        if filter_algebs:
            self._algebs_int.extend(filter_algebs)
            self._algebs_int_units.update(self._filter.algebs_units())
            self._algebs_int_x0.update(self._filter.algebs_x0())
            for name in filter_algebs:
                setattr(self, name, np.array([], dtype=float))

        # Angle source: its states (Pc_tilde, delta_c) occupy the next block. Owns
        # the Kp droop param and the Pref setpoint; the host writes the Pc_tilde
        # measurement-filter equation.
        self._params.update(self._angle.params())
        self._descr.update(self._angle.descriptions())
        for param_name in self._angle.params():
            setattr(self, param_name, np.array([], dtype=float))
        angle_states = self._angle.states()
        self.ns += len(angle_states)
        self.states.extend(angle_states)
        self.units.extend(self._angle.units())
        for name in angle_states:
            setattr(self, name, np.array([], dtype=float))
        self._x0.update(self._angle.x0())
        self._setpoints.update(self._angle.setpoints())
        for sp_name in self._angle.setpoints():
            setattr(self, sp_name, np.array([], dtype=float))

        # Outer voltage control: its state (Qc_tilde) follows. Owns Kq and the
        # Qref/Vref setpoints; the host writes the Qc_tilde measurement-filter
        # equation.
        self._params.update(self._voltage.params())
        self._descr.update(self._voltage.descriptions())
        for param_name in self._voltage.params():
            setattr(self, param_name, np.array([], dtype=float))
        voltage_states = self._voltage.states()
        self.ns += len(voltage_states)
        self.states.extend(voltage_states)
        self.units.extend(self._voltage.units())
        for name in voltage_states:
            setattr(self, name, np.array([], dtype=float))
        self._x0.update(self._voltage.x0())
        self._setpoints.update(self._voltage.setpoints())
        for sp_name in self._voltage.setpoints():
            setattr(self, sp_name, np.array([], dtype=float))

        # Inner control: its states (xi_d, xi_q, gamma_d, gamma_q) follow.
        self._params.update(self._inner.params())
        self._descr.update(self._inner.descriptions())
        for param_name in self._inner.params():
            setattr(self, param_name, np.array([], dtype=float))
        inner_states = self._inner.states()
        self.ns += len(inner_states)
        self.states.extend(inner_states)
        self.units.extend(self._inner.units())
        for name in inner_states:
            setattr(self, name, np.array([], dtype=float))
        self._x0.update(self._inner.x0())

        # PLL strategy (if present): its states occupy the trailing block of the
        # vector (e.g. GridFollowing's epsilon/delta_pll).
        if self._pll is not None:
            self._params.update(self._pll.params())
            self._descr.update(self._pll.descriptions())
            for param_name in self._pll.params():
                setattr(self, param_name, np.array([], dtype=float))
            pll_states = self._pll.states()
            self.ns += len(pll_states)
            self.states.extend(pll_states)
            self.units.extend(self._pll.units())
            for name in pll_states:
                setattr(self, name, np.array([], dtype=float))
            self._x0.update(self._pll.x0())
            # Exposed for the reference-frame machinery (system.py) before the
            # first fgcall; the strategy sets the omega_pll expression each fgcall.
            self.omega_pll = None

        # Warn (but continue) if the inner controller needs plant features (e.g. a
        # shunt capacitor for its voltage loop) the chosen filter does not provide.
        missing = self._inner.requires() - self._filter.provides()
        if missing:
            logging.warning(
                "Inverter strategy mismatch: inner controller %s requires plant "
                "capabilities %s that filter %s does not provide; "
                "initialization/behaviour may be inconsistent.",
                type(self._inner).__name__,
                sorted(missing),
                type(self._filter).__name__,
            )

        # A quasi-static filter realizes its quantities as private algebraics,
        # handled by either init method: the joint solve includes them as unknowns;
        # the sequential solve routes the filter strategy's algebraic values into
        # dae.yinit (see _load_finit). Such a filter follows the device's
        # _init_method like any other.

        # Control intermediates published by the strategies each fgcall and read
        # back through the host accessors voltage_command / current_ref /
        # switching_voltage (the same host-mediated pattern as pll_frequency). They
        # are symbolic intermediates, not registered DAE variables. Pre-initialized
        # to None like omega_pll/omega_c.
        self.Vcd = None  # voltage-magnitude command (from the voltage strategy)
        self.ifd_ref = None  # current references (from the inner strategy)
        self.ifq_ref = None
        self.Vswd = None  # switching voltage (from the inner strategy)
        self.Vswq = None
        self.Pc = None  # terminal active power (device p.u.); set in fgcall
        self.Qc = None  # terminal reactive power (device p.u.); set in fgcall

        self.properties.update({"fplot": True})

    def gcall(self, dae: Dae) -> None:

        # Current-balance (rectangular) into the network, scaled to the grid base
        # power. The terminal current is a filter quantity read via var_sym, so a
        # quasi-static filter (where it is algebraic) is transparent here.
        dae.g[self.vre] -= self.Sn / dae.Sb * self.var_sym(dae, "itd_ext")
        dae.g[self.vim] -= self.Sn / dae.Sb * self.var_sym(dae, "itq_ext")

    def var_sym(self, dae: Dae, name: str) -> ca.SX:
        """Resolve a registered variable name to its symbol wherever it lives:
        ``dae.y`` for a device-private algebraic, ``dae.x`` for a differential
        state. Lets the converter equations read a coupling quantity (a filter
        state, the frame angle, ...) regardless of whether a given realization made
        it a state or an algebraic (dynamic ``LCL`` states vs quasi-static
        ``LCL_static`` algebraics)."""
        if name in self._algebs_int:
            return dae.y[getattr(self, name)]
        return dae.x[getattr(self, name)]

    @staticmethod
    def to_internal(d_ext, q_ext, delta):
        """Park-rotate ``(d, q)`` from the network (external) frame into the
        converter (internal) frame defined by angle ``delta``."""
        cos_d = np.cos(-delta)
        sin_d = np.sin(-delta)
        return d_ext * cos_d - q_ext * sin_d, d_ext * sin_d + q_ext * cos_d

    @staticmethod
    def to_external(d_int, q_int, delta):
        """Park-rotate ``(d, q)`` from the converter (internal) frame back to the
        network (external) frame defined by angle ``delta``."""
        cos_d = np.cos(delta)
        sin_d = np.sin(delta)
        return d_int * cos_d - q_int * sin_d, d_int * sin_d + q_int * cos_d

    def _pll_fgcall(self, dae: Dae, omega_ref_vec, omega_b) -> None:
        """Delegate to the PLL strategy (no-op if there is no PLL). Runs before the
        angle source so that ``self.omega_pll`` is set when a PLL-consuming angle
        source reads it via :meth:`pll_frequency`."""
        if self._pll is not None:
            self._pll.fgcall(self, dae, omega_ref_vec, omega_b)

    def pll_frequency(self, dae: Dae) -> ca.SX:
        """Synchronizing frequency from the PLL, host-mediated: the PLL's
        ``omega_pll`` when a PLL strategy is present, else nominal ``omega_net``
        (no PLL => no estimate). Consumers read this accessor and never reference
        the PLL strategy directly."""
        if self._pll is None:
            return dae.omega_net
        return self.omega_pll

    def voltage_command(self, dae: Dae) -> ca.SX:
        """Voltage-magnitude reference ``Vcd``, host-mediated: published by the
        voltage strategy's ``fgcall`` and read by the inner controller. A symbolic
        intermediate, not a DAE variable."""
        return self.Vcd

    def current_ref(self, dae: Dae):
        """Inner current references ``(ifd_ref, ifq_ref)``, host-mediated:
        published by the inner strategy and read back by its own current loop. This
        accessor is the interception seam for a future current limiter, which would
        resolve it to a saturated ``var_sym`` algebraic (``i* = sat(iref)``)."""
        return self.ifd_ref, self.ifq_ref

    def switching_voltage(self, dae: Dae):
        """Switching voltage ``(Vswd, Vswq)`` in the network frame, host-mediated:
        published by the inner strategy and read by the filter. A symbolic
        intermediate, not a DAE variable."""
        return self.Vswd, self.Vswq

    def fgcall(self, dae: Dae) -> None:
        """Orchestrate the pluggable converter strategies into the DAE residual.

        The host owns only the cross-cutting glue: the reference-frame frequency,
        the Park transforms into the converter frame, the power measurement, and
        the power-measurement filters. Everything else is delegated, in signal-flow
        order: PLL -> angle source (omega_c, delta_c) -> voltage control (Vcd) ->
        inner control (Vsw) -> filter (LCL). Each strategy reads host params/states
        by attribute and writes its own equations; the host threads the symbolic
        intermediates (omega_c, Vcd, Vsw) between them."""
        n = self.n

        # Vector formulation for base speed
        omega_b = [2 * np.pi * dae.fn] * n

        # Per-machine reference-frame frequency (bus-uniform).
        omega_ref_vec = ca.SX.ones(n, 1) * dae.omega_net  # initialization and fallback
        if getattr(dae, "omega_ref_buses", None) is not None:
            omega_list = []
            for k in range(n):
                bus_label = str(self.bus[k])
                bus_idx = dae.grid.idx_bus[bus_label]
                omega_list.append(
                    dae.omega_ref_buses[bus_idx]
                )  # frequency at inverter bus
            omega_ref_vec = ca.vertcat(*omega_list)

        # PLL (frequency estimator), if present: sets self.omega_pll for the angle
        # source and reference-frame machinery, and writes its own state equations.
        self._pll_fgcall(dae, omega_ref_vec, omega_b)

        # Angle source: converter frequency + angle dynamics (pluggable strategy).
        omega_c = self._angle.fgcall(self, dae, omega_ref_vec, omega_b)

        # Outer voltage control: publishes the voltage-magnitude command on the
        # host (read by the inner ladder below via self.voltage_command).
        self._voltage.fgcall(self, dae)

        # Filter-state and frame-angle reads go through var_sym so a quasi-static
        # filter (where these are algebraics) is transparent to the control ladder.
        Vfd_ext_s = self.var_sym(dae, "Vfd_ext")
        Vfq_ext_s = self.var_sym(dae, "Vfq_ext")
        ifd_ext_s = self.var_sym(dae, "ifd_ext")
        ifq_ext_s = self.var_sym(dae, "ifq_ext")
        itd_ext_s = self.var_sym(dae, "itd_ext")
        itq_ext_s = self.var_sym(dae, "itq_ext")
        delta_c_s = self.var_sym(dae, "delta_c")

        # Park-rotate the filter quantities into the converter (internal) frame and
        # form the injected powers. The internal quantities are handed to the inner
        # control strategy below.
        Vfd_int, Vfq_int = self.to_internal(Vfd_ext_s, Vfq_ext_s, delta_c_s)
        itd_int, itq_int = self.to_internal(itd_ext_s, itq_ext_s, delta_c_s)
        ifd_int, ifq_int = self.to_internal(ifd_ext_s, ifq_ext_s, delta_c_s)

        Pc = Vfd_int * itd_int + Vfq_int * itq_int
        Qc = -Vfd_int * itq_int + Vfq_int * itd_int
        # Publish the instantaneous terminal powers (device p.u., on Sn). The
        # states Pc_tilde / Qc_tilde are these passed through the measurement
        # filter; keeping the unfiltered expressions lets them be read back after
        # a run (plots, objectives) for any filter/control strategy.
        self.Pc, self.Qc = Pc, Qc

        # Inner control (cascaded V/I + virtual impedance): consumes the converter-
        # frame quantities + omega_c, reads the voltage command via
        # self.voltage_command, writes its PI integrator equations, and publishes
        # the switching voltage + current references on the host.
        internals = {
            "Vfd": Vfd_int,
            "Vfq": Vfq_int,
            "itd": itd_int,
            "itq": itq_int,
            "ifd": ifd_int,
            "ifq": ifq_int,
        }
        self._inner.fgcall(self, dae, internals, omega_c, delta_c_s)

        # Filter (electrical plant): delegate the LCL dynamics to the filter
        # strategy. It reads the driving switching voltage via self.switching_voltage.
        self._filter.fgcall(self, dae, omega_ref_vec, omega_b)

        # Power-measurement filters (host-level: Pc/Qc come from the Park loop and
        # feed both the angle and voltage strategies).
        dae.f[self.Pc_tilde] = self.omega_f * (Pc - dae.x[self.Pc_tilde])
        dae.f[self.Qc_tilde] = self.omega_f * (Qc - dae.x[self.Qc_tilde])

        self.gcall(dae)

    def finit_anchor_residuals(self, dae: Dae) -> list:
        # The inverter has 3 setpoints (Pref/Qref/Vref) but the bus-current
        # equations pin only 2. Pref is pinned by the angle integrator
        # (f[delta_c]=0 -> omega_c=omega_ref -> Pref=Pc_tilde via the droop). The
        # remaining Qref/Vref gauge (both enter steady state only through
        # Vcd = Vref + Kq(Qref - Qc_tilde)) is fixed by the convention Qref = Qc:
        # Qref equals the dispatched reactive power, = Qc_tilde at steady state.
        # This makes the joint-init Newton system square.
        return [self.Qref - dae.x[self.Qc_tilde]]

    def _finit_sequential(self, dae: Dae) -> None:
        """Strategy-composed staged initialization (the inverter default), shared
        by GridForming and GridFollowing. Each strategy owns its own stage; the
        host threads the operating point between them and assembles the result by
        name. Data flow:

        filter (decoupled) -> pll (decoupled) -> powers from the filter op-point
        (frame-invariant) -> inner (frame ``delta_c`` + command ``Vcd`` + the four
        integrators) -> angle (``Pref``/``Pc_tilde``, owns ``delta_c``) -> voltage
        (``Qref``/``Qc_tilde``, unpacks ``Vcd`` -> ``Vref`` via its gauge).
        """
        vals: dict = {}

        # 1. Filter: steady state from the power-flow terminal point (decoupled).
        # The filter realizes its quantities as states (dynamic LCL) or private
        # algebraics (quasi-static LCL_static); collect both, _load_finit routes
        # each to dae.xinit or dae.yinit.
        filt = self._filter.finit_sequential(self, dae)
        for name in self._filter.states():
            vals[name] = filt[name]
        for name in self._filter.algebs():
            vals[name] = filt[name]

        # 2. PLL (if present): locked to the filter voltage (decoupled).
        if self._pll is not None:
            vals.update(
                self._pll.finit_sequential(self, dae, filt["Vfd_ext"], filt["Vfq_ext"])
            )

        # 3. Injected powers from the filter op-point. Frame-invariant
        #    (Vd*Id + Vq*Iq is rotation-invariant), so computed directly here with
        #    no delta_c or inner solve. Owned by the angle (P) / voltage (Q) below.
        itd_ext = dae.Sb / self.Sn * dae.iinit[self.vre]
        itq_ext = dae.Sb / self.Sn * dae.iinit[self.vim]
        Pc = filt["Vfd_ext"] * itd_ext + filt["Vfq_ext"] * itq_ext
        Qc = -filt["Vfd_ext"] * itq_ext + filt["Vfq_ext"] * itd_ext

        # 4. Inner control: the frame angle, voltage command, and integrators (owns
        #    the virtual impedance). Fed the synchronizing frequency by the angle.
        omega_c = self._angle.steady_frequency(self, dae)
        inner = self._inner.finit_sequential(self, dae, filt, omega_c)
        for name in self._inner.states():
            vals[name] = inner[name]

        # 5. Angle source: owns delta_c (value from the inner) + Pref / Pc_tilde.
        vals.update(self._angle.finit_sequential(self, dae, Pc, inner["delta_c"]))

        # 6. Voltage controller: owns Qref / Qc_tilde and unpacks Vcd -> Vref.
        vals.update(self._voltage.finit_sequential(self, dae, Qc, inner["Vcd"]))

        # 7. Assemble by name into xinit / yinit / setpoints.
        self._load_finit(dae, vals)

    def _load_finit(self, dae: Dae, vals: dict) -> None:
        """Load the computed init values by name: differential states -> dae.xinit,
        device-private algebraics -> dae.yinit, setpoints -> the device's setpoint
        arrays. Driven by self.states / self._algebs_int / self._setpoints, so it
        adapts to any strategy combo and to the state-vs-algebraic realization."""
        for name in self.states:
            dae.xinit[self.__dict__[name]] = vals[name]
        for name in self._algebs_int:
            dae.yinit[self.__dict__[name]] = vals[name]
        for name in self._setpoints:
            self.__dict__[name] = vals[name]


class GridFollowing(Inverter):
    r"""Grid-Following Inverter (with Droop)
    Based on the grid-following inverter model in https://doi.org/10.1109/TPWRS.2021.3061434

    The dynamic behavior of the grid-following converter is described by the following differential equations:

    **Converter Voltage Dynamics**


    .. math::

        \dot{v}_{fd_{ext}} = \frac{\omega_{b}}{c_{f}}(i_{fd_{ext}} - i_{td_{ext}}) + \omega_{net}\omega_{b}v_{fq_{ext}}

    .. math::

        \dot{v}_{fq_{ext}} = \frac{\omega_{b}}{c_{f}}(i_{fq_{ext}} - i_{tq_{ext}}) - \omega_{net}\omega_{b}v_{fd_{ext}}

    **Converter Current Dynamics**


    .. math::

        \dot{i}_{fd_{ext}} = \frac{\omega_{b}}{l_{f}}(v_{swd} - v_{fd_{ext}}) - \frac{\omega_{b}r_{f}}{l_{f}}i_{fd_{ext}} + \omega_{net}\omega_{b}i_{fq_{ext}}

    .. math::

        \dot{i}_{fq_{ext}} = \frac{\omega_{b}}{l_{f}}(v_{swq} - v_{fq_{ext}}) - \frac{\omega_{b}r_{f}}{l_{f}}i_{fq_{ext}} - \omega_{net}\omega_{b}i_{fd_{ext}}

    **Grid-Side Current Dynamics**


    .. math::

        \dot{i}_{td_{ext}} = \frac{\omega_b}{l_t}(v_{fd_{ext}} - v_{n_{re}}) - \frac{\omega_b r_t}{l_t}i_{td_{ext}} + \omega_{net} \omega_b i_{tq_{ext}}

    .. math::

        \dot{i}_{tq_{ext}} = \frac{\omega_b}{l_t}(v_{fq_{ext}} - v_{n_{im}}) - \frac{\omega_b r_t}{l_t}i_{tq_{ext}} - \omega_{net} \omega_b i_{td_{ext}}

    **Phase-Locked Loop (PLL) Dynamics**


    .. math::

        \dot{\epsilon} = v_{fq_{pll}}

    .. math::

        \delta\dot{\theta}_{pll} = \omega_{b}\delta\omega_{pll}

    **Power and Frequency Dynamics**


    .. math::

        \dot{\tilde{p}}_{c} = \omega_{f}(p_{c} - \tilde{p}_{c})

    .. math::

        \delta\dot{\theta}_{c} = \omega_{b}\delta\omega_{c}

    .. math::

        \dot{\tilde{q}}_{c} = \omega_{f}(q_{c} - \tilde{q}_{c})

    **Control Dynamics**


    .. math::

        \dot{\xi}_{d} = v_{fd^{*}} - v_{fd_{int}}

    .. math::

        \dot{\xi}_{q} = v_{fq^{*}} - v_{fq_{int}}

    .. math::

        \dot{\gamma}_{d} = i_{fd^{*}} - i_{fd_{int}}

    .. math::

        \dot{\gamma}_{q} = i_{fq^{*}} - i_{fq_{int}}

    """

    def __init__(
        self, filter=None, angle=None, voltage=None, inner=None, pll=None
    ) -> None:
        # Grid-following = the converter frame anchored on a PLL. The angle source
        # (default PLLAngle) rides on the PLL frequency; the PLL strategy (default
        # SRF_PLL) owns epsilon/delta_pll + Kpll_p/Kpll_i. Other axes pass through.
        super().__init__(
            filter=filter,
            angle=angle or PLLAngle(),
            voltage=voltage,
            inner=inner,
            pll=pll or SRF_PLL(),
        )

        # private data
        self._type = "Inverter"
        self._name = "GridFollowing_inverter_model"

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
            }
        )
        self._init_data()


class GridForming(Inverter):
    # Droop-based voltage-source inverter
    r"""Grid-Forming Inverter (Droop-Based)
    Based on the grid-forming inverter model in https://doi.org/10.1109/TPWRS.2021.3061434
    The dynamic behavior of the grid-forming converter is described by the following differential equations:

    **Converter Voltage Dynamics**


    .. math::

        \dot{v}_{fd_{ext}} = \frac{\omega_{b}}{c_{f}}(i_{fd_{ext}} - i_{td_{ext}}) + \omega_{net}\omega_{b}v_{fq_{ext}}

    .. math::

        \dot{v}_{fq_{ext}} = \frac{\omega_{b}}{c_{f}}(i_{fq_{ext}} - i_{tq_{ext}}) - \omega_{net}\omega_{b}v_{fd_{ext}}

    **Converter Current Dynamics**


    .. math::

        \dot{i}_{fd_{ext}} = \frac{\omega_{b}}{l_{f}}(v_{swd} - v_{fd_{ext}}) - \frac{\omega_{b}r_{f}}{l_{f}}i_{fd_{ext}} + \omega_{net}\omega_{b}i_{fq_{ext}}

    .. math::

        \dot{i}_{fq_{ext}} = \frac{\omega_{b}}{l_{f}}(v_{swq} - v_{fq_{ext}}) - \frac{\omega_{b}r_{f}}{l_{f}}i_{fq_{ext}} - \omega_{net}\omega_{b}i_{fd_{ext}}

    **Grid-Side Current Dynamics**


    .. math::

        \dot{i}_{td_{ext}} = \frac{\omega_b}{l_t}(v_{fd_{ext}} - v_{n_{re}}) - \frac{\omega_b r_t}{l_t}i_{td_{ext}} + \omega_{net} \omega_b i_{tq_{ext}}

    .. math::

        \dot{i}_{tq_{ext}} = \frac{\omega_b}{l_t}(v_{fq_{ext}} - v_{n_{im}}) - \frac{\omega_b r_t}{l_t}i_{tq_{ext}} - \omega_{net} \omega_b i_{td_{ext}}

    **Power and Frequency Dynamics**


    .. math::

        \dot{\tilde{p}}_{c} = \omega_{f}(p_{c} - \tilde{p}_{c})

    .. math::

        \delta\dot{\theta}_{c} = \omega_{b}\delta\omega_{c}

    .. math::

        \dot{\tilde{q}}_{c} = \omega_{f}(q_{c} - \tilde{q}_{c})

    **Control Dynamics**


    .. math::

        \dot{\xi}_{d} = v_{fd^{*}} - v_{fd_{int}}

    .. math::

        \dot{\xi}_{q} = v_{fq^{*}} - v_{fq_{int}}

    .. math::

        \dot{\gamma}_{d} = i_{fd^{*}} - i_{fd_{int}}

    .. math::

        \dot{\gamma}_{q} = i_{fq^{*}} - i_{fq_{int}}

    """

    def __init__(
        self, filter=None, angle=None, voltage=None, inner=None, pll=None
    ) -> None:
        # Grid-forming = the converter sets its own frequency (default DroopAngle);
        # all other axes pass through to the base defaults (or a data-file override).
        super().__init__(
            filter=filter,
            angle=angle or DroopAngle(),
            voltage=voltage,
            inner=inner,
            pll=pll,
        )

        # private data
        self._type = "Inverter"
        self._name = "GridForming_inverter_model"

        # Exposed for the reference-frequency machinery (system.py dispatches GFM by
        # the presence of omega_c) before the first fgcall; the DroopAngle strategy
        # sets it each fgcall.
        self.omega_c = None  # (algebraic, not state)

        self.properties.update(
            {
                "fgcall": True,
                "finit": True,
                "init_data": True,
                "xy_index": True,
                "save_data": True,
            }
        )
        self._init_data()
