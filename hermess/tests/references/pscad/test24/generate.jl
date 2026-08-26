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

# PSID reference for the pscad/test24 case: the twin of system/sim_param.txt,
# and the SAME system whose PSCAD trajectory is committed in
# upstream/Test24_p.csv. Grid-following converter (PI power outers,
# current-mode inner with voltage feed-forward, reduced-order PLL) on the
# OMIB; reference power step 0.5 -> 0.7 at t = 1 s. Note: the upstream PSID
# suite asserts only the initialization and eigenvalues of this case against
# its own records and keeps the PSCAD trajectory comparison commented out;
# the achieved PSCAD agreement is recorded in case.json either way.
# Regenerate with:
#
#   julia --project=hermess/tests/references/psid/_generate \
#         hermess/tests/references/pscad/test24/generate.jl

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
        PSY.ActivePowerPI(; Kp_p = 2.0, Ki_p = 30.0, ωz = 0.132 * 2 * pi * 50),
        PSY.ReactivePowerPI(; Kp_q = 2.0, Ki_q = 30.0, ωf = 0.132 * 2 * pi * 50),
    ),
    PSY.CurrentModeControl(; kpc = 0.37, kic = 0.7, kffv = 1.0),
    PSY.FixedDCSource(; voltage = 600.0),
    PSY.ReducedOrderPLL(; ω_lp = 1.32 * 2 * pi * 50, kp_pll = 2.0, ki_pll = 20.0),
    PSY.LCLFilter(; lf = 0.009, rf = 0.016, cf = 2.5, lg = 0.002, rg = 0.003),
)
add_component!(sys, inverter, static_gen)

name = PSY.get_name(inverter)
println("inverter states: ", PSY.get_states(inverter))

columns = Pair{String, Any}[
    "sigma_p" => (name, :σp_oc),
    "pm" => (name, :p_oc),
    "sigma_q" => (name, :σq_oc),
    "qm" => (name, :q_oc),
    "gamma_d" => (name, :γd_ic),
    "gamma_q" => (name, :γq_ic),
    "ir_cnv" => (name, :ir_cnv),
    "ii_cnv" => (name, :ii_cnv),
    "vr_filter" => (name, :vr_filter),
    "vi_filter" => (name, :vi_filter),
    "ir_filter" => (name, :ir_filter),
    "ii_filter" => (name, :ii_filter),
    "vq_lp" => (name, :vq_pll),
    "epsilon" => (name, :ε_pll),
    "delta_pll" => (name, :θ_pll),
    "v_102" => (:voltage, 102),
]

run_and_write(
    case_dir,
    "Grid-following converter (PI power outers, current-mode inner, " *
    "reduced-order PLL) on the OMIB, P_ref step 0.5 -> 0.7 at t = 1 s; the " *
    "system of the PSCAD Test24 benchmark.",
    sys,
    PSID.ControlReferenceChange(1.0, inverter, :P_ref, 0.7),
    columns;
    t_end = 2.0,
    ts = 0.005,
    abstol = 1e-6,
    reltol = 1e-6,
    notes = [
        "hermess: GridFollowing (angle = PLLPowerPI, voltage = QPowerPI, " *
        "inner = CurrentPI, pll = ReducedPLL); sigma_p/sigma_q, pm = " *
        "Pc_tilde, qm = Qc_tilde, gamma_d/q, the six filter states and the " *
        "PLL states map by name; the hermess frame angle delta_c is the " *
        "algebraic alias of delta_pll = θ_pll.",
        "The PSCAD trajectory upstream/Test24_p.csv starts at t = 9 s " *
        "(offset 9.0) and holds the filtered active power p_oc in p.u.",
    ],
)
