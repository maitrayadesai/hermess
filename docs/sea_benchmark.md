# The 14-generator South East Australian benchmark in HERMESS

Source: M. Gibbard & D. Vowles, *Simplified 14-Generator Model of the South
East Australian Power System*, The University of Adelaide, Revision 4, 2014
(publicly available report; the parameter tables were transcribed into
`sea_data.py` / `sea_dynamics.py`, the PDF itself is not part of this
repository). 59 buses, 5 areas,
14 aggregated power stations, 5 SVCs, 50 Hz, six published operating cases.

## Layout

```
hermess/systems/sea14gen/
  sea_data.py          # Tables 1, 8-14: network, loads, schedules (transcribed)
  sea_dynamics.py      # Tables 15-20, 26/27, Fig. 22, Tables 2-7 (modes)
  build_sea_system.py  # emits case<N>[ _nopss | _conv ]/sim_param.txt
  validate_sea.py      # loadflow + rotor-mode validation vs the PDF tables
  smib_crosscheck.py   # machine-implementation cross-check (SMIB)
  case1/ ...       # generated system files
```

Build and validate (case 1..6):

```
python hermess/systems/sea14gen/build_sea_system.py 1
python hermess/systems/sea14gen/validate_sea.py 1
python hermess/systems/sea14gen/build_sea_system.py 1 --no-pss
python hermess/systems/sea14gen/validate_sea.py 1 --no-pss
# converter variant: replace stations by GFM/GFL converters
python .../build_sea_system.py 1 --gfm "SPS_4,GPS_4" --gfl "TPS_5"
```

## Model mapping

| benchmark component | implementation |
|---|---|
| 6th/5th-order PSS/E generator model (App. I.5) | `GENROU` / `GENSAL` (devices/synchronous.py) |
| ST1A exciters (Fig. 20, Tables 16/26) | `AVRST1A` (transducer + two lead-lags + KA/(1+sTA)) |
| AC1A exciters (Fig. 21, Table 27) | `AVRAC1A` (rotating-exciter integrator + rate feedback) |
| speed-PSS, eqs. (7)-(10), Tables 17-20 | `PSSSEA` (washout + 4 lead-lag slots + complex-zero quadratic, ±0.1 pu output limit) |
| no governor (constant Pm) | `GOVCONST` |
| SVCs (Fig. 22, Table 9) | `SVC` (devices/svc.py) — integrator voltage regulator with Q/Vt droop, closed-form init |
| constant-impedance loads + switched shunts | `StaticZIP` (z-share 1) with iterated voltage calibration |
| generator transformers, taps (Tables 11/13) | `Line` entries, tap on the generator side per Fig. 19 |

All machine parameters are converted to the 100 MVA system base
(`Sn = Sb` convention); published 0 s time constants get a 1 ms floor
(parasitic pole at 1000 rad/s, two decades above the rotor band).

## Pitfalls found and resolved (worth knowing before editing)

1. **q-axis damper sign (eqs. (16)/(25)).** A literal transcription leaves
   the stator's steady state inconsistent (the model then has *no* physical
   equilibrium with `vd = Xq·iq`). Chasing the equilibrium through
   eqs. (17)/(20)/(23) forces `+(X'q−Xa)·iq` resp. `+(Xq−X''q)·iq`; the
   d-axis keeps the printed minus because eq. (18) carries the opposite
   current sign.

2. **Mirror equilibria in the joint init.** The machine equations admit a
   saddle equilibrium at `δ−π` with all EMFs negated. With the class-level
   uniform Newton guess, machines at buses with large voltage angles
   (BPS_2 and all of Area 4 in case 1) converge to the saddle — the
   loadflow still matches, the small-signal spectrum silently grows
   unstable field modes, and time-domain runs diverge after any
   disturbance. `GENROU.finit_guess` seeds every instance from
   the phasor construction `E_q = V + (Rs + jXq)·I` (hook:
   `DeviceRect.finit_guess`).

3. **PSS quadratic sections are not low-pass.** Numerator and denominator
   orders are equal; the published HPS_1 section has a high-frequency gain
   of ~864 (·gain 15.38). Integrate with `abstol ≤ 1e-12`
   (the per-state tolerance is amplified by that factor into the AVR path),
   and keep the published ±0.1 pu output limit in place.

4. **No governors → frequency zero mode.** With constant Pm everywhere and
   no frequency-dependent load, the common rotor speed is a zero
   eigenvalue direction: any disturbance leaves a permanent frequency
   offset (constant-impedance load steps re-equilibrate through the
   voltage profile; constant-power steps would ramp the frequency without
   bound). Cleared faults — like the published transient studies — return
   to the original operating point and are the appropriate default event.

## Validation results (Case 1)

Load flow vs Tables 8/9: generator reactive outputs within 3.5 Mvar, SVC
outputs within 2.6 Mvar (table-rounding scale); slack LPS_3 active power
matches the published schedule.

Rotor modes vs Table 2 (13 electromechanical modes):

| | max \|Δfreq\| | max \|Δζ\| |
|---|---:|---:|
| no PSSs | 0.006 rad/s | < 0.0005 |
| PSSs in service | 0.003 rad/s | < 0.0005 |

i.e. the published Mudpack eigenvalues are reproduced to the printed
precision of the report, with no spurious unstable modes anywhere in the
spectrum.
