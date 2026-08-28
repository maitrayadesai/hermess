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

"""Tests of the GUI's non-Qt logic: the system-file display parser, the
worker-process protocol, the results extraction and the CSV export. None of
these need PySide6, so they run in the core CI."""

import csv
import pickle
import threading

import numpy as np
import pytest

import hermess
from hermess.gui import device_info, sysparse, validation
from hermess.gui.export import export_csv
from hermess.gui.graphlayout import spring_layout
from hermess.gui.worker import RunRequest, simulation_worker, stability_gate
from hermess.results import SimulationResults, extract_results


# ---- sysparse ---------------------------------------------------------------


def test_parse_shipped_3bus_system():
    desc = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus")
    kinds = [e.kind for e in desc.devices]
    assert kinds == ["SynchronousSubtransientSP", "GridForming", "StaticZIP"]
    assert len(desc.lines) == 3
    assert len(desc.bus_inits) == 3
    assert desc.buses() == ["1", "2", "3"]

    # The synchronous machine entry spans a continuation line; parameters from
    # both physical lines must land in the same entry.
    machine = desc.devices[0]
    assert machine.get("idx") == "SG1"
    assert machine.get("H") == "6.50"
    assert machine.get("x_l") == "0.2"  # from the continuation line

    dist = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus_loadstep")
    assert [e.get("type") for e in dist.disturbances] == ["LOAD"]


def test_parse_entries_tolerates_junk():
    entries = sysparse.parse_entries(
        "# comment only\n"
        "\n"
        'Line, bus_i = "1", stray-fragment, bus_j = "2"\n'
    )
    assert len(entries) == 1
    assert entries[0].params == {"bus_i": "1", "bus_j": "2"}


# ---- pre-flight validation --------------------------------------------------


def test_validate_clean_shipped_system():
    desc = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus")
    assert validation.validate(desc, {}) == []


def test_validate_flags_disconnected_network(tmp_path):
    (tmp_path / "sim_param.txt").write_text(
        'Line, bus_i = "1", bus_j = "2", r = 0.01, x = 0.1, b = 0.02\n'
        'Line, bus_i = "3", bus_j = "4", r = 0.01, x = 0.1, b = 0.02\n'
        'BusInit, bus = "1", p = 0, v = 1.0, type = "slack"\n'
    )
    desc = sysparse.parse_system(tmp_path)
    issues = validation.validate(desc, {})
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert "not connected" in errors[0].message
    assert "3" in errors[0].message and "4" in errors[0].message


def test_validate_solver_rules():
    desc = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus")
    # ODE scheme on an algebraic network: hard error.
    issues = validation.validate(desc, {"int_scheme_sim": "cvodes", "line_dyn": False})
    assert any(
        i.severity == "error" and "cvodes" in i.message for i in issues
    )
    # ODE scheme with dynamic lines and only dynamic filters: no solver error.
    issues = validation.validate(desc, {"int_scheme_sim": "rk", "line_dyn": True})
    assert not any("rk" in i.message and i.severity == "error" for i in issues)


def test_validate_solver_rejects_static_filter_devices(tmp_path):
    (tmp_path / "sim_param.txt").write_text(
        'GridForming, idx = "GFM1", bus = "1", filter = "LCL_static", Sn = 100\n'
        'BusInit, bus = "1", p = 0, v = 1.0, type = "slack"\n'
    )
    desc = sysparse.parse_system(tmp_path)
    issues = validation.validate(desc, {"int_scheme_sim": "cvodes", "line_dyn": True})
    assert any(
        i.severity == "error" and "GFM1" in i.message for i in issues
    )
    # The same static filter on a dynamic network is also flagged as incoherent.
    issues = validation.validate(desc, {"line_dyn": True})
    assert any(
        i.severity == "warning" and "quasi-static" in i.message for i in issues
    )


def test_validate_reference_device_and_time_grid():
    desc = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus")
    issues = validation.validate(
        desc, {"omega_mode": "single", "omega_single_idx": "NOPE"}
    )
    assert any(i.severity == "error" and "NOPE" in i.message for i in issues)
    # The shipped 3bus has devices SG1 and GFMI2; a valid idx passes.
    issues = validation.validate(
        desc, {"omega_mode": "single", "omega_single_idx": "SG1"}
    )
    assert not any("omega" in i.message for i in issues)

    issues = validation.validate(desc, {"ts": 2.0, "T_end": 1.0})
    assert any("not smaller" in i.message for i in issues)
    issues = validation.validate(desc, {"ts": -1.0})
    assert any("positive" in i.message for i in issues)


# ---- graph layout -----------------------------------------------------------


def test_spring_layout_deterministic_and_bounded():
    edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    a = spring_layout(4, edges)
    b = spring_layout(4, edges)
    assert np.array_equal(a, b)
    assert a.shape == (4, 2)
    assert a.min() >= 0.0 and a.max() <= 1.0
    # Degenerate sizes must not crash.
    assert spring_layout(0, []).shape == (0, 2)
    assert spring_layout(1, []).shape == (1, 2)


def test_spring_layout_separates_non_neighbors():
    # In a path 0-1-2-3, adjacent nodes must end up closer than the endpoints.
    pos = spring_layout(4, [(0, 1), (1, 2), (2, 3)])
    d01 = np.linalg.norm(pos[0] - pos[1])
    d03 = np.linalg.norm(pos[0] - pos[3])
    assert d01 < d03


# ---- worker protocol --------------------------------------------------------


class _ListConn:
    """In-process stand-in for the worker's pipe connection."""

    def __init__(self):
        self.messages = []

    def send(self, msg):
        self.messages.append(msg)

    def close(self):
        pass


@pytest.fixture(scope="module")
def worker_messages():
    conn = _ListConn()
    request = RunRequest(
        system="3bus_loadstep",
        overrides={"T_end": 0.5, "small_signal_analysis": True},
    )
    simulation_worker(conn, request, threading.Event())
    return conn.messages


def test_worker_completes_with_results(worker_messages):
    kinds = [m[0] for m in worker_messages]
    assert kinds[-1] == "done"
    assert "progress" in kinds
    results = worker_messages[-1][1]
    assert isinstance(results, SimulationResults)
    assert results.system == "3bus_loadstep"
    assert set(results.voltage) == {"1", "2", "3"}
    assert results.small_signal is not None
    assert results.small_signal.eigenvalues.size > 0
    assert results.power_flow_bus is not None
    assert results.config["T_end"] == 0.5
    # The container must cross a process boundary.
    assert pickle.loads(pickle.dumps(results)).system == "3bus_loadstep"


def test_worker_progress_monotonic(worker_messages):
    fractions = [m[1] for m in worker_messages if m[0] == "progress"]
    assert fractions == sorted(fractions)
    assert fractions[0] == 0.0
    assert fractions[-1] == 1.0


def test_worker_cancels_immediately():
    conn = _ListConn()
    event = threading.Event()
    event.set()  # cancel before the time stepping starts
    simulation_worker(
        conn, RunRequest(system="3bus_loadstep", overrides={"T_end": 0.5}), event
    )
    assert conn.messages[-1] == ("cancelled",)


def test_worker_reports_stability(worker_messages):
    stability = [m for m in worker_messages if m[0] == "stability"]
    assert len(stability) == 1
    payload = stability[0][1]
    assert payload["n_modes"] > 0
    assert payload["unstable"] == []  # the 3bus operating point is stable


class _FakeDae:
    def __init__(self, real_parts):
        self.eigenvalues = np.array([r + 0j for r in real_parts])
        self.modes = [
            {
                "id": i + 1,
                "eig": complex(r, 3.0),
                "freq_hz": 0.5,
                "zeta": -0.01 if r > 0 else 0.5,
                "dominant": [("SM@1:omega", 0.8)],
            }
            for i, r in enumerate(real_parts)
        ]


class _DuplexConn(_ListConn):
    """List-collecting conn that also answers recv() from a scripted queue."""

    def __init__(self, replies=()):
        super().__init__()
        self.replies = list(replies)

    def recv(self):
        return self.replies.pop(0)


def test_stability_gate_stable_passes_without_blocking():
    conn = _DuplexConn()  # recv() would raise; must not be called
    result = stability_gate(conn, threading.Event(), _FakeDae([-1.0, -2.0]))
    assert result is None
    assert conn.messages[0][0] == "stability"
    assert conn.messages[0][1]["unstable"] == []


def test_stability_gate_unstable_waits_for_decision():
    proceed = _DuplexConn(replies=[("continue", True)])
    assert stability_gate(proceed, threading.Event(), _FakeDae([0.5, -1.0])) is None
    assert proceed.messages[0][1]["unstable"][0]["id"] == 1

    refuse = _DuplexConn(replies=[("continue", False)])
    assert stability_gate(refuse, threading.Event(), _FakeDae([0.5])) is False


def test_stability_gate_skips_without_eigen_data():
    conn = _DuplexConn()

    class NoAnalysis:
        eigenvalues = None

    assert stability_gate(conn, threading.Event(), NoAnalysis()) is None
    assert conn.messages == []


# ---- device info ------------------------------------------------------------


def test_class_descriptions_resolve():
    text = device_info.class_description("GridForming")
    assert text and "grid" in text.lower()
    assert device_info.class_description("SynchronousSubtransientSP")
    assert device_info.class_description("NoSuchModel") is None


def test_schematic_mapping():
    machine = sysparse.Entry(
        "GENROU", {"idx": "SG1", "avr": "SEXST", "governor": "TGOV1", "pss": "PSSKundur"}
    )
    names = [f for _c, f in device_info.schematics_for(machine)]
    assert names == [
        "sm_composition.svg",
        "avr_sexst.svg",
        "gov_tgov1.svg",
        "pss.svg",
    ]
    gfl = sysparse.Entry("GridSupporting", {"idx": "GFL1"})
    names = [f for _c, f in device_info.schematics_for(gfl)]
    assert "conv_gfl.svg" in names and "pll_srf.svg" in names
    assert device_info.schematics_for(sysparse.Entry("StaticZIP", {})) == []
    # Every mapped file exists in the docs tree of a source checkout.
    root = device_info.schematics_dir()
    assert root is not None
    for entry in (machine, gfl):
        for _caption, filename in device_info.schematics_for(entry):
            assert (root / filename).exists(), filename


def test_worker_reports_errors():
    conn = _ListConn()
    simulation_worker(
        conn, RunRequest(system="no_such_system"), threading.Event()
    )
    final = conn.messages[-1]
    assert final[0] == "error"
    assert final[1] == "FileNotFoundError"


# ---- results extraction -----------------------------------------------------


def test_extract_results_from_simulate():
    dae = hermess.simulate("3bus_loadstep", T_end=0.5)
    results = extract_results(dae)
    assert results.t.shape == (dae.nts,)
    assert np.allclose(np.abs(results.voltage["1"][0]), 1.0, atol=0.1)
    units = {d.unit for d in results.devices}
    assert {"SG1", "GFMI2"} <= units
    machine = next(d for d in results.devices if d.unit == "SG1")
    assert "omega" in machine.states
    assert machine.states["omega"].shape == (dae.nts,)


# ---- CSV export -------------------------------------------------------------


def test_export_csv(tmp_path):
    results = SimulationResults(
        system="demo",
        t=np.array([0.0, 0.1, 0.2]),
        voltage={"1": np.array([1.0 + 0j, 1.0 + 0j, 0.9 + 0j])},
        power={},
        config={"T_end": 0.2},
        hermess_version="1.0.0",
        created="2026-08-25T12:00:00",
    )
    target = tmp_path / "demo.csv"
    sidecar = export_csv(target, results, [("V1", results.voltage_magnitude("1"))])

    with open(target) as fid:
        rows = list(csv.reader(fid))
    assert rows[0] == ["t", "V1"]
    assert [float(x) for x in rows[3]] == [0.2, 0.9]
    assert sidecar.exists()
    assert "demo" in sidecar.read_text()
