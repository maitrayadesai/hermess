# PSS/E reference trajectories

These cases compare hermess against trajectories produced by **PSS/E**, the
industry reference tool. We do not hold a PSS/E license; the trajectories are
the benchmark data committed by the `PowerSimulationsDynamics.jl` (PSID)
project, which generated them by driving PSS/E through its Python API and
uses them to validate its own models. Consuming the same files gives a
direct, if second-hand, comparison against PSS/E, on systems small enough to
transcribe exactly.

## Provenance

Every `<case>/upstream/` folder holds verbatim copies of the PSID benchmark
files (the PSS/E `.raw` network, the `.dyr` dynamic data, and the CSV written
from the PSS/E channel output), together with the upstream BSD-3-Clause
LICENSE. The source repository, commit and SHA-256 checksums are recorded in
each `case.json`. Upstream:

```
https://github.com/Sienna-Platform/PowerSimulationsDynamics.jl
commit dfb56d80b7a019b2d287f1da4d65157d6de134fa, test/benchmarks/psse/
```

How the PSS/E runs were made (from the upstream `python_scripts/`): loads
converted to 100 % constant admittance for both P and Q (`conl`
[0, 100, 0, 100]), generators converted with `cong`, fixed 5 ms output step.
The channel time grid drifts slightly off 5 ms and duplicates the sample at
the switching instant, so the test interpolates the reference on its own time
column onto the hermess grid.

## The cases

- `genrou/` -- ThreeBusMulti (60 Hz): infinite bus at 101 (the PSS/E GENCLS
  with H = 0 behind ZX = 1e-5, transcribed as `StaticInfiniteBus`), the
  saturation-free GENROU at 102, a converted 250 MW load at 103; trip of
  line 101-102 at t = 1 s, 20 s span. The CSV pins the rotor angle (degrees).

The comparison is weaker per case than the ANDES ones (PSS/E published only
the rotor-angle channel), but the source is stronger. `test_reference_traces.py`
asserts the initialized rotor angle and the trajectory infinity norm; PSID's
own acceptance against the same data is 0.1 rad, and the hermess agreement is
recorded in `case.json`.

## Why the other upstream references are not consumed (yet)

Checked against the upstream `.dyr` files at the commit above; each entry
names the feature that would have to be added to hermess first. Adding a
case later means adding a folder, as for the ANDES family.

| upstream case | blocker |
|---|---|
| `GENROU` (base / HIGH_SAT) | machine saturation (S10 = 0.05/1.0); hermess GENROU carries none. The NO_SAT variant is consumed. |
| `GENSAL` | machine saturation (S10 = 0.11, S12 = 0.62); no unsaturated variant upstream. |
| `TGOV1` | the reference TGOV1 has an active lead-lag (T2 = 0.3, T3 = 0.8) that hermess TGOV1 omits, and its machine carries an ESAC1A with transducer (TR = 0.01) and TB = 0.1 lag that AVRAC1A omits. |
| `SEXS` | reference machine saturated (S10 = 0.1, S12 = 0.8) and the SEXS lead-lag is active (TA/TB = 0.4); hermess SEXST is the pure lag. |
| `IEEEST` | same saturated machine and lead-lag SEXS underneath; the stabilizer itself (no-filter variant) would map onto PSSKundur. |
| `EXST1`, others | different, larger test system (`TVC_System_32.raw`) or models hermess does not ship. |

Implementing quadratic saturation (S10/S12) in GENROU/GENSAL would unlock
GENSAL and, with a lead-lag exciter, SEXS and IEEEST. A first-party PSS/E or
PowerFactory run of our own eight three-bus twins needs a departmental
license; the `.raw`/`.dyr` transcriptions here show the shape of that
automation.
