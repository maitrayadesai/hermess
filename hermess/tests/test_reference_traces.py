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

"""Cross-tool validation against committed ANDES reference trajectories.

Unlike the baseline tests (which pin our own past output), these cases compare
against a tool that is not ours: each folder under ``references/andes/``
carries a small hermess system, the script that produced the ANDES reference
(``generate.py``), the committed reference data (``reference.csv`` +
``reference_meta.json``) and the comparison spec (``case.json``). Adding a
model means adding a folder; this module discovers and asserts them all.

Three things are checked per case, in order of strength:

1. the initialized operating point (states, setpoints, power-flow voltages),
2. the eigenvalues of the linearization at that point (matched pairwise), and
3. the post-disturbance trajectory (infinity norm per quantity; the algebraic
   quantities skip the samples at the switching instant, where the two tools
   sample opposite sides of the discontinuity).

ANDES itself is NOT needed here: the tests read the committed CSV/JSON.
Regeneration is a deliberate act (see ``references/README.md``). Every
assertion message reports the achieved error next to the tolerance so a future
tightening is informed by data.

A second family under ``references/psse/`` compares against trajectories that
PSS/E produced (the benchmark data of PowerSimulationsDynamics.jl, committed
there with provenance; see ``references/psse/README.md``). Those references
pin only the rotor-angle channel, so the PSS/E cases assert the initialized
rotor angle and its trajectory; the PSS/E channel grid drifts slightly off
the 5 ms step, so the reference is interpolated on its own time column.

A third family under ``references/psid/`` compares against
PowerSimulationsDynamics.jl (Julia) run locally, the counterpart with the
matching six-state LCL converter, Sauer-Pai machine and multi-mass shaft;
each case carries the generate.jl that produced it and asserts the same
three levels as the ANDES family (see ``references/psid/README.md``).
"""

import json
from pathlib import Path

import numpy as np
import pytest

from hermess.config import config
from hermess.run import run

REFERENCE_ROOT = Path(__file__).parent / "references" / "andes"
PSSE_ROOT = Path(__file__).parent / "references" / "psse"
PSID_ROOT = Path(__file__).parent / "references" / "psid"

CASES = sorted(p.name for p in REFERENCE_ROOT.iterdir() if (p / "case.json").is_file())
PSSE_CASES = sorted(
    p.name for p in PSSE_ROOT.iterdir() if (p / "case.json").is_file()
)
PSID_CASES = sorted(
    p.name for p in PSID_ROOT.iterdir() if (p / "case.json").is_file()
)

# The shared run configuration of every reference case; a case.json may carry
# a "config" dict of overrides (the PSS/E cases run at 60 Hz over 20 s).
BASE_CONFIG = dict(
    testsystemfile="system",
    omega_mode="nom",
    fn=50,
    Sb=100,
    ts=0.005,
    T_start=0.0,
    T_end=10.0,
    int_scheme_sim="idas",
    int_scheme_sim_options={
        "abstol": 1e-9,
        "reltol": 1e-9,
        "max_num_steps": 100000,
    },
    plot=False,
    plot_voltage=False,
    plot_diff=False,
    log_level="WARNING",
    incl_lim=False,
    line_dyn=False,
    skip_disturance=False,
    debug_check_init=False,
    print_power_flow=False,
    small_signal_analysis=True,
    small_signal_figures=False,
)


def _run_hermess(case_dir: Path, overrides: dict):
    cfg = config.updated(**{**BASE_CONFIG, **overrides, "system_root": case_dir})
    return run(cfg)


def _load_case(name: str):
    case_dir = REFERENCE_ROOT / name
    spec = json.loads((case_dir / "case.json").read_text())
    meta = json.loads((case_dir / "reference_meta.json").read_text())
    csv = np.genfromtxt(case_dir / "reference.csv", delimiter=",", names=True)
    return case_dir, spec, meta, csv


@pytest.fixture(scope="module")
def reference_runs():
    """Run each hermess case once; all three checks share the run."""
    runs: dict = {}

    def _get(name: str):
        if name not in runs:
            case_dir, spec, meta, csv = _load_case(name)
            sim = _run_hermess(case_dir, spec.get("config", {}))
            runs[name] = (sim, spec, meta, csv)
        return runs[name]

    return _get


@pytest.fixture(scope="module")
def psse_runs():
    """Run each PSS/E-family hermess case once; both checks share the run."""
    runs: dict = {}

    def _get(name: str):
        if name not in runs:
            case_dir = PSSE_ROOT / name
            spec = json.loads((case_dir / "case.json").read_text())
            raw = np.loadtxt(case_dir / spec["reference_csv"], delimiter=",")
            t_ref, delta_ref = raw[:, 0], raw[:, 1]
            if spec.get("delta_unit") == "degrees":
                delta_ref = np.deg2rad(delta_ref)
            sim = _run_hermess(case_dir, spec.get("config", {}))
            runs[name] = (sim, spec, t_ref, delta_ref)
        return runs[name]

    return _get


def _machine(sim):
    """The (single) synchronous-machine device of the case and its instance
    order (insertion order of the idx map, matching the reference columns)."""
    machines = [
        d for d in sim.device_list
        if getattr(d, "_type", "") == "Synchronous_machine"
    ]
    assert len(machines) == 1
    sg = machines[0]
    gens = sorted(sg.int, key=sg.int.get)
    return sg, gens


@pytest.mark.parametrize("case", CASES)
def test_initial_conditions_match_reference(case, reference_runs):
    sim, spec, meta, _ = reference_runs(case)
    sg, _gens = _machine(sim)
    tol = spec["tolerances"]["initial"]

    errors = {}
    # initial_maps: {reference section: {hermess name: reference name}}; a
    # hermess name is a state (compared from xinit) or a setpoint solved by
    # the initialization (compared from the device attribute). A mapping value
    # may be {"ref": name, "scale": s} when the tools put a gain in different
    # places (e.g. our Rf = KF/TF * their WF_x).
    for section, mapping in spec["initial_maps"].items():
        for ours, theirs in mapping.items():
            if isinstance(theirs, dict):
                ref = np.asarray(meta["initial"][section][theirs["ref"]])
                ref = ref * theirs["scale"]
                label = f"{section}.{theirs['scale']:.4g}*{theirs['ref']}"
            else:
                ref = np.asarray(meta["initial"][section][theirs])
                label = f"{section}.{theirs}"
            got = (
                np.asarray(sg.xinit[ours])
                if ours in sg.states
                else np.asarray(getattr(sg, ours))
            )
            errors[f"{ours} vs {label}"] = np.abs(got - ref).max()
    v0 = np.array([np.hypot(*sim.grid.yinit[str(b)]) for b in sim.grid.buses])
    errors["power-flow |V|"] = np.abs(v0 - np.asarray(meta["initial"]["bus_v"])).max()

    worst = max(errors.values())
    assert worst <= tol, (
        f"{case}: initialized operating point differs from ANDES by {worst:.3e} "
        f"(tolerance {tol:.0e}); per quantity: "
        + ", ".join(f"{k} {v:.2e}" for k, v in errors.items())
    )


@pytest.mark.parametrize("case", CASES)
def test_eigenvalues_match_reference(case, reference_runs):
    sim, spec, meta, _ = reference_runs(case)
    mu = np.array([complex(re, im) for re, im in meta["eigenvalues"]])

    drop = spec.get("drop_reference_eigenvalues")
    if drop:
        near = complex(*drop["near"])
        for _ in range(drop["count"]):
            mu = np.delete(mu, int(np.argmin(np.abs(mu - near))))

    # Reductions can leave the reference with decoupled artifact modes that
    # have no hermess counterpart (documented per case in generate.py); they
    # stay unmatched below and only their count is pinned here.
    extra = spec.get("allow_extra_reference_eigenvalues", 0)
    lam = np.asarray(sim.eigenvalues)
    assert lam.size + extra == mu.size, (
        f"{case}: {lam.size} hermess eigenvalues vs {mu.size} reference ones "
        f"(expected {extra} unmatched reference artifacts)"
    )

    # Greedy nearest-neighbour pairing; each reference eigenvalue used once.
    abs_tol = spec["tolerances"]["eig_abs"]
    rel_tol = spec["tolerances"]["eig_rel"]
    used = np.zeros(mu.size, dtype=bool)
    worst = (0.0, 0j)
    for lv in lam:
        d = np.abs(mu - lv)
        d[used] = np.inf
        k = int(np.argmin(d))
        used[k] = True
        scaled = d[k] / (1.0 + np.abs(mu[k]) * rel_tol / abs_tol)
        if scaled > worst[0]:
            worst = (scaled, mu[k])
    assert worst[0] <= abs_tol, (
        f"{case}: eigenvalue nearest to reference {worst[1]:.4f} differs by "
        f"{worst[0]:.3e} (tolerance {abs_tol:.0e} + {rel_tol:.0e}*|mu|)"
    )


@pytest.mark.parametrize("case", CASES)
def test_trajectories_match_reference(case, reference_runs):
    sim, spec, meta, csv = reference_runs(case)
    sg, gens = _machine(sim)
    tols = spec["tolerances"]["traj"]

    nts = min(len(csv["t"]), sim.nts)
    t = np.arange(nts) * 0.005
    assert np.allclose(csv["t"][:nts], t)
    # The two tools sample opposite sides of a switching discontinuity, so the
    # algebraic quantities skip the samples at the events; states are
    # continuous and compared everywhere.
    keep = np.ones(nts, dtype=bool)
    for ev in spec["event_times"]:
        keep &= np.abs(t - ev) > 0.0075

    errors: dict[str, tuple[float, float]] = {}

    def check(kind: str, label: str, ours: np.ndarray, theirs: np.ndarray,
              algebraic: bool) -> None:
        diff = np.abs(ours[:nts] - theirs[:nts])
        err = diff[keep].max() if algebraic else diff.max()
        errors[label] = (err, tols[kind])

    for k, g in enumerate(gens):
        check("omega", f"omega_{g}", sg.xf["omega"][k], csv[f"omega_{g}"], False)
        check("delta", f"delta_{g}", sg.xf["delta"][k], csv[f"delta_{g}"], False)
    for b in sim.grid.buses:
        vh = np.hypot(*sim.grid.yf[str(b)])
        check("v", f"v_{b}", vh, csv[f"v_{b}"], True)
    for k, g in enumerate(gens):
        bus = str(sg.bus[k])
        check("p", f"p_{g}", sim.grid.sf[bus][0], csv[f"p_{g}"], True)
        check("q", f"q_{g}", sim.grid.sf[bus][1], csv[f"q_{g}"], True)
    # extra_trajectories: {hermess variable: reference column prefix} for the
    # controller quantities a case additionally pins (governor and exciter
    # states from xf; device-private algebraics such as the PSS output from
    # yf_int, which skip the switching samples like every algebraic).
    for ours, col in spec.get("extra_trajectories", {}).items():
        algebraic = ours not in sg.xf
        source = sg.yf_int if algebraic else sg.xf
        for k, g in enumerate(gens):
            check(col, f"{col}_{g}", source[ours][k], csv[f"{col}_{g}"], algebraic)

    failed = {k: v for k, v in errors.items() if v[0] > v[1]}
    achieved = ", ".join(f"{k} {e:.2e}" for k, (e, _) in errors.items())
    assert not failed, (
        f"{case}: trajectory differs from ANDES beyond tolerance: "
        + ", ".join(f"{k} {e:.3e} > {tol:.0e}" for k, (e, tol) in failed.items())
        + f"; all achieved errors: {achieved}"
    )


@pytest.fixture(scope="module")
def psid_runs():
    """Run each PSID-family hermess case once; all three checks share the run."""
    runs: dict = {}

    def _get(name: str):
        if name not in runs:
            case_dir = PSID_ROOT / name
            spec = json.loads((case_dir / "case.json").read_text())
            meta = json.loads((case_dir / "reference_meta.json").read_text())
            csv = np.genfromtxt(case_dir / "reference.csv", delimiter=",", names=True)
            sim = _run_hermess(case_dir, spec.get("config", {}))
            runs[name] = (sim, spec, meta, csv)
        return runs[name]

    return _get


def _psid_device(sim, spec):
    return [
        d for d in sim.device_list if type(d).__name__ == spec["device_class"]
    ][0]


@pytest.mark.parametrize("case", PSID_CASES)
def test_psid_initial_conditions_match_reference(case, psid_runs):
    sim, spec, meta, _csv = psid_runs(case)
    dev = _psid_device(sim, spec)
    tol = spec["tolerances"]["initial"]
    # The t = 0 trajectory sample is the initialized state on both sides.
    errors = {
        ours: abs(float(dev.xf[ours][0, 0]) - float(meta["initial"][col]))
        for ours, col in spec["state_columns"].items()
    }
    worst = max(errors.values())
    assert worst <= tol, (
        f"psid/{case}: initialized states differ from PSID by {worst:.3e} "
        f"(tolerance {tol:.0e}); per state: "
        + ", ".join(f"{k} {v:.2e}" for k, v in errors.items())
    )


@pytest.mark.parametrize("case", PSID_CASES)
def test_psid_eigenvalues_match_reference(case, psid_runs):
    sim, spec, meta, _csv = psid_runs(case)
    mu = np.array([complex(re, im) for re, im in meta["eigenvalues"]])
    extra = spec.get("allow_extra_reference_eigenvalues", 0)
    lam = np.asarray(sim.eigenvalues)
    assert lam.size + extra == mu.size, (
        f"psid/{case}: {lam.size} hermess eigenvalues vs {mu.size} reference "
        f"ones (expected {extra} unmatched reference artifacts)"
    )
    abs_tol = spec["tolerances"]["eig_abs"]
    rel_tol = spec["tolerances"]["eig_rel"]
    used = np.zeros(mu.size, dtype=bool)
    worst = (0.0, 0j)
    for lv in lam:
        d = np.abs(mu - lv)
        d[used] = np.inf
        k = int(np.argmin(d))
        used[k] = True
        scaled = d[k] / (1.0 + np.abs(mu[k]) * rel_tol / abs_tol)
        if scaled > worst[0]:
            worst = (scaled, mu[k])
    assert worst[0] <= abs_tol, (
        f"psid/{case}: eigenvalue nearest to reference {worst[1]:.4f} differs "
        f"by {worst[0]:.3e} (tolerance {abs_tol:.0e} + {rel_tol:.0e}*|mu|)"
    )


@pytest.mark.parametrize("case", PSID_CASES)
def test_psid_trajectories_match_reference(case, psid_runs):
    sim, spec, meta, csv = psid_runs(case)
    dev = _psid_device(sim, spec)
    tols = spec["tolerances"]["traj"]
    default_tol = spec["tolerances"]["traj_default"]

    nts = min(len(csv["t"]), sim.nts)
    t = np.arange(nts) * 0.005
    assert np.allclose(csv["t"][:nts], t)
    keep = np.ones(nts, dtype=bool)
    for ev in spec["event_times"]:
        keep &= np.abs(t - ev) > 0.0075

    errors: dict[str, tuple[float, float]] = {}
    for ours, col in spec["state_columns"].items():
        err = np.abs(dev.xf[ours][0, :nts] - csv[col][:nts]).max()
        errors[col] = (err, tols.get(col, default_tol))
    for bus, col in spec["voltage_columns"].items():
        vh = np.hypot(*sim.grid.yf[bus])[:nts]
        err = np.abs(vh - csv[col][:nts])[keep].max()
        errors[col] = (err, tols.get(col, default_tol))

    failed = {k: v for k, v in errors.items() if v[0] > v[1]}
    achieved = ", ".join(f"{k} {e:.2e}" for k, (e, _) in errors.items())
    assert not failed, (
        f"psid/{case}: trajectory differs from PSID beyond tolerance: "
        + ", ".join(f"{k} {e:.3e} > {tol:.0e}" for k, (e, tol) in failed.items())
        + f"; all achieved errors: {achieved}"
    )


@pytest.mark.parametrize("case", PSSE_CASES)
def test_psse_initial_rotor_angle_matches_reference(case, psse_runs):
    sim, spec, _t_ref, delta_ref = psse_runs(case)
    sg, _gens = _machine(sim)
    tol = spec["tolerances"]["delta_init"]
    err = abs(float(sg.xinit["delta"][0]) - float(delta_ref[0]))
    assert err <= tol, (
        f"psse/{case}: initialized rotor angle differs from PSS/E by "
        f"{err:.3e} rad (tolerance {tol:.0e})"
    )


@pytest.mark.parametrize("case", PSSE_CASES)
def test_psse_rotor_angle_trajectory_matches_reference(case, psse_runs):
    sim, spec, t_ref, delta_ref = psse_runs(case)
    sg, _gens = _machine(sim)
    tol = spec["tolerances"]["delta_traj"]
    t_h = np.arange(sim.nts) * 0.005
    ref = np.interp(t_h, t_ref, delta_ref)
    err = np.abs(sg.xf["delta"][0] - ref).max()
    assert err <= tol, (
        f"psse/{case}: rotor-angle trajectory differs from PSS/E by "
        f"{err:.3e} rad inf-norm (tolerance {tol:.0e}); for scale, the "
        f"upstream project's own acceptance against this data is 1e-1 rad"
    )
