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

# PSID reference for the gfm_droop case: the twin of system/sim_param.txt.
#
# Droop grid-forming inverter (the D'Arco component set) at bus 102 of the
# three-bus system in ThreeBusGFM.raw, ideal source at the reference bus,
# constant-impedance load at bus 103; trip of line 103-101 at t = 1 s. The
# PSID components reduce exactly to the hermess GridForming:
#   ActivePowerDroop(Rp, ωz)     = Droop angle source (Kp = Rp),
#   ReactivePowerDroop(kq, ωf)   = QVDroop (Kq = kq), with ωz = ωf = the one
#                                  hermess power-filter frequency omega_f,
#   VoltageModeControl(kad = 0)  = Cascaded (PSID kffi = hermess Kffv, PSID
#                                  kffv = hermess Kffc); the two active-
#                                  damping states are inert and contribute
#                                  one eigenvalue pair at exactly -ωad,
#   LCLFilter                    = LCL (lf rf cf lg rg = Lf Rf Cf Lt Rt),
# and the internal frames coincide (θ_oc = delta_c, so filter, outer and PI
# integrator states all compare directly). Regenerate with:
#
#   julia --project=hermess/tests/references/psid/_generate \
#         hermess/tests/references/psid/gfm_droop/generate.jl

include(joinpath(@__DIR__, "..", "_generate", "common.jl"))

case_dir = @__DIR__

sys = System(joinpath(case_dir, "ThreeBusGFM.raw"); runchecks = false, frequency = 50.0)
println("system frequency: ", PSY.get_frequency(sys))
loads_to_constant_impedance!(sys)
add_source_to_ref!(sys; X_th = 1e-4)

static_gen = only(get_components(PSY.ThermalStandard, sys))
inverter = PSY.DynamicInverter(
    PSY.get_name(static_gen),
    1.0, # ω_ref
    PSY.AverageConverter(; rated_voltage = 690.0, rated_current = 2.75),
    PSY.OuterControl(
        PSY.ActivePowerDroop(; Rp = 0.05, ωz = 2 * pi * 5),
        PSY.ReactivePowerDroop(; kq = 0.2, ωf = 2 * pi * 5),
    ),
    PSY.VoltageModeControl(;
        kpv = 0.59, kiv = 736.0, kffv = 0.0, rv = 0.0, lv = 0.2,
        kpc = 1.27, kic = 14.3, kffi = 0.0, ωad = 50.0, kad = 0.0,
    ),
    PSY.FixedDCSource(; voltage = 600.0),
    PSY.FixedFrequency(),
    PSY.LCLFilter(; lf = 0.08, rf = 0.003, cf = 0.074, lg = 0.2, rg = 0.01),
)
add_component!(sys, inverter, static_gen)

name = PSY.get_name(inverter)
println("inverter states: ", PSY.get_states(inverter))

columns = Pair{String, Any}[
    "theta" => (name, :θ_oc),
    "pm" => (name, :p_oc),
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
    "v_101" => (:voltage, 101),
    "v_102" => (:voltage, 102),
    "v_103" => (:voltage, 103),
]

load = only(get_components(PSY.StandardLoad, sys))

run_and_write(
    case_dir,
    "Droop grid-forming inverter (D'Arco set, kad = 0) on the three-bus " *
    "system, +20 MW / +5 Mvar impedance-load step at bus 103 at t = 1 s; " *
    "vs hermess GridForming.",
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
        "hermess state map (direct, same frames): delta_c=theta, " *
        "Pc_tilde=pm, Qc_tilde=qm, Vfd_ext=vr_filter, Vfq_ext=vi_filter, " *
        "ifd_ext=ir_cnv, ifq_ext=ii_cnv, itd_ext=ir_filter, " *
        "itq_ext=ii_filter, xi_d/xi_q/gamma_d/gamma_q identical.",
        "kad = 0 leaves the two active-damping states inert: two reference " *
        "eigenvalues at exactly -ωad = -50 with no hermess counterpart.",
    ],
)
