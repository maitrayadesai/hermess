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

"""The ``hermess`` console script (hermess.__main__.main).

Argument handling is tested in process by calling ``main(argv)`` directly;
one short end-to-end run exercises the ``run`` subcommand against a shipped
system. In particular ``--help`` and ``--version`` must exit without starting
a simulation, which was broken in 1.1.0.
"""

import pytest

import hermess
from hermess.__main__ import main


@pytest.fixture(autouse=True)
def plain_help(monkeypatch):
    """argparse colors its help on Python 3.14+ (ANSI escapes inside "usage:
    hermess"); PYTHON_COLORS=0 takes precedence over FORCE_COLOR and a tty."""
    monkeypatch.setenv("PYTHON_COLORS", "0")


def test_no_arguments_prints_help_and_exits_cleanly(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage: hermess" in out
    assert "run" in out and "list" in out


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_exits_without_simulating(capsys, flag):
    with pytest.raises(SystemExit) as excinfo:
        main([flag])
    assert excinfo.value.code == 0
    assert "usage: hermess" in capsys.readouterr().out


def test_version_prints_package_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert hermess.__version__ in capsys.readouterr().out


def test_list_prints_the_shipped_systems(capsys):
    assert main(["list"]) == 0
    listed = capsys.readouterr().out.splitlines()
    assert listed == hermess.list_systems()
    assert "3bus" in listed


def test_run_unknown_system_fails_with_hint(capsys):
    assert main(["run", "no_such_system", "--no-plot"]) == 1
    err = capsys.readouterr().err
    assert "no_such_system" in err
    assert "hermess list" in err


def test_run_rejects_malformed_set(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "3bus", "--set", "T_end"])
    assert excinfo.value.code == 2
    assert "KEY=VALUE" in capsys.readouterr().err


def test_run_rejects_unknown_config_field(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "3bus", "--set", "T_endd=1.0"])
    assert excinfo.value.code == 2
    assert "T_endd" in capsys.readouterr().err


def test_run_short_simulation(capsys):
    assert main(["run", "3bus", "--no-plot", "--t-end", "0.2"]) == 0
    assert "Simulated 3bus." in capsys.readouterr().out
