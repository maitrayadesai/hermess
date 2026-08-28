.. _parametric:

Parametric sensitivities
========================

With ``parametric=True`` the equations are assembled with every device
parameter as a CasADi symbol, so trajectories and functionals can be
differentiated with respect to them. The run itself is unchanged (the numeric
model is recovered by substitution before anything is integrated); the
parametric expressions are kept on the returned model:

.. code-block:: python

   import casadi as ca
   import numpy as np

   dae = hermess.simulate("3bus", T_end=0.5, parametric=True)

   model = dae.parametric_model      # p, p_val, f, g, entries
   rhs = dae.parametric_rhs()        # same expressions, reference frame resolved
   ca.jacobian(rhs.f, rhs.p)         # the parameter Jacobian of the model

Each entry of ``model.p`` is one per-unit parameter vector of one device;
``model.slice_of(device, "H")`` (or ``model.slice_of("SG1", "H")``) locates it.
``model.dae_dict()`` packages the parametric model for ``ca.integrator``, with
``p`` appended to the parameter input, so a trajectory functional and its exact
gradient cost one reverse-mode sweep regardless of the number of parameters:

.. code-block:: python

   grid = np.arange(0.01, 0.5, 0.01)
   I = ca.integrator("I", "idas", model.dae_dict(), 0.0, grid,
                     {"reltol": 1e-10, "abstol": 1e-12})

   machine = dae.device_list[0]
   x0 = np.array(dae.xinit)
   x0[machine.omega] += 2e-3         # kick the speed off the equilibrium

   p = ca.MX.sym("p", model.p.numel())
   res = I(x0=x0, z0=dae.yinit, p=ca.vertcat(ca.DM.ones(dae.nx), p))
   J = ca.sumsqr(res["xf"][int(machine.omega[0]), :] - 1.0)

   dJ_dp = ca.Function("dJ", [p], [ca.gradient(J, p)])(model.p_val)

Two boundaries to keep in mind. Setpoints (``Pref``, ``Vref``, ...) are
overwritten by the initialization to match the power flow and stay numeric;
so do the line parameters, which enter through the admittance matrices. And
the operating point itself is computed at the nominal values, so the
sensitivities are exact for parameters the operating point does not depend on
and omit the initial-condition term otherwise. ``hermess/parametric.py``
documents the full scope.
