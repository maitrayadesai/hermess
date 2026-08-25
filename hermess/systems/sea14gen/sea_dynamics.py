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

# Dynamic model data of the simplified 14-generator South East Australian
# system (Gibbard & Vowles, Univ. of Adelaide, Rev 4, 2014). Companion to
# sea_data.py (network/loadflow tables). Table references are to the PDF.
#
# Machine model (Appendix I.5): PSS/E-style 6th-order model with states
# (delta, omega, E'q, psi_kd, E'd, psi_kq); the 5th-order variant (HPS_1,
# YPS_3) replaces the q-axis pair by a single psi''_q damper state,
# eqs. (25)-(26). Ra = 0 and D = 0 for all machines. f = 50 Hz.

# --- Table 15: generator parameters (reactances pu on machine MVA rating) ---
# name: dict with order (5|6), H (MWs/MVA), Xa (leakage), Xd, Xq, Xd1 (X'd),
# Td01 (T'do s), Xd2 (X''d), Td02 (T''do s), Xq1 (X'q), Tq01 (T'qo s),
# Xq2 (X''q), Tq02 (T''qo s). Xq1/Tq01 are absent for 5th-order machines.
GEN_PARAMS = {
    "HPS_1": dict(order=5, H=3.60, Xa=0.14, Xd=1.10, Xq=0.65, Xd1=0.25,
                  Td01=8.50, Xd2=0.25, Td02=0.050, Xq1=None, Tq01=None,
                  Xq2=0.25, Tq02=0.200),
    "BPS_2": dict(order=6, H=3.20, Xa=0.20, Xd=1.80, Xq=1.75, Xd1=0.30,
                  Td01=8.50, Xd2=0.21, Td02=0.040, Xq1=0.70, Tq01=0.30,
                  Xq2=0.21, Tq02=0.080),
    "EPS_2": dict(order=6, H=2.80, Xa=0.17, Xd=2.20, Xq=2.10, Xd1=0.30,
                  Td01=4.50, Xd2=0.20, Td02=0.040, Xq1=0.50, Tq01=1.50,
                  Xq2=0.21, Tq02=0.060),
    "MPS_2": dict(order=6, H=3.20, Xa=0.20, Xd=1.80, Xq=1.75, Xd1=0.30,
                  Td01=8.50, Xd2=0.21, Td02=0.040, Xq1=0.70, Tq01=0.30,
                  Xq2=0.21, Tq02=0.080),
    "VPS_2": dict(order=6, H=2.60, Xa=0.20, Xd=2.30, Xq=1.70, Xd1=0.30,
                  Td01=5.00, Xd2=0.25, Td02=0.030, Xq1=0.40, Tq01=2.00,
                  Xq2=0.25, Tq02=0.250),
    "LPS_3": dict(order=6, H=2.80, Xa=0.20, Xd=2.70, Xq=1.50, Xd1=0.30,
                  Td01=7.50, Xd2=0.25, Td02=0.040, Xq1=0.85, Tq01=0.85,
                  Xq2=0.25, Tq02=0.120),
    "YPS_3": dict(order=5, H=3.50, Xa=0.15, Xd=2.00, Xq=1.80, Xd1=0.25,
                  Td01=7.50, Xd2=0.20, Td02=0.040, Xq1=None, Tq01=None,
                  Xq2=0.20, Tq02=0.250),
    "CPS_4": dict(order=6, H=3.00, Xa=0.20, Xd=1.90, Xq=1.80, Xd1=0.30,
                  Td01=6.50, Xd2=0.26, Td02=0.035, Xq1=0.55, Tq01=1.40,
                  Xq2=0.26, Tq02=0.040),
    "GPS_4": dict(order=6, H=4.00, Xa=0.18, Xd=2.20, Xq=1.40, Xd1=0.32,
                  Td01=9.00, Xd2=0.24, Td02=0.040, Xq1=0.75, Tq01=1.40,
                  Xq2=0.24, Tq02=0.130),
    "SPS_4": dict(order=6, H=2.60, Xa=0.20, Xd=2.30, Xq=1.70, Xd1=0.30,
                  Td01=5.00, Xd2=0.25, Td02=0.030, Xq1=0.40, Tq01=2.00,
                  Xq2=0.25, Tq02=0.250),
    "TPS_4": dict(order=6, H=2.60, Xa=0.20, Xd=2.30, Xq=1.70, Xd1=0.30,
                  Td01=5.00, Xd2=0.25, Td02=0.030, Xq1=0.40, Tq01=2.00,
                  Xq2=0.25, Tq02=0.250),
    "NPS_5": dict(order=6, H=3.50, Xa=0.15, Xd=2.20, Xq=1.70, Xd1=0.30,
                  Td01=7.50, Xd2=0.24, Td02=0.025, Xq1=0.80, Tq01=1.50,
                  Xq2=0.24, Tq02=0.100),
    "TPS_5": dict(order=6, H=4.00, Xa=0.20, Xd=2.00, Xq=1.50, Xd1=0.30,
                  Td01=7.50, Xd2=0.22, Td02=0.040, Xq1=0.80, Tq01=3.00,
                  Xq2=0.22, Tq02=0.200),
    "PPS_5": dict(order=6, H=7.50, Xa=0.15, Xd=2.30, Xq=2.00, Xd1=0.25,
                  Td01=5.00, Xd2=0.17, Td02=0.022, Xq1=0.35, Tq01=1.00,
                  Xq2=0.17, Tq02=0.035),
}

# --- Tables 16 + 26/27: excitation systems ----------------------------------
# ST1A (Fig. 20 / Table 26): Vc = Vt/(1+s·Tr);
#   Ef = KA/(1+s·TA) · (1+s·TC)/(1+s·TB) · (1+s·TC1)/(1+s·TB1) · (Vref−Vc+Vs)
# Table 16's "KE/TE" rows for ST1A machines are in fact TB1/TC1 (verified
# against Table 26: only TPS_5 has a second lead-lag).
AVR_ST1A = {
    "HPS_1": dict(Tr=0.0, KA=200.0, TA=0.10, TB=13.25, TC=2.50, TB1=0.0, TC1=0.0),
    "BPS_2": dict(Tr=0.0, KA=400.0, TA=0.02, TB=1.12, TC=0.50, TB1=0.0, TC1=0.0),
    "VPS_2": dict(Tr=0.0, KA=300.0, TA=0.01, TB=0.70, TC=0.35, TB1=0.0, TC1=0.0),
    "MPS_2": dict(Tr=0.0, KA=400.0, TA=0.02, TB=1.12, TC=0.50, TB1=0.0, TC1=0.0),
    "LPS_3": dict(Tr=0.0, KA=400.0, TA=0.05, TB=6.42, TC=1.14, TB1=0.0, TC1=0.0),
    "TPS_4": dict(Tr=0.0, KA=300.0, TA=0.10, TB=40.0, TC=4.00, TB1=0.0, TC1=0.0),
    "CPS_4": dict(Tr=0.02, KA=300.0, TA=0.05, TB=9.80, TC=1.52, TB1=0.0, TC1=0.0),
    "SPS_4": dict(Tr=0.0, KA=300.0, TA=0.01, TB=0.70, TC=0.35, TB1=0.0, TC1=0.0),
    "GPS_4": dict(Tr=0.0, KA=250.0, TA=0.20, TB=0.0232, TC=0.1360, TB1=0.0, TC1=0.0),
    "TPS_5": dict(Tr=0.0, KA=400.0, TA=0.50, TB=16.0, TC=1.40, TB1=0.05, TC1=0.60),
    "PPS_5": dict(Tr=0.0, KA=300.0, TA=0.01, TB=0.80, TC=0.20, TB1=0.0, TC1=0.0),
}

# AC1A (Fig. 21 / Table 27), saturation/rectifier effects neglected:
#   Vr = KA/(1+s·TA) · (Vref−Vc+Vs−Vf);  TE·dEf/dt = Vr − KE·Ef;
#   Vf = s·KF/(1+s·TF) · Ef
# (TB = TC = 0 for all three AC1A machines.) NPS_5 values follow Table 27
# (KE=1, TE=0.87, KF=0.004, TF=0.27).
AVR_AC1A = {
    "EPS_2": dict(Tr=0.0, KA=400.0, TA=0.02, KE=1.0, TE=1.0, KF=0.029, TF=1.0),
    "YPS_3": dict(Tr=0.0, KA=200.0, TA=0.05, KE=1.0, TE=1.333, KF=0.020, TF=0.8),
    "NPS_5": dict(Tr=0.0, KA=1000.0, TA=0.04, KE=1.0, TE=0.87, KF=0.004, TF=0.27),
}

# --- Tables 17-20 + I.3: power system stabilisers ----------------------------
# H_PSS(s) = De · sTW/(1+sTW) · Hc(s),  De = 20 pu on machine MVA, TW = 7.5 s.
# Hc forms (PDF eqs. (7)-(10)); all denominators are products of first-order
# lags, numerators are first-order or complex-pair (1 + a·s + b·s²) sections.
PSS_TW = 7.5
PSS_DE = 20.0
# Each entry: (Kc, zeros, poles) with
#   zeros: list of ("T", T) first-order (1+sT) or ("ab", a, b) quadratic terms
#   poles: list of T for (1+sT) lags (zeros with T=0 omitted).
PSS = {
    # Table 17, eq (7): 4 real lead-lag pairs
    "EPS_2": (0.233, [("T", 0.286), ("T", 0.111), ("T", 0.040)],
              [0.00667, 0.00667, 0.00667]),
    "TPS_5": (0.294, [("T", 0.500), ("T", 0.0588), ("T", 0.0167)],
              [0.00667, 0.00667, 0.00667]),
    "PPS_5": (0.178, [("T", 0.200), ("T", 0.187), ("T", 0.167), ("T", 0.020)],
              [0.350, 0.0667, 0.00667, 0.00667]),
    # Table 18, eq (8): real zeros + complex pair
    "MPS_2": (0.333, [("T", 0.010), ("ab", 0.10, 0.0051)],
              [0.00667, 0.00667, 0.00667]),
    "YPS_3": (0.298, [("T", 0.050), ("ab", 0.5091, 0.1322)],
              [0.00667, 0.00667, 0.00667]),
    "NPS_5": (0.195, [("T", 0.033), ("T", 0.033), ("ab", 0.30, 0.1111)],
              [0.300, 0.00667, 0.00667, 0.00667]),
    # Table 19, eq (9): 2 real lead-lag pairs
    "VPS_2": (0.286, [("T", 0.0708), ("T", 0.0292)], [0.00667, 0.00667]),
    "TPS_4": (0.357, [("T", 0.2083), ("T", 0.2083)], [0.00667, 0.00667]),
    "CPS_4": (0.235, [("T", 0.2777), ("T", 0.1000)], [0.00667, 0.00667]),
    # Table 20, eq (10): complex pair only
    "HPS_1": (0.769, [("ab", 0.3725, 0.03845)], [0.00667, 0.00667]),
    "BPS_2": (0.278, [("ab", 0.1280, 0.00640)], [0.00667, 0.00667]),
    "LPS_3": (0.625, [("ab", 0.1684, 0.01180)], [0.00667, 0.00667]),
    "SPS_4": (0.316, [("ab", 0.0909, 0.002067)], [0.00667, 0.00667]),
    "GPS_4": (0.303, [("ab", 0.1154, 0.005917)], [0.00667, 0.00667]),
}
# HPS_1's PSS is out of service in Cases 4 and 6 (synchronous condenser);
# in Case 5 (pumping) its output sign is negated.
PSS_OFF = {4: ["HPS_1"], 6: ["HPS_1"]}
PSS_NEGATED = {5: ["HPS_1"]}

# --- I.2.3 / Fig. 22: SVC small-signal model ---------------------------------
# dB control: e = Vref − Vt + Vs − Kd·Ks·(Q/Vt-deviation);
#   B = (1/Ks) · 2.5/(1+s·Td) · (KA/s) · e        [B, Q/Vt in pu on MBASE]
# name: (KA, Ks); common: Kd = 0.01 pu on SBASE(100 MVA), Td = 0.005 s.
SVC_CONTROL = {
    "ASVC_2": (500.0, 6.5),
    "RSVC_3": (500.0, 8.0),
    "BSVC_4": (500.0, 14.3),
    "PSVC_5": (250.0, 5.0),
    "SSVC_5": (250.0, 5.5),
}
SVC_KD = 0.01
SVC_TD = 0.005

# --- Tables 2-7: rotor modes (validation targets) -----------------------------
# case -> {"no_pss": [(re, im)], "pss": [(re, im)]}; rad/s, complex pair
# representatives as published. 13 electromechanical modes (14 machines).
ROTOR_MODES = {
    1: {"no_pss": [(-0.175, 10.442), (0.109, 9.583), (0.041, 8.959),
                   (-0.557, 8.634), (-0.260, 8.368), (-0.612, 8.047),
                   (-0.439, 7.965), (0.014, 7.812), (-0.189, 7.724),
                   (-0.617, 7.425), (0.115, 3.970), (0.088, 2.601),
                   (-0.016, 2.028)],
        "pss": [(-2.193, 10.386), (-1.978, 9.742), (-1.926, 9.293),
                (-2.505, 8.858), (-1.953, 8.261), (-1.971, 8.490),
                (-1.875, 7.756), (-1.777, 7.643), (-2.061, 7.872),
                (-1.878, 7.588), (-1.044, 3.640), (-0.385, 2.402),
                (-0.522, 1.798)]},
    2: {"no_pss": [(0.066, 10.743), (0.101, 9.563), (-0.250, 9.261),
                   (-0.922, 8.613), (-0.534, 8.669), (-0.184, 8.482),
                   (-0.700, 8.293), (-0.208, 7.929), (-0.065, 7.385),
                   (-0.485, 7.570), (0.193, 3.772), (0.054, 2.863),
                   (0.081, 1.915)],
        "pss": [(-2.403, 10.964), (-2.038, 9.725), (-2.370, 9.644),
                (-2.805, 8.962), (-2.494, 8.936), (-2.039, 8.379),
                (-2.442, 8.370), (-2.029, 7.739), (-2.021, 7.490),
                (-1.814, 7.772), (-0.769, 3.537), (-0.447, 2.542),
                (-0.431, 1.759)]},
    3: {"no_pss": [(-0.377, 11.109), (0.101, 9.555), (-0.301, 9.021),
                   (-0.583, 8.702), (-0.182, 8.660), (-0.140, 8.249),
                   (-0.191, 8.110), (-0.076, 7.625), (-0.576, 7.381),
                   (-0.131, 6.314), (0.011, 4.090), (0.020, 2.727),
                   (-0.032, 2.105)],
        "pss": [(-1.909, 11.244), (-2.037, 9.724), (-2.278, 9.100),
                (-2.519, 8.914), (-2.025, 8.376), (-1.948, 8.492),
                (-2.011, 7.727), (-1.932, 7.535), (-1.933, 7.800),
                (-2.030, 5.909), (-1.119, 3.707), (-0.428, 2.418),
                (-0.580, 1.860)]},
    4: {"no_pss": [(0.197, 10.484), (0.030, 9.665), (-0.173, 9.369),
                   (-1.541, 8.276), (-0.178, 8.779), (-0.561, 8.581),
                   (-0.211, 8.278), (-0.508, 8.522), (-0.431, 8.211),
                   (-0.190, 7.200), (0.165, 4.743), (0.023, 3.573),
                   (-0.009, 2.678)],
        "pss": [(-2.374, 10.774), (-2.163, 9.951), (-2.269, 9.813),
                (-1.695, 8.169), (-2.272, 8.793), (-2.496, 9.064),
                (-2.554, 8.445), (-2.492, 8.826), (-2.280, 8.279),
                (-1.319, 7.494), (-1.080, 4.581), (-0.563, 3.322),
                (-0.589, 2.513)]},
    5: {"no_pss": [(0.181, 10.940), (0.086, 9.570), (-0.163, 9.171),
                   (-0.182, 8.696), (-0.496, 8.554), (-0.263, 8.452),
                   (-0.524, 7.975), (0.008, 7.896), (-0.157, 7.736),
                   (-0.765, 7.241), (0.191, 4.152), (0.006, 3.122),
                   (0.059, 2.154)],
        "pss": [(-2.409, 11.257), (-1.988, 9.762), (-2.093, 9.395),
                (-2.187, 9.119), (-2.471, 8.828), (-2.024, 8.382),
                (-2.382, 7.969), (-1.853, 7.809), (-2.116, 7.865),
                (-1.858, 7.449), (-0.884, 3.902), (-0.457, 2.889),
                (-0.497, 1.957)]},
    6: {"no_pss": [(0.276, 10.390), (0.318, 10.138), (-0.129, 9.423),
                   (-0.233, 8.920), (-0.455, 8.738), (-0.136, 8.578),
                   (-0.213, 8.285), (-1.507, 8.237), (-0.301, 8.128),
                   (-0.359, 7.250), (0.200, 4.810), (0.054, 3.552),
                   (0.036, 2.597)],
        "pss": [(-2.217, 10.708), (-2.142, 10.652), (-2.069, 10.017),
                (-2.522, 9.541), (-2.381, 9.023), (-2.320, 8.506),
                (-2.579, 8.453), (-1.701, 8.168), (-2.076, 8.242),
                (-1.598, 7.553), (-1.078, 4.644), (-0.565, 3.298),
                (-0.520, 2.451)]},
}
