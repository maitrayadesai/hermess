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

# PSID reference for the shaft5mass case: the twin of system/sim_param.txt.
#
# The Sauer-Pai machine of the sauerpai case on the five-mass torsional
# shaft HP-IP-LP-GEN-EXC, with the Sauer-Pai torsional data set of the PSID
# test suite; trip of line 103-101 at t = 1 s excites the torsional modes.
# PSID's FiveMassShaft applies the whole mechanical torque to the HP mass,
# which is the hermess Shaft5Mass with F_hp = 1, F_ip = F_lp = 0; inertias,
# self and mutual dampings, stiffnesses and the uniform reference-frame
# subtraction map one to one (PSID K_hp/K_ip/K_lp/K_ex name the section
# after its left mass = hermess K_hp_ip/K_ip_lp/K_lp_gen/K_gen_exc; PSID
# D_12/D_23/D_34/D_45 = hermess Dm_*). Regenerate with:
#
#   julia --project=hermess/tests/references/psid/_generate \
#         hermess/tests/references/psid/shaft5mass/generate.jl

include(joinpath(@__DIR__, "..", "_generate", "common.jl"))

case_dir = @__DIR__

sys = System(joinpath(case_dir, "ThreeBusMachine.raw"); runchecks = false, frequency = 50.0)
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
    shaft = PSY.FiveMassShaft(
        3.01,    # H (gen)
        0.3348,  # H_hp
        0.7306,  # H_ip
        0.8154,  # H_lp
        0.0452,  # H_ex
        0.0,     # D (gen)
        0.518,   # D_hp
        0.224,   # D_ip
        0.224,   # D_lp
        0.145,   # D_ex
        0.0518,  # D_12 (HP-IP)
        0.0224,  # D_23 (IP-LP)
        0.0224,  # D_34 (LP-GEN)
        0.0145,  # D_45 (GEN-EX)
        33.07,   # K_hp (HP-IP)
        28.59,   # K_ip (IP-LP)
        44.68,   # K_lp (LP-GEN)
        21.984,  # K_ex (GEN-EX)
    ),
    avr = PSY.AVRFixed(0.0),
    prime_mover = PSY.TGFixed(1.0),
    pss = PSY.PSSFixed(0.0),
)
add_component!(sys, gen, static_gen)

name = PSY.get_name(gen)
println("generator states: ", PSY.get_states(gen))

columns = Pair{String, Any}[
    "delta" => (name, :δ),
    "omega" => (name, :ω),
    "delta_hp" => (name, :δ_hp),
    "omega_hp" => (name, :ω_hp),
    "delta_ip" => (name, :δ_ip),
    "omega_ip" => (name, :ω_ip),
    "delta_lp" => (name, :δ_lp),
    "omega_lp" => (name, :ω_lp),
    "delta_exc" => (name, :δ_ex),
    "omega_exc" => (name, :ω_ex),
    "psid_pp" => (name, :ψd_pp),
    "psiq_pp" => (name, :ψq_pp),
    "v_102" => (:voltage, 102),
]

load = only(get_components(PSY.StandardLoad, sys))

run_and_write(
    case_dir,
    "Five-mass torsional shaft (HP-IP-LP-GEN-EXC, Sauer-Pai torsional data) " *
    "on the Sauer-Pai machine, three-bus system, +20 MW / +5 Mvar " *
    "impedance-load step at bus 103 at t = 1 s; vs hermess Shaft5Mass with " *
    "F_hp = 1.",
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
        "hermess state map: delta/omega (gen mass), delta_hp/omega_hp, " *
        "delta_ip/omega_ip, delta_lp/omega_lp, delta_exc/omega_exc = " *
        "δ/ω, δ_hp/ω_hp, δ_ip/ω_ip, δ_lp/ω_lp, δ_ex/ω_ex.",
        "hermess must run with F_hp = 1, F_ip = F_lp = 0 (PSID applies the " *
        "whole mechanical torque to the HP mass) and f = 0.",
    ],
)
