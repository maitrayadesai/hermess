# PSID reference trajectories

These cases compare hermess against `PowerSimulationsDynamics.jl` (PSID), the
Julia simulator whose converter carries the same six-state LCL filter, whose
Sauer-Pai machine and five-mass shaft match ours structurally, and which is
itself benchmarked against PSCAD trajectories. Unlike the ANDES and PSS/E
families, these references are generated locally by running PSID: each case
folder carries the `generate.jl` that produced it, the PSS/E raw file the
twin system is parsed from, and the committed `reference.csv` +
`reference_meta.json`.

## Regenerating

Regeneration is a deliberate act; CI compares the committed files and needs
no Julia. The pinned Julia environment lives in `_generate/`
(Project.toml + Manifest.toml):

```
julia --project=hermess/tests/references/psid/_generate \
      -e 'using Pkg; Pkg.instantiate()'
julia --project=hermess/tests/references/psid/_generate \
      hermess/tests/references/psid/<case>/generate.jl
```

The versions that produced each reference are recorded in its
`reference_meta.json`. The committed data was generated with PSID 0.16.2.

## The cases

- `gfm_droop/` -- the droop grid-forming converter (D'Arco component set):
  PSID ActivePowerDroop + ReactivePowerDroop + VoltageModeControl + LCL is
  the hermess GridForming exactly, once PSID's active damping is off
  (`kad = 0`, leaving two inert states at exactly -ωad) and its two power
  filters share one corner frequency (ωz = ωf = hermess `omega_f`). The
  internal dq frames coincide (θ_oc = `delta_c`), so all thirteen states
  compare directly.
- `sauerpai/` -- the six-state Sauer-Pai machine: PSID SauerPaiMachine +
  SingleMass(D = 0) + AVRFixed + TGFixed is hermess
  SynchronousSubtransientSP + AVRCONST + GOVCONST (D = 0, f = 0)
  equation for equation, including the derived gamma coefficients and the
  Kundur dq transform.
- `shaft5mass/` -- the five-mass torsional shaft (Sauer-Pai torsional data):
  PSID FiveMassShaft applies the whole mechanical torque to the HP mass,
  which is hermess Shaft5Mass with `F_hp = 1, F_ip = F_lp = 0`; everything
  else (inertias, self and mutual dampings, stiffnesses) maps one to one.

All three share a three-bus system: ideal source at the reference bus
(PSID `Source` = hermess `StaticInfiniteBus`, X_th = 1e-4), the device under
test at bus 102, a constant-impedance load at bus 103, and a
+20 MW / +5 Mvar impedance-load step at t = 1 s (both tools scale the load
admittance at the initial power-flow voltage).

## Findings and pitfalls recorded while building these

- **The PowerSystems.jl PSS/E parser ignores the frequency in the raw
  header** and defaults the system to 60 Hz; `generate.jl` must pass
  `frequency = 50.0` explicitly. The mismatch barely moved the trajectories
  of a mildly disturbed machine but shifted every oscillatory eigenvalue by
  the ωb ratio (the stator-flux mode by exactly 60/50) — the reason the
  suite checks spectra, not just trajectories.
- PSID's IDA does not restart across a `BranchTrip` topology change in
  these systems (error-test failure at minimum step, at any source
  stiffness we tried), and tolerances tighter than 1e-6 fail the restart
  even for a load step; the references therefore use the load step and
  abstol = reltol = 1e-6, which bounds the reference accuracy itself.
- PSID's default frequency reference (`ReferenceBus`) can rotate the
  network frame with the reference device's speed; `generate.jl` pins
  `ConstantFrequency()`, the frame hermess uses with `omega_mode = "nom"`.

## Why the PSCAD-benchmarked PSID cases are not consumed

PSID commits four PSCAD-produced trajectories (`test/benchmarks/pscad/`,
Test08/23/24/25). None is representable by hermess as shipped; consuming
them would validate someone else's model, not ours:

| upstream case | blocker |
|---|---|
| Test08 (VSM inverter) | hermess ships no virtual-inertia angle source (`VirtualInertia` Ta/kd/kω). |
| Test23 (droop inverter) | the reference embeds active damping (kad = 0.2) and split power-filter frequencies (ωz = 2π·5, ωf = 1000); hermess has neither. |
| Test24 (grid following) | PSID's grid-following chain is PI outer + current-mode inner + Kaura PLL; hermess GridFollowing (PLL-anchored droop + voltage-mode cascade) has no PSID counterpart at all — the anchor choice is welded to the actuation type in PSID. |
| Test25 (multi-machine, dynamic lines) | Marconato machines + AVRSimple + TG Type II, none shipped by hermess. |

The `gfm_droop` case is the exact-match replacement for Test23: same
component family, active damping disabled on the PSID side instead of
missing on ours.

## What remains possible here

- A dynamic-lines case (hermess `line_dyn=True` vs PSID `DynamicBranch`) is
  structurally exact within a documented box: all lines dynamic, unity
  taps, `g = 0`, charging `b > 0` at every bus, nominal frame; neither tool
  supports tripping a dynamic line, so the disturbance must be a load step.
- hermess GridFollowing needs a different reference tool (or a PSID
  extension); the structural analysis is in the table above.
