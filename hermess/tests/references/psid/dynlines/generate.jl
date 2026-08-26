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

# PSID reference for the dynlines case: the twin of system/sim_param.txt.
#
# The Sauer-Pai machine of the sauerpai case with the network itself
# dynamic: PSID all_lines_dynamic (every Line becomes a DynamicBranch with
# series-current states, and every bus voltage a capacitor state driven by
# the summed b/2 line charging) is the hermess line_dyn = True formulation
# exactly, inside the documented box: unity taps, g = 0, b > 0 on every
# line, nominal reference frame. Neither tool supports tripping a dynamic
# line, so the disturbance is the impedance-load step. Regenerate with:
#
#   julia --project=hermess/tests/references/psid/_generate \
#         hermess/tests/references/psid/dynlines/generate.jl

include(joinpath(@__DIR__, "..", "_generate", "common.jl"))

case_dir = @__DIR__

sys = System(joinpath(case_dir, "ThreeBusDyn.raw"); runchecks = false, frequency = 50.0)
println("system frequency: ", PSY.get_frequency(sys))
loads_to_constant_impedance!(sys)
add_source_to_ref!(sys; X_th = 1e-4)

static_gen = only(get_components(PSY.ThermalStandard, sys))
gen = PSY.DynamicGenerator(;
    name = PSY.get_name(static_gen),
    ω_ref = 1.0,
    machine = PSY.SauerPaiMachine(
        0.0025, # R
        1.8,    # Xd
        1.7,    # Xq
        0.3,    # Xd_p
        0.55,   # Xq_p
        0.25,   # Xd_pp
        0.25,   # Xq_pp
        0.2,    # Xl
        8.0,    # Td0_p
        0.4,    # Tq0_p
        0.03,   # Td0_pp
        0.05,   # Tq0_pp
    ),
    shaft = PSY.SingleMass(; H = 6.5, D = 0.0),
    avr = PSY.AVRFixed(0.0),
    prime_mover = PSY.TGFixed(1.0),
    pss = PSY.PSSFixed(0.0),
)
add_component!(sys, gen, static_gen)

name = PSY.get_name(gen)

columns = Pair{String, Any}[
    "delta" => (name, :δ),
    "omega" => (name, :ω),
    "psiq" => (name, :ψq),
    "psid" => (name, :ψd),
    "eq_p" => (name, :eq_p),
    "ed_p" => (name, :ed_p),
    "psid_pp" => (name, :ψd_pp),
    "psiq_pp" => (name, :ψq_pp),
    "v_101" => (:voltage, 101),
    "v_102" => (:voltage, 102),
    "v_103" => (:voltage, 103),
]

load = only(get_components(PSY.StandardLoad, sys))

run_and_write(
    case_dir,
    "Dynamic network (all lines as DynamicBranch, bus voltages as capacitor " *
    "states) around the Sauer-Pai machine, +20 MW / +5 Mvar impedance-load " *
    "step at bus 103 at t = 1 s; vs hermess line_dyn = True.",
    sys,
    [
        PSID.LoadChange(1.0, load, :P_ref_impedance, 1.0),
        PSID.LoadChange(1.0, load, :Q_ref_impedance, 0.15),
    ],
    columns;
    t_end = 8.0,
    ts = 0.005,
    abstol = 1e-6,
    reltol = 1e-6,
    notes = [
        "hermess runs this system with line_dyn = True; machine state map " *
        "as in the sauerpai case; the bus-voltage magnitudes are dynamic " *
        "states on both sides.",
        "Exactness box: unity taps, g = 0, b > 0 on every line, " *
        "omega_mode = nom; PSID rotates the dynamic network at the " *
        "constant nominal frequency, as hermess does.",
    ],
    extra_meta = Dict("all_lines_dynamic" => true),
)
