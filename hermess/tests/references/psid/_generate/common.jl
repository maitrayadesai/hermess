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

# Shared machinery for the PSID reference generators. Each <case>/generate.jl
# builds its PowerSystems.jl system (from the PSS/E raw committed next to it),
# attaches the dynamic devices, and calls run_and_write(). Regeneration:
#
#   julia --project=hermess/tests/references/psid/_generate \
#         hermess/tests/references/psid/<case>/generate.jl
#
# The tests compare the committed CSV/JSON; Julia is never needed in CI.

using PowerSystems
using PowerSimulationsDynamics
using Sundials
using JSON
using LinearAlgebra

const PSY = PowerSystems
const PSID = PowerSimulationsDynamics

"""Convert every StandardLoad to a pure constant-impedance load (all power on
the impedance branch). PSID computes the admittance from the power-flow
voltage, matching the hermess StaticZIP with z_share = 1."""
function loads_to_constant_impedance!(sys)
    for load in get_components(PSY.StandardLoad, sys)
        p = PSY.get_constant_active_power(load) + PSY.get_impedance_active_power(load)
        q = PSY.get_constant_reactive_power(load) + PSY.get_impedance_reactive_power(load)
        PSY.set_impedance_active_power!(load, p)
        PSY.set_impedance_reactive_power!(load, q)
        PSY.set_max_impedance_active_power!(load, p)
        PSY.set_max_impedance_reactive_power!(load, q)
        PSY.set_constant_active_power!(load, 0.0)
        PSY.set_constant_reactive_power!(load, 0.0)
        PSY.set_max_constant_active_power!(load, 0.0)
        PSY.set_max_constant_reactive_power!(load, 0.0)
        PSY.set_current_active_power!(load, 0.0)
        PSY.set_current_reactive_power!(load, 0.0)
        PSY.set_max_current_active_power!(load, 0.0)
        PSY.set_max_current_reactive_power!(load, 0.0)
    end
end

"""Attach the ideal source (infinite bus) at the reference bus: the PSID
counterpart of the hermess StaticInfiniteBus with r = 0, x = X_th."""
function add_source_to_ref!(sys; X_th = 1e-5)
    slack = only(
        b for b in get_components(PSY.ACBus, sys) if
        PSY.get_bustype(b) == PSY.ACBusTypes.REF
    )
    source = PSY.Source(;
        name = "InfBus",
        available = true,
        active_power = 0.0,
        reactive_power = 0.0,
        bus = slack,
        R_th = 0.0,
        X_th = X_th,
    )
    add_component!(sys, source)
    return source
end

"""Initialize, run small-signal + time-domain, and write reference.csv and
reference_meta.json into `case_dir`. `columns` maps CSV column name =>
(device_name, state_symbol) for states, or => (:voltage, bus_number) for a
bus-voltage magnitude series. `t_end`/`ts` define the exact output grid."""
function run_and_write(
    case_dir::String,
    description::String,
    sys,
    perturbation,
    columns::Vector{Pair{String, Any}};
    t_end::Float64 = 8.0,
    ts::Float64 = 0.005,
    abstol::Float64 = 1e-9,
    reltol::Float64 = 1e-9,
    notes::Vector{String} = String[],
    extra_meta::Dict = Dict(),
)
    # ConstantFrequency: the network/filter rotation terms use the constant
    # nominal frequency, matching the hermess omega_mode = "nom" frame. The
    # PSID default (ReferenceBus) rotates the frame with the reference
    # device's own speed, which is a (slightly) different vector field: the
    # trajectories barely move but the linearization shifts every
    # oscillatory mode.
    sim = PSID.Simulation(
        PSID.ResidualModel,
        sys,
        mktempdir(),
        (0.0, t_end),
        perturbation;
        all_lines_dynamic = get(extra_meta, "all_lines_dynamic", false),
        frequency_reference = PSID.ConstantFrequency(),
    )

    ss = PSID.small_signal_analysis(sim)
    eigs = ss.eigenvalues
    println("small-signal stable: ", ss.stable,
            "; max Re(eig): ", maximum(real.(eigs)))
    srt = sort(eigs; by = real, rev = true)
    println("slowest/most critical eigenvalues: ", srt[1:min(8, length(srt))])

    status = PSID.execute!(
        sim,
        IDA();
        dtmax = ts,
        saveat = ts,
        abstol = abstol,
        reltol = reltol,
    )
    status == PSID.SIMULATION_FINALIZED || error("PSID simulation failed: $status")
    results = PSID.read_results(sim)

    t_ref = nothing
    data = Vector{Vector{Float64}}()
    names = String[]
    for (col, spec) in columns
        if spec isa Tuple && spec[1] === :voltage
            t, v = PSID.get_voltage_magnitude_series(results, spec[2])
        else
            t, v = PSID.get_state_series(results, spec)
        end
        t_ref === nothing && (t_ref = collect(t))
        length(v) == length(t_ref) || error("length mismatch for $col")
        push!(names, col)
        push!(data, collect(v))
    end

    open(joinpath(case_dir, "reference.csv"), "w") do io
        println(io, "t," * join(names, ","))
        for i in eachindex(t_ref)
            print(io, t_ref[i])
            for series in data
                print(io, ",", series[i])
            end
            println(io)
        end
    end

    initial = Dict(name => series[1] for (name, series) in zip(names, data))

    meta = Dict(
        "description" => description,
        "tool" => "PowerSimulationsDynamics.jl",
        "versions" => Dict(
            "PowerSimulationsDynamics" => string(pkgversion(PowerSimulationsDynamics)),
            "PowerSystems" => string(pkgversion(PowerSystems)),
            "julia" => string(VERSION),
        ),
        "integration" => Dict(
            "solver" => "Sundials IDA",
            "dtmax" => ts,
            "saveat" => ts,
            "abstol" => abstol,
            "reltol" => reltol,
        ),
        "initial" => initial,
        "eigenvalues" => [[real(m), imag(m)] for m in eigs],
        "notes" => notes,
        "extra" => extra_meta,
    )
    open(joinpath(case_dir, "reference_meta.json"), "w") do io
        JSON.print(io, meta, 1)
    end
    println(
        "wrote $(joinpath(case_dir, "reference.csv")) " *
        "($(length(t_ref)) rows, $(length(names) + 1) columns) and " *
        "reference_meta.json (PSID $(pkgversion(PowerSimulationsDynamics)))",
    )
    return sim, results, eigs
end
