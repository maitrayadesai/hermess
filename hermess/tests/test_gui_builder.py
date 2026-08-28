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

"""Tests of the builder's non-Qt substance: the system document, its
serializer, the parameter metadata, and the proof that a document built
through the API produces a system the simulator actually runs."""

import numpy as np

import hermess
from hermess.gui import param_meta, sysparse, validation
from hermess.gui.sysdoc import LINE_DEFAULTS, SystemDocument


# ---- document operations ----------------------------------------------------


def test_blank_document_bus_and_naming():
    doc = SystemDocument.blank()
    assert doc.add_bus() == "1"
    assert doc.add_bus() == "2"
    types = [e.get("type") for e in doc.desc.bus_inits]
    assert types == ["slack", "PQ"]  # first bus becomes the slack
    assert doc.next_idx("GridForming") == "GFM1"
    doc.add_device("GridForming", "2", {"Sn": "100"})
    assert doc.next_idx("GridForming") == "GFM2"
    assert doc.next_idx("GENROU") == "SG1"
    assert doc.dirty


def test_remove_bus_cascades():
    doc = SystemDocument.blank()
    doc.add_bus()
    doc.add_bus()
    doc.add_line("1", "2")
    doc.add_device("StaticZIP", "2")
    doc.add_disturbance({"time": "1.0", "type": "LOAD", "bus": "2", "p_delta": "5"})
    doc.remove_bus("2")
    assert doc.desc.buses() == ["1"]
    assert doc.desc.lines == []
    assert doc.desc.devices == []
    assert doc.desc.disturbances == []


def test_undo_redo():
    doc = SystemDocument.blank()
    doc.add_bus()
    doc.add_bus()
    assert doc.desc.buses() == ["1", "2"]
    doc.undo()
    assert doc.desc.buses() == ["1"]
    doc.redo()
    assert doc.desc.buses() == ["1", "2"]
    doc.undo()
    doc.add_bus()  # a new edit clears the redo history
    assert not doc.can_redo()


def test_set_businit_creates_and_updates():
    doc = SystemDocument.blank()
    doc.add_bus()
    doc.set_businit("1", {"p": "-50", "v": "1.02", "type": "PV"})
    entry = doc.desc.bus_inits[0]
    assert entry.get("type") == "PV" and entry.get("p") == "-50"
    doc.set_businit("9", {"type": "PQ"})  # unknown bus: entry is created
    assert doc.desc.bus_inits[-1].get("bus") == "9"


# ---- serialization ----------------------------------------------------------


def test_serializer_round_trip(tmp_path):
    original = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus_loadstep")
    doc = SystemDocument.load(hermess.SYSTEMS_DIR / "3bus_loadstep")
    folder = doc.save(tmp_path / "roundtrip")
    reparsed = sysparse.parse_system(folder)

    assert [e.kind for e in reparsed.devices] == [e.kind for e in original.devices]
    for before, after in zip(
        original.devices + original.lines + original.bus_inits + original.disturbances,
        reparsed.devices + reparsed.lines + reparsed.bus_inits + reparsed.disturbances,
    ):
        assert after.params == before.params  # values round-trip verbatim
    assert not doc.dirty


def test_serializer_quoting(tmp_path):
    doc = SystemDocument.blank()
    doc.add_bus()
    doc.add_bus()
    doc.add_line("1", "2")
    doc.add_device("GridForming", "1", {"Sn": "100", "angle": "DroopAngle"})
    text = doc.sim_param_text()
    assert 'bus = "1"' in text  # names are quoted, or they would parse as floats
    assert 'angle = "DroopAngle"' in text
    assert "Sn = 100" in text  # numbers stay bare
    assert 'idx = "GFM1"' in text


def test_roundtrip_simulates_identically(tmp_path):
    """A re-serialized shipped system must run and match the original."""
    doc = SystemDocument.load(hermess.SYSTEMS_DIR / "3bus_loadstep")
    folder = doc.save(tmp_path / "3bus_copy")
    dae_copy = hermess.simulate("3bus_copy", system_root=tmp_path, T_end=0.3)
    dae_orig = hermess.simulate("3bus_loadstep", T_end=0.3)
    assert np.allclose(dae_copy.x_full, dae_orig.x_full, rtol=1e-9, atol=1e-12)


def test_built_from_scratch_simulates(tmp_path):
    """The decisive test: a system assembled purely through document
    operations (as canvas clicks would) validates and simulates."""
    source = sysparse.parse_system(hermess.SYSTEMS_DIR / "3bus")

    doc = SystemDocument.blank("built")
    for _ in range(3):
        doc.add_bus()
    for entry in source.lines:
        params = {k: v for k, v in entry.params.items() if k not in ("bus_i", "bus_j")}
        doc.add_line(entry.get("bus_i"), entry.get("bus_j"), params)
    for entry in source.bus_inits:
        doc.set_businit(
            entry.get("bus"), {k: v for k, v in entry.params.items() if k != "bus"}
        )
    for entry in source.devices:
        params = {k: v for k, v in entry.params.items() if k not in ("bus",)}
        doc.add_device(entry.kind, entry.get("bus"), params)
    doc.add_disturbance({"time": "0.1", "type": "LOAD", "bus": "2", "p_delta": "5"})

    assert [i for i in validation.validate(doc.desc, {}) if i.severity == "error"] == []
    folder = doc.save(tmp_path / "built")
    dae = hermess.simulate("built", system_root=tmp_path, T_end=0.3)
    assert dae.x_full.shape[1] > 1
    assert np.isfinite(dae.x_full).all()


# ---- parameter metadata -----------------------------------------------------


def test_device_meta_reflects_strategies():
    base = param_meta.device_meta("GENROU")
    with_pss = param_meta.device_meta("GENROU", {"pss": "PSSKundur"})
    assert base is not None and with_pss is not None
    assert set(base.params) != set(with_pss.params)  # the PSS adds parameters
    assert param_meta.device_meta("NoSuchDevice") is None


def test_meta_defaults_and_sentinels():
    meta = param_meta.device_meta("GridForming")
    assert meta.params["Sn"] == "100"
    assert meta.sentinels["omega_f_q"] == "omega_f"
    assert meta.params["omega_f_q"] == ""  # NaN sentinel shows as empty
    assert "filter" in meta.strategy_axes
    kinds = param_meta.buildable_device_kinds()
    assert {"GridForming", "GENROU", "StaticZIP", "SVC"} <= set(kinds)


def test_line_meta_uses_builder_defaults():
    meta = param_meta.line_meta()
    assert meta.params["b"] == LINE_DEFAULTS["b"]  # nonzero for line_dyn
    assert "bus_i" not in meta.params
