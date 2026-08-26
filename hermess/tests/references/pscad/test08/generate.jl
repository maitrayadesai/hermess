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

# PSID reference for the pscad/test08 case: the twin of system/sim_param.txt,
# and the SAME system whose PSCAD trajectory is committed in
# upstream/Test08_omega.csv. Virtual-synchronous-machine converter (D'Arco
# VirtualInertia + reactive droop + damped voltage-mode inner + Kaura PLL)
# on the OMIB; reference power step 0.5 -> 0.7 at t = 1 s. Regenerate with:
#
#   julia --project=hermess/tests/references/psid/_generate \
#         hermess/tests/references/pscad/test08/generate.jl

include(joinpath(@__DIR__, "..", "..", "psid", "_generate", "common.jl"))

case_dir = @__DIR__

sys = System(joinpath(case_dir, "OMIB.raw"); runchecks = false, frequency = 50.0)
println("system frequency: ", PSY.get_frequency(sys))
add_source_to_ref!(sys; X_th = 5e-6)

static_gen = only(get_components(PSY.ThermalStandard, sys))
inverter = PSY.DynamicInverter(
    PSY.get_name(static_gen),
    1.0, # ω_ref
    PSY.AverageConverter(; rated_voltage = 690.0, rated_current = 2.75),
    PSY.OuterControl(
        PSY.VirtualInertia(; Ta = 2.0, kd = 400.0, kω = 20.0),
        PSY.ReactivePowerDroop(; kq = 0.2, ωf = 1000.0),
    ),
    PSY.VoltageModeControl(;
        kpv = 0.59, kiv = 736.0, kffv = 0.0, rv = 0.0, lv = 0.2,
        kpc = 1.27, kic = 14.3, kffi = 0.0, ωad = 50.0, kad = 0.2,
    ),
    PSY.FixedDCSource(; voltage = 600.0),
    PSY.KauraPLL(; ω_lp = 500.0, kp_pll = 0.084, ki_pll = 4.69),
    PSY.LCLFilter(; lf = 0.08, rf = 0.003, cf = 0.074, lg = 0.2, rg = 0.01),
)
add_component!(sys, inverter, static_gen)

name = PSY.get_name(inverter)
println("inverter states: ", PSY.get_states(inverter))

columns = Pair{String, Any}[
    "theta" => (name, :θ_oc),
    "omega_vsm" => (name, :ω_oc),
    "qm" => (name, :q_oc),
    "ir_cnv" => (name, :ir_cnv),
    "ii_cnv" => (name, :ii_cnv),
    "vr_filter" => (name, :vr_filter),
    "vi_filter" => (name, :vi_filter),
    "ir_filter" => (name, :ir_filter),
    "ii_filter" => (name, :ii_filter),
    "xi_d" => (name, :ξd_ic),
    "xi_q" => (name, :ξq_ic),
    "gamma_d" => (name, :γd_ic),
    "gamma_q" => (name, :γq_ic),
    "phi_d" => (name, :ϕd_ic),
    "phi_q" => (name, :ϕq_ic),
    "vd_lp" => (name, :vd_pll),
    "vq_lp" => (name, :vq_pll),
    "epsilon" => (name, :ε_pll),
    "delta_pll" => (name, :θ_pll),
    "v_102" => (:voltage, 102),
]

run_and_write(
    case_dir,
    "Virtual-synchronous-machine converter (D'Arco set, Kaura PLL) on the " *
    "OMIB, P_ref step 0.5 -> 0.7 at t = 1 s; the system of the PSCAD Test08 " *
    "benchmark.",
    sys,
    PSID.ControlReferenceChange(1.0, inverter, :P_ref, 0.7),
    columns;
    t_end = 4.0,
    ts = 0.005,
    abstol = 1e-6,
    reltol = 1e-6,
    notes = [
        "hermess: GridForming with angle = VSM (Ta, Kd, Kw), pll = Kaura, " *
        "inner = CascadedDamped, omega_f_q = 1000; omega_vsm = ω_oc, " *
        "delta_c = θ_oc, and the PLL states map by name.",
        "The PSCAD trajectory upstream/Test08_omega.csv starts at t = 9 s " *
        "(offset 9.0) and holds ω_oc in p.u.",
    ],
)
