# Changelog

Notable changes to HERMESS. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) as spelled out in `RELEASING.md`.

## [1.7.2] - 2026-09-04

### Fixed
- Python 3.14 compatibility: the faulted-line admittance no longer passes
  complex values to `complex()` (deprecated in 3.14, an error later), the
  participation heatmap uses `Colormap.with_extremes` instead of the
  deprecated `set_bad`, and the CLI tests keep argparse help uncolored.
  Results are unchanged.

## [1.7.1] - 2026-09-03

### Changed
- The systems shipped with the package are read-only for every helper
  that writes system files. `hermess.analysis.set_param`,
  `set_disturbances` and `copy_system` (also with `overwrite=True`, before
  any deletion) and the GUI's `SystemDocument.save` raise a
  `PermissionError` pointing to `copy_system` when the target resolves to
  a folder under `hermess.SYSTEMS_DIR`; the GUI's post-save
  `sim_settings.txt` offer skips such folders. The SEA benchmark generator
  scripts (`hermess/systems/sea14gen/*.py`), which write their case folders
  next to themselves, are no longer packaged in the wheel.

### Fixed
- `DaeSim.eigenvalue_analysis` (and so `hermess.analysis.small_signal`,
  `modal_table`, `participation_table`, `state_matrix` and `plot_modes`)
  called after a run with a disturbance linearized the post-disturbance
  equations at the pre-disturbance operating point, which is not an
  equilibrium of them: the modes moved and a spurious real eigenvalue near
  zero appeared with an "operating point seems unstable" log. The run now
  snapshots the initial equation build at the initial operating point
  before the stepping, and the analysis always uses it, so a post-run
  analysis equals the pre-run one (`small_signal_analysis=True`) and the
  disturbance-free run of the same system. Trajectories are unchanged.

## [1.7.0] - 2026-09-01

All of this release grew out of one first-time Windows test drive by an
external user; thanks for the reports.

### Added
- Per-system defaults: an optional `sim_settings.txt` in a system folder
  carries the configuration the system needs to run out of the box (one
  `field = value` per line, JSON values, `Config` field names).
  `hermess.simulate`, the command line and the GUI apply it between the
  package defaults and explicit arguments, so anything passed explicitly
  still wins. The 25 shipped networks whose buses carry no shunt
  susceptance now default to the quasi-static network instead of failing
  the dynamic-network guard on a bare run.
- The GUI's disturbance editor explains itself: every field is labeled
  with the core's meaning and units, required fields are enforced per
  event type, optional fields show their defaults, and the equivalent
  `sim_dist.txt` line is displayed. The tables come from the core
  (`Disturbance._EVENT_FIELDS`), so editor and simulator cannot drift.
- Saving a built network whose lines carry no charging offers once to
  write a `sim_settings.txt` with `line_dyn = false` next to it.

### Changed
- Disturbance rows are validated when the system loads: an unknown type,
  a misspelled field or a missing required field stops the run with the
  fields, units and an example row for that type, instead of the stray
  field being silently ignored.
- An `IDACalcIC` convergence failure under dynamic lines raises a
  readable message, separately for the initialization at t = 0 and for
  the restart after a disturbance, with the raw solver error attached as
  the cause.

### Fixed
- The built-in result plots (the default `hermess run` path) and the
  participation heatmap used matplotlib APIs removed in 3.9
  (`cm.get_cmap`, `plt.get_cmap`) and crashed on any current
  matplotlib. The plot path now has a smoke test.
- The unknown-disturbance branch called `logging.ERROR(...)` (an int)
  and would have crashed if ever reached.
- The installation guide covers the Windows case where the `hermess`
  command is not on `PATH` after a user-site install.

## [1.6.1] - 2026-08-31

### Changed
- Relaxed the dependency floors to what the suite actually requires:
  `numpy>=2.0` (from 2.2.4), `pandas>=2.2.2` (from 2.2.3, the first
  numpy-2-compatible pandas) and `matplotlib>=3.8.4` (from 3.8.3, which
  declares `numpy<2` and can never coexist with the required numpy). The
  full test suite passes against exactly this oldest stack. On
  environments with a preinstalled scientific stack (e.g. Google Colab),
  `pip install hermess` now leaves numpy and pandas untouched instead of
  upgrading them under a live kernel.
- CasADi's numpy-mode `FutureWarning` (casadi issue #2959, printed at every
  first simulation per call site on casadi 3.7) is silenced by explicitly
  keeping the legacy behavior, `GlobalOptions.setNumpyMode(-1)`: results are
  bit-identical, only the notice goes away. The migration to the
  casadi-aware numpy mode remains deliberate future work.

## [1.6.0] - 2026-08-30

### Added
- `hermess.analysis`, the post-processing and notebook workflow as a public
  API: signal addressing (`owner:quantity` with globs, lists, dicts and
  device objects), pandas tables and CSV export (`signals`, `get`,
  `to_dataframe`, `to_csv`, `metrics`, `summary`), one-line plotting
  including the single-line system diagram (`plot`, `plot_states`,
  `compare`, `plot_frequency`, `plot_voltages`, `plot_active_power`,
  `plot_modes`, `plot_system`, `mark_events`), small-signal tables
  (`small_signal`, `modal_table`, `participation_table`, `state_matrix`,
  `power_flow_table`), raw accessors (`get_device`, `frequency_hz`,
  `bus_voltage`, `state_index`, `device_label`) and text-level system-file
  helpers (`copy_system`, `show_system`, `set_param`, `set_disturbances`,
  `read_events`). One star-import gives a notebook the whole workflow. The
  plots follow the active matplotlib style.
- Quiet runs: the `show_progress` configuration field turns the progress
  bar off, and `hermess.simulate(..., quiet=True)` is the shorthand (no
  progress bar, warnings-only logging).
- The returned model carries the scheduled disturbances as `dae.events`
  (`(time, type, where)` tuples) and the resolved configuration as
  `dae.cfg`.

## [1.5.1] - 2026-08-30

### Fixed
- Derived outputs (`omega_c`, `omega_pll`) are reconstructed correctly
  across a `SETPOINT` disturbance. The event bakes the new setpoint into
  the rebuilt expressions as a numeric constant, and the post-run
  evaluation used those final expressions for the whole run, shifting the
  pre-event segment (by `Kp * (Pref_new - Pref_old)` for a grid-forming
  converter's frequency). Each stored segment is now evaluated with the
  expressions of its own equation build. Affects `SimulationResults` and
  the GUI signal tree; the stored state and algebraic trajectories were
  always correct.
- `progress_callback` and `init_callback` cancel the run on any falsy
  return other than `None`. A callback returning numpy bools (natural
  when comparing against the reported fraction) previously failed the
  exact `is False` test and the cancellation was silently ignored.
- The angle-source module docstring no longer lists the shipped `VSM`
  strategy as future work.

## [1.5.0] - 2026-08-30

### Added
- Device-level algebraic signals in the time-domain view: the private
  algebraic variables (e.g. the quasi-static filter quantities) and the
  outputs the models expose symbolically, such as a grid-forming
  converter's frequency `omega_c` (or a PLL's `omega_pll`), evaluated over
  the stored trajectories and marked "(algebraic)" in the signal tree.
  `SimulationResults` carries them per device unit.
- Topology view controls: *Fit* (also the space bar) refits the diagram
  while keeping the manual arrangement, and a *Labels* toggle shows or
  hides the device names; dense systems start decluttered, with glyph
  hover naming the unit.

### Changed
- The GUI has a refreshed visual design (underline tabs, toolbar icons,
  filled active states, visible splitter handles) with no new
  dependencies, and everyday details were polished: the window title names
  the shown system with an unsaved marker, the progress bar is
  indeterminate while the model builds, checked signals carry color chips
  matching their curves, and the options dialog documents every field
  with tooltips.
- Large one-line diagrams lay out without overlaps: minimum node spacing
  is enforced, device glyphs and labels go into each bus's locally empty
  sector, and the bus number takes the opposite side.
- Zooming on long large-amplitude records is smooth: traces beyond 20k
  points render with a thin aliased pen (measured ~270x faster per zoom
  step), visually indistinguishable at that density.

### Fixed
- Clicking an eigenvalue in the small-signal map no longer raises a numpy
  truthiness error when the click selects nothing.

## [1.4.0] - 2026-08-29

### Added
- Lines are editable in the builder: double-clicking one opens its
  parameter form in edit mode, and a detail pop-up with the pi-section
  schematic in view mode.
- *Save…* and *Save as…* buttons in the builder palette. *Save as…* forks
  the current state into a new folder (suggested next to the original) so a
  variant can be kept for comparison without touching the system it started
  from; choosing a folder that already holds a different system asks before
  replacing it.
- A *Clear canvas* button that empties the edited system after a
  confirmation and stays undoable, plus undo/redo shortcuts with proper
  enabled states, and Escape to abandon a half-drawn line.
- The validation enforces one injector per bus as an error (with the
  low-impedance-branch remedy) and flags unproven device pairings and
  duplicate unit identifiers, live in the builder's status line and at
  pre-flight.

### Changed
- The builder names actual defaults instead of generic placeholders: the
  strategy dropdowns show what the model default resolves to, the unit
  identifier field shows the name that will be generated, and disturbance
  fields show their defaults.
- Completing a line, device or delete action drops the tool back to *Move*
  so stray clicks stay inert, and the mouse cursor indicates the active
  tool. While a document is edited, the systems browser is deselected and
  its inspector emptied, restored when edit mode ends.

### Fixed
- Toggling edit mode off with unsaved changes now asks (save, discard or
  keep editing) instead of dropping them silently.

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
