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

# PSID reference for the pscad/test25 case: the twin of system/sim_param.txt,
# and the SAME system whose PSCAD trajectory is committed in
# upstream/Test25_v102.csv. Two Marconato machines (bus 101 with the Type II
# governor, bus 102 with fixed torque), AVRSimple on both, every line
# dynamic, 60 Hz; reference power step 0.8 -> 0.9 on the bus-102 machine at
# t = 1 s. Regenerate with:
#
#   julia --project=hermess/tests/references/psid/_generate \
#         hermess/tests/references/pscad/test25/generate.jl

include(joinpath(@__DIR__, "..", "..", "psid", "_generate", "common.jl"))

case_dir = @__DIR__

sys = System(
    joinpath(case_dir, "ThreeBusMultiLoad.raw");
    runchecks = false,
    frequency = 60.0,
)
println("system frequency: ", PSY.get_frequency(sys))
loads_to_constant_impedance!(sys)

machine() = PSY.MarconatoMachine(
    0.0,     # R
    1.3125,  # Xd
    1.2578,  # Xq
    0.1813,  # Xd_p
    0.25,    # Xq_p
    0.14,    # Xd_pp
    0.18,    # Xq_pp
    5.89,    # Td0_p
    0.6,     # Tq0_p
    0.5,     # Td0_pp
    0.023,   # Tq0_pp
    0.0,     # T_AA
)

gens = sort(
    collect(get_components(PSY.ThermalStandard, sys));
    by = g -> PSY.get_number(PSY.get_bus(g)),
)
gen101, gen102 = gens

dyn101 = PSY.DynamicGenerator(;
    name = PSY.get_name(gen101),
    ω_ref = 1.0,
    machine = machine(),
    shaft = PSY.SingleMass(; H = 3.01, D = 0.0),
    avr = PSY.AVRSimple(1.0),
    prime_mover = PSY.TGTypeII(; R = 0.05, T1 = 1.0, T2 = 2.0,
                               τ_limits = (min = 0.1, max = 1.5)),
    pss = PSY.PSSFixed(0.0),
)
add_component!(sys, dyn101, gen101)

dyn102 = PSY.DynamicGenerator(;
    name = PSY.get_name(gen102),
    ω_ref = 1.0,
    machine = machine(),
    shaft = PSY.SingleMass(; H = 3.01, D = 0.0),
    avr = PSY.AVRSimple(1.0),
    prime_mover = PSY.TGFixed(1.0),
    pss = PSY.PSSFixed(0.0),
)
add_component!(sys, dyn102, gen102)

println("gen 101 states: ", PSY.get_states(dyn101))
n101 = PSY.get_name(dyn101)
n102 = PSY.get_name(dyn102)

columns = Pair{String, Any}[
    "delta_1" => (n101, :δ),
    "omega_1" => (n101, :ω),
    "xg_1" => (n101, :xg),
    "efd_1" => (n101, :Vf),
    "psiq_1" => (n101, :ψq),
    "psid_1" => (n101, :ψd),
    "eq_p_1" => (n101, :eq_p),
    "ed_p_1" => (n101, :ed_p),
    "eq_pp_1" => (n101, :eq_pp),
    "ed_pp_1" => (n101, :ed_pp),
    "delta_2" => (n102, :δ),
    "omega_2" => (n102, :ω),
    "efd_2" => (n102, :Vf),
    "psid_2" => (n102, :ψd),
    "psiq_2" => (n102, :ψq),
    "v_101" => (:voltage, 101),
    "v_102" => (:voltage, 102),
    "v_103" => (:voltage, 103),
]

run_and_write(
    case_dir,
    "Two Marconato machines (Type II governor at bus 101, fixed torque at " *
    "bus 102, AVRSimple) on a fully dynamic network at 60 Hz, P_ref step " *
    "0.8 -> 0.9 at t = 1 s; the system of the PSCAD Test25 benchmark.",
    sys,
    PSID.ControlReferenceChange(1.0, dyn102, :P_ref, 0.9),
    columns;
    t_end = 40.0,
    ts = 0.01,
    abstol = 1e-6,
    reltol = 1e-6,
    notes = [
        "hermess: two Marconato devices with avr = AVRSimple, governor = " *
        "TGTypeII (bus 1) / GOVCONST (bus 2), line_dyn = True, fn = 60; " *
        "state map: delta/omega/psid/psiq by name, e_qprim=eq_p, " *
        "e_dprim=ed_p, e_qsec=eq_pp, e_dsec=ed_pp, Efd=Vf, xg=x_g1.",
        "The PSCAD trajectory upstream/Test25_v102.csv starts at t = 49 s " *
        "(offset 49.0) and holds the bus-102 voltage magnitude in p.u.",
    ],
    extra_meta = Dict("all_lines_dynamic" => true, "reference_bus" => true),
)
