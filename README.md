<div align="center">

# HERMESS

*Hybrid EMT/RMS Modern Electric power System Simulator*

</div>

---
## About

`hermess` is a dynamic simulation tool for power systems modeled by nonlinear Differential-Algebraic Equations (DAEs).
It integrates the dynamic evolution equations of the components together with the algebraic network equations to produce time-domain trajectories of the bus voltages and of every device's internal states.

This repository is the **simulation-only** build of [`PowerDynamicEstimator`](https://doi.org/10.5905/ethz-1007-842): the dynamic state estimation (DSE) layer has been removed, leaving a focused, self-contained power-system dynamic simulator. The Python package is still importable as `hermess`.

## Features

- Time-domain simulation of nonlinear DAE power system models
- Synchronous machine models (transient and subtransient, including Sauer–Pai formulations) with pluggable AVR, governor, PSS and (multi-mass) shaft strategies
- Grid-forming and grid-following converter (inverter) models with composable control strategies
- Static loads (constant power / impedance / ZIP) and infinite bus
- Quasi-static or fully dynamic (differential) network/line models
- Disturbances: bus/line faults, line switching, and load steps
- Configurable reference-frame handling (centre-of-inertia, single-machine, nominal, distributed)
- Small-signal eigenvalue / participation-factor analysis at the operating point
- Multiple integration schemes (`idas`, `cvodes`, `collocation`, `rk`)
- Supports 50 Hz and 60 Hz systems
- User-defined dynamic and static models can be integrated
- Available as a Python package: `hermess`

## Installation

To get started with `hermess`, follow these steps:
### Option 1: Install from Source (with `venv`)

1. **Clone the repository** and `cd` into it.
2. **Create and activate a virtual environment**:
```bash
python -m venv venv
```
```bash
source venv/bin/activate # On Windows: venv\Scripts\activate
```

3. **Install the package**:
```bash
pip install -e .
```
### Option 2: Install from Source (with `conda`)

1. **Clone the repository** and `cd` into it.

2. **Create the** `conda` **environment**:

```bash
conda env create -f environment.yaml
```
```bash
conda activate hermess
```

## Usage

### Running a simulation

```bash
python -m hermess
```

This runs the simulation defined by the configuration in `./hermess/config.py` and plots the resulting voltage and state trajectories.

## Examples

You can check out the available examples in the `./examples` directory to get started.

## Important Notes

### Parameters

System dynamic and static parameters, including the topology, are specified in the `./hermess/systems` subfolder. You can define the loads, generators, converters, and their characteristics at specific nodes in the power system. The component parameters live in `sim_param.txt` and the disturbances in `sim_dist.txt` within each system folder.

### Simulation Settings

Adjust parameters related to the simulation (time step, end time, integration scheme, reference-frame mode, plotting, small-signal analysis, etc.) in the `./hermess/config.py` file.

### Limitations

- **Injector Limitation**: Currently, the platform supports only one injector per node due to initialization ambiguity. To handle multiple injectors per node, you can create a new node connected via a branch with very small impedance.

## Authors and copyright

© 2024-2026 ETH Zurich

Created by: Milos Katanic (original author of `PowerDynamicEstimator`) and Maitraya Avadhut Desai (simulation-only fork and maintainer).

HERMESS is a simulation-only fork of `PowerDynamicEstimator` (https://doi.org/10.5905/ethz-1007-842); the dynamic state estimation has been removed. See [`AUTHORS`](AUTHORS) and [`CONTRIBUTORS`](CONTRIBUTORS) for the full list of authors and contributors, and [`CONTRIBUTING.md`](CONTRIBUTING.md) if you would like to contribute.

## Acknowledgments

`PowerDynamicEstimator`, from which this build is derived, was developed at the [Power Systems Laboratory](https://psl.ee.ethz.ch/) at [ETH Zurich](https://ethz.ch/en.html), supported as part of [NCCR Automation](https://nccr-automation.ch/), a National Centre of Competence in Research funded by the Swiss National Science Foundation (grant number 51NF40_225155).

## Citing

If you use HERMESS in academic work, please cite the software release in the ETH Research Collection (DOI [10.3929/ethz-c-000805609](https://doi.org/10.3929/ethz-c-000805609), see also [`CITATION.cff`](CITATION.cff)) and the paper describing the underlying models:

> M. Katanic, J. Lygeros, and G. Hug, "Recursive dynamic state estimation for power systems with an incomplete nonlinear DAE model," *IET Generation, Transmission & Distribution*, vol. 18, no. 22, pp. 3657-3668, 2024, doi: [10.1049/gtd2.13308](https://doi.org/10.1049/gtd2.13308).

## License

This software is free software, released by ETH Zurich under the [GNU General Public License v3.0 or later (GPL-3.0-or-later)](https://www.gnu.org/licenses/gpl-3.0.html). See [`LICENSE.txt`](LICENSE.txt) for the full license text. It is distributed WITHOUT ANY WARRANTY; see the license for details.
