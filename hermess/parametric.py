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

r"""Parametric build: device parameters as CasADi symbols.

With ``Config(parametric=True)``, :func:`hermess.run.run` replaces every
numeric device parameter with a CasADi symbol between the numeric
initialization (the ``finit`` loop) and the symbolic equation assembly (the
``fgcall`` loop), so the assembled equations carry parameter *symbols* rather
than baked-in numbers and :math:`\partial f/\partial p` exists. Immediately
after the assembly the numeric model is recovered by substituting the values
back in place, and the parametric copies are stashed on the Dae as
``dae.parametric_model``. Everything downstream (integration, the
initialization check, the eigenvalue analysis, the test baselines) therefore
sees a numeric model that agrees with the non-parametric build to floating
point rounding; the parametric expressions are served on request by
:meth:`hermess.system.Dae.parametric_rhs`.

Scope (phase 1 of ``docs/differentiability_plan.md``; the audit is in
``docs/differentiability_feasibility.md``):

* Only device parameters (``_params``) are lifted. Setpoints (``Pref``,
  ``Vref``, ...) are overwritten by the initialization to match the power flow
  and stay numeric. Line/grid parameters enter through the admittance matrices
  and stay numeric.
* The operating point is *not* differentiated: ``dae.xinit``/``dae.yinit`` are
  the numbers computed by ``finit`` at the nominal parameter values. The
  sensitivities are exact for parameters the operating point does not depend
  on and omit the initial-condition term otherwise (the plan's phase 2).
* A mid-run rebuild (a disturbance with dynamic lines, or a SETPOINT event)
  reassembles the equations from the restored numeric attributes; the stashed
  parametric model keeps describing the pre-disturbance system.
* The reference-frequency weights built by ``update_omega`` are numeric, so a
  ``coi``-type reference does not contribute parameter dependence through the
  frame in phase 1.
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import casadi as ca
import logging
import numpy as np


@dataclass
class ParamEntry:
    """One lifted parameter vector: ``device.<name>`` occupies ``p[sl]``.

    ``values`` are the numbers baked into ``p_val`` (NaN sentinels resolved);
    ``original`` is the untouched attribute array, put back on the device
    after the build so every numeric consumer keeps working.
    """

    device: object
    name: str
    values: np.ndarray
    original: np.ndarray
    sym: ca.SX
    sl: slice


@dataclass
class ParametricModel:
    """The parametric equations of one build, stashed as ``dae.parametric_model``.

    ``f``/``g``/``fnode``/``fl`` are the assembled expressions containing the
    parameter symbols ``p``; ``x``/``y``/``s``/``xl``/``sl`` are the symbol
    vectors they are written in (captured at build time, so later rebuilds do
    not invalidate them). ``ca.substitute(f, p, p_val)`` reproduces the
    numeric model.
    """

    p: ca.SX
    p_val: np.ndarray
    entries: list
    f: Optional[ca.SX]
    g: Optional[ca.SX]
    fnode: Optional[ca.SX]
    fl: Optional[ca.SX]
    x: Optional[ca.SX]
    y: Optional[ca.SX]
    s: Optional[ca.SX]
    xl: Optional[ca.SX]
    sl: Optional[ca.SX]
    dae: object

    def slice_of(self, device, name: str) -> slice:
        """The slice of ``p`` holding parameter ``name`` of ``device``.

        ``device`` is the device object or the ``idx`` of one of its units;
        the slice always covers the device object's full per-unit vector, and
        ``device.int[idx]`` gives the position of one unit inside it.
        """
        for e in self.entries:
            if e.name != name:
                continue
            if e.device is device or (
                isinstance(device, str) and device in getattr(e.device, "int", {})
            ):
                return e.sl
        raise KeyError(f"no lifted parameter '{name}' for device {device!r}")

    def rhs(self) -> SimpleNamespace:
        """The parametric right-hand side with the reference-frequency
        placeholders substituted by their expressions, mirroring what
        ``DaeSim.fgcall`` bakes into the integrator. Requires the simulation
        to have run (``update_omega`` builds the expressions)."""
        d = self.dae
        if getattr(d, "omega_ref_expr", None) is None:
            raise RuntimeError(
                "reference-frequency expressions not built yet; "
                "run the simulation before calling rhs()"
            )
        W_sym = ca.vertcat(d.omega_ref, d.omega_ref_buses, d.omega_ref_lines)
        W_expr = ca.vertcat(
            d.omega_ref_expr, d.omega_ref_buses_expr, d.omega_ref_lines_expr
        )

        def sub(e):
            return None if e is None else ca.substitute(e, W_sym, W_expr)

        return SimpleNamespace(
            x=self.x, y=self.y, s=self.s, xl=self.xl, sl=self.sl,
            f=sub(self.f), g=sub(self.g), fnode=sub(self.fnode), fl=sub(self.fl),
            p=self.p, p_val=self.p_val,
        )

    def dae_dict(self) -> dict:
        """A CasADi integrator dict of the parametric model, structured like
        the one ``DaeSim.fgcall`` builds, with ``p`` appended to the parameter
        vector. Use with ``ca.integrator`` to compute trajectories and their
        parameter sensitivities::

            I = ca.integrator("I", "idas", model.dae_dict(), t0, tgrid)
            res = I(x0=..., z0=..., p=ca.vertcat(ones(nx), p))
        """
        r = self.rhs()
        d = self.dae
        if d.line_dyn:
            if d.n_priv > 0:
                y_volt = r.y[: d.nv]
                y_priv = r.y[d.nv:]
                return {
                    "x": ca.vertcat(r.x, y_volt, r.xl),
                    "z": y_priv,
                    "p": ca.vertcat(r.s, r.sl, self.p),
                    "ode": ca.vertcat(r.f, r.fnode, r.fl),
                    "alg": r.g[d.nv:],
                }
            return {
                "x": ca.vertcat(r.x, r.y, r.xl),
                "p": ca.vertcat(r.s, r.sl, self.p),
                "ode": ca.vertcat(r.f, r.fnode, r.fl),
            }
        return {
            "x": r.x,
            "z": r.y,
            "p": ca.vertcat(r.s, self.p),
            "ode": r.f,
            "alg": r.g,
        }


def swap_parameters(device_list) -> list:
    """Replace the numeric parameter arrays of every equation-writing device
    with CasADi symbols and return the registry of what was swapped.

    Must run after the ``finit`` loop (initialization is numeric) and before
    the ``fgcall`` loop (assembly picks up the symbols). Ordering is stable:
    devices in ``device_list`` order, parameter names sorted within a device.

    Lifted: float arrays in ``device._params`` with at least one entry.
    Left numeric: non-float entries, and NaN-sentinel parameters without a
    declared fallback in ``device._param_sentinels`` (a sentinel with a
    fallback is lifted with its NaN entries resolved numerically, e.g. the
    inverter's ``omega_f_q`` following ``omega_f``). A resolved sentinel is
    an independent symbol: differentiating with respect to the fallback holds
    it fixed, and the sensitivity to a shared corner is the sum of the two
    partial derivatives.
    """
    entries: list = []
    offset = 0
    for dev in device_list:
        if not dev.properties.get("fgcall"):
            continue
        numeric = {
            name: getattr(dev, name)
            for name in dev._params
            if isinstance(getattr(dev, name, None), np.ndarray)
            and getattr(dev, name).dtype.kind == "f"
            and getattr(dev, name).size > 0
        }
        for name in sorted(numeric):
            original = numeric[name]
            values = original.copy()
            if np.isnan(values).any():
                fallback = getattr(dev, "_param_sentinels", {}).get(name)
                if fallback is None or fallback not in numeric:
                    logging.debug(
                        "parametric: leaving %s.%s numeric (NaN sentinel "
                        "without fallback)", dev._name, name,
                    )
                    continue
                values = np.where(np.isnan(values), numeric[fallback], values)
            sym = ca.SX.sym(f"{dev._type}_{name}", values.size)
            entries.append(
                ParamEntry(
                    device=dev, name=name, values=values, original=original,
                    sym=sym, sl=slice(offset, offset + values.size),
                )
            )
            setattr(dev, name, sym)
            offset += values.size
    return entries


def finalize(dae, entries: list) -> ParametricModel:
    """Stash the parametric expressions, substitute the numeric values back
    into ``dae.f``/``dae.g``/``dae.fnode``/``dae.fl`` in place, and restore
    the numeric device attributes.

    Runs right after the equation assembly (device ``fgcall`` loop plus
    ``grid.gcall``); from here on the run is numerically the model it is
    without the parametric flag, apart from floating point association (see
    the feasibility note).
    """
    if entries:
        p = ca.vertcat(*[e.sym for e in entries])
        p_val = np.concatenate([e.values for e in entries])
    else:
        p = ca.SX.sym("p", 0)
        p_val = np.zeros(0)

    model = ParametricModel(
        p=p, p_val=p_val, entries=entries,
        f=dae.f, g=dae.g, fnode=dae.fnode, fl=dae.fl,
        x=dae.x, y=dae.y, s=dae.s, xl=dae.xl, sl=getattr(dae, "sl", None),
        dae=dae,
    )

    pv = ca.DM(p_val)
    for attr in ("f", "g", "fnode", "fl"):
        expr = getattr(dae, attr)
        if isinstance(expr, ca.SX):
            setattr(dae, attr, ca.substitute(expr, p, pv))

    # Numeric attributes back (sentinel arrays keep their original NaNs, so a
    # later numeric rebuild reproduces today's fallback behavior exactly).
    for e in entries:
        setattr(e.device, e.name, e.original)

    # Published per-device expressions (Pe, Pc, Qc, the inner-control command
    # chain, ...) were assembled while the parameters were symbolic; make them
    # numeric in p as well so post-run evaluation keeps working.
    for dev in {id(e.device): e.device for e in entries}.values():
        for key, val in list(dev.__dict__.items()):
            if isinstance(val, ca.SX):
                dev.__dict__[key] = ca.substitute(val, p, pv)

    dae.p = p
    dae.p_val = p_val
    dae.parametric_model = model
    return model
