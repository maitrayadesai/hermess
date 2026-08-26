# PSCAD reference trajectories

These cases carry the strongest evidence in the suite: comparison against
**PSCAD**, a full electromagnetic-transients simulator, on the four systems
whose PSCAD runs the PSID project commits (`test/benchmarks/pscad/`,
Test08/23/24/25). Enabling them drove real model additions in v1.1: active
damping (`CascadedDamped`), split power-filter corners (`omega_f_q`), the
VSM angle source, the Kaura and reduced-order PLLs, the current-injecting
`GridFollowing` chain (the old PLL-droop chain became `GridSupporting`),
the Marconato machine, `AVRSimple`, `TGTypeII`, and the `SETPOINT`
disturbance (a reference step, the perturbation of all four benchmarks).

## Two-tier structure

Each case folder holds BOTH references for the same system:

- `upstream/` -- the PSCAD-produced trajectory (CSV) copied verbatim from
  the PSID benchmark set, with the upstream BSD-3 LICENSE and the `.pscx`
  project file; provenance and checksummed identity are pinned by the
  upstream commit recorded in `case.json`. The PSCAD component libraries
  (`PSID_Library*.pslx`, ~1 MB each) are not copied; they live at the
  pinned upstream path.
- `generate.jl` + `reference.csv` + `reference_meta.json` -- a locally
  generated PSID reference of the same system (the pinned Julia environment
  of `../psid/_generate/`), giving the full three-level check (operating
  point, eigenvalues, all states); the PSCAD CSV then adds the
  electromagnetic trajectory on top. The PSCAD data typically pins one
  channel (an angle, a speed, a power, a voltage), starting at a time
  offset recorded in `case.json`.

## The cases

- `test23/` -- droop grid-forming converter, full D'Arco set (active
  damping ON, split power filters), OMIB; θ_oc vs PSCAD.
- `test08/` -- virtual-synchronous-machine converter (VSM + Kaura PLL),
  OMIB; ω vs PSCAD to 1.3e-4 p.u.
- `test24/` -- grid-following converter (PI power outers, current-mode
  inner, reduced-order PLL), OMIB; p vs PSCAD. The upstream suite keeps its
  own PSCAD assertion for this case commented out; hermess and PSID agree
  to 9e-5 while both differ from the PSCAD power trace, so the committed
  bound is deliberately loose and only pins gross regressions.
- `test25/` -- two Marconato machines (Type II governor / fixed torque,
  AVRSimple) on a fully dynamic 60 Hz network; bus-102 voltage vs PSCAD,
  within the acceptance the upstream project itself uses (0.1 two-norm,
  "relaxed to account for mismatch in damping"). Its PSID reference runs in
  PSID's ReferenceBus frame (the constant frame fails to initialize with
  all lines dynamic upstream), so only frame-invariant trajectories are
  compared and the eigenvalue level is skipped, both documented in
  `case.json`.

## Findings recorded while building these

- The two OMIB inverter systems are extremely sensitive to the slack
  voltage: the raw file says 1.00001, and transcribing it as 1.0001 moved
  the operating point by 4.4e-2 in device-p.u. current (9e-5 across
  x = 0.075). With the exact transcription, initial states and eigenvalues
  agree with PSID to 1e-10.
- PSID realizes the TGTypeII lead-lag with the feedthrough separated: its
  state settles at (1 - T1/T2) times ours. Identical input/output, different
  internal coordinate; the state is compared at t = 0 only.

## Regenerating

```
julia --project=hermess/tests/references/psid/_generate \
      hermess/tests/references/pscad/<case>/generate.jl
```

The PSCAD CSVs are upstream data and are never regenerated here; refreshing
them means updating the pinned upstream commit.
