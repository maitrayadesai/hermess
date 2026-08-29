# Changelog

Notable changes to HERMESS. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) as spelled out in `RELEASING.md`.

## [1.3.0] - 2026-08-29

### Added
- Graphical system builder in the GUI: the *Edit* toggle on the topology
  view opens a palette to place buses, connect lines and attach any shipped
  or user-registered device model by clicking on the canvas. The parameter
  forms are generated from the model classes, so every parameter appears
  with the model's own default and description, and the control strategies
  (AVR, governor, PSS, shaft; filter, angle, voltage, inner control, PLL)
  are selected from dropdowns; fields left empty are not written, keeping
  generated files as terse as hand-written ones. Includes a disturbance
  sequence editor, undo/redo, and live validation in a status line.
- Built systems are saved as ordinary system folders (`sim_param.txt` +
  `sim_dist.txt`) that scripts, the CLI and version control handle like any
  hand-written one; parameter values round-trip verbatim. `File > New
  system` starts from a blank canvas, and editing a selected system works
  on a copy. Running an edited system saves it automatically once a save
  location has been chosen.
- The GUI's pre-flight validation checks the summed line charging per bus
  when dynamic lines are enabled, mirroring the setup guard from 1.2.2, so
  the problem surfaces before the model is built.

## [1.2.2] - 2026-08-29

### Fixed
- Running with `line_dyn=True` on a system file without line charging now
  fails at setup with the names of the buses that lack shunt susceptance
  and the remedy, instead of an opaque integrator error at the first step.
  With dynamic lines the charging `b` acts as the bus capacitance, so every
  bus needs a connected branch with `b > 0`; the system-file guide states
  the requirement.

## [1.2.1] - 2026-08-29

### Added
- `Documentation` link in the package metadata, pointing at the rebuilt
  documentation site (https://maitrayadesai.github.io/hermess/): report-style
  pages, a per-family model reference generated from the code, executed
  example notebooks and a public API page.
- Docstrings for the core classes (`Grid`, `GridSim`, `Dae`, `DaeSim`) and
  the entry modules, so `help()` on the model returned by `simulate` is
  informative.

### Changed
- The example notebooks are rebuilt as five studies, one simulator aspect
  each: a first run, scheduled disturbances, the hybrid EMT/RMS network,
  small-signal analysis and parametric sensitivities. They are executed
  during the documentation build, so the shown outputs always match the
  installed version.
- `hermess.utils` is a regular package instead of an implicit namespace
  package.

### Fixed
- Opening a line no longer emits a spurious numpy overflow
  `RuntimeWarning` when the opened branch's impedance is inverted.

## [1.2.0] - 2026-08-28

### Added
- Real command-line interface behind the `hermess` console script and
  `python -m hermess`: `hermess list` prints the runnable systems and
  `hermess run <system>` simulates one, with `--t-end`, `--ts`, `--no-plot`,
  `--small-signal`, `--system-root`, and `--set KEY=VALUE` for any other
  `Config` field. `--help` and `--version` behave as expected.

### Changed
- A bare `hermess` (or `python -m hermess`) now prints the usage instead of
  immediately running the configuration shipped in `hermess/config.py`; that
  demo run is now `hermess run ieee39_conv --small-signal`. In 1.1.0 every
  invocation, including `hermess --help`, started that simulation.

## [1.1.0] - 2026-08-28

First release on PyPI.

### Added
- Cross-tool validation suite spanning five reference families, all compared
  against committed CSV references so no external tool is needed at test time:
  frozen own baselines, ANDES (8 machine/exciter/stabilizer cases), PSS/E
  (GENROU trajectory via the PSID benchmark set), PowerSimulationsDynamics.jl
  (converter, Sauer-Pai machine, five-mass shaft, dynamic network), and PSCAD
  (4 converter cases). Documented in the new validation chapter.
- New models: Marconato synchronous machine, AVRCONST, AVRSimple, IEEEDC1A and
  AVRAC1A exciters, PSSKundur stabilizer, TGTypeII governor, and a
  current-injecting grid-following converter chain with the CascadedDamped,
  VSMAngle, KauraPLL, ReducedPLL, PLLPowerPI, QPowerPI and CurrentPI
  strategies.
- SETPOINT disturbance for changing a device parameter or setpoint at a given
  simulation time.
- Package-level API: `hermess.list_systems`, `hermess.simulate`,
  `hermess.register`.
- Parametric build (`Config(parametric=True)`) exposing
  `dae.parametric_model` for gradient-based studies, tested against finite
  differences.
- Init callback at the initialized operating point.
- GUI pre-flight checks and per-component detail views.
- Uniform model documentation: every device and strategy docstring carries the
  governing equations and a symbol table, with TikZ schematics in the docs.

### Changed
- **Breaking:** the former `GridFollowing` converter is renamed
  `GridSupporting`; `GridFollowing` now denotes the new current-injecting
  chain. Old parameter files using the previous meaning fail with a clear
  error.
- Shipped system folders renamed to a uniform lowercase scheme (`3bus`,
  `ieee39`, `kundur`, `smib`, ...); the old names still resolve and emit a
  `DeprecationWarning`.
- Packaging moved from Poetry to uv (PEP 621 metadata, `uv_build` backend).
  Wheels no longer include the test suite. The `main` console script is
  removed; use `hermess` or `hermess-gui`.

### Fixed
- The loader's registry path dropped strategy kwargs for registered devices,
  and `system_root` did not expand `~`.
- Stale state names in the lazy eigenvalue analysis.
- CSV quoting in two device symbol tables.

## [1.0.0] - 2026-08-22

Initial public release, deposited in the ETH Zurich Research Collection
(doi: [10.3929/ethz-c-000805609](https://doi.org/10.3929/ethz-c-000805609)).
