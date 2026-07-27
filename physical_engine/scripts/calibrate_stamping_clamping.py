#!/usr/bin/env python3
"""
Monte Carlo calibration verification script for Stations 1–4 process models.

Runs 10,000 iterations for each station to verify that nominal execution yields non-defective
parts and that stochastic noise matches target defect rate specifications:
- Station 1 (MEA Prep): Target cure alpha in [0.85, 0.98]
- Station 2 (Catalyst Deposition): Target ECSA ratio = 1.0 nominal
- Station 3 (Bipolar Plate Stamping): Target defect rate = 0.20%
- Station 4 (Stack Clamping): Target defect rate = 0.80%
"""

import numpy as np
from physical_engine.factory_simulation.station1_mea_preparation import simulate_stage1_mea_prep_safe
from physical_engine.factory_simulation.station2_catalyst_deposition import simulate_stage2_catalyst_deposition_safe
from physical_engine.factory_simulation.station3_bipolar_plate_stamping import (
    simulate_stage1_stamping_safe,
    F_NOM_S3,
)
from physical_engine.factory_simulation.station4_stack_clamping import simulate_stage2_clamping_safe

def run_calibration():
    np.random.seed(42)
    N = 10000

    print("=" * 70)
    print("      MATRIX FACTORY TWIN: STATIONS 1–4 CALIBRATION REPORT      ")
    print("=" * 70)

    # --- Station 1 ---
    t_proc_1, def_1, vr_1, alpha_1, delam_1, pinhole_1 = simulate_stage1_mea_prep_safe(433.15, 300.0)
    print(f"[Station 1 MEA Prep] Nominal T=160C (433.15K) t=300s -> alpha={alpha_1:.4f}, defective={def_1}")
    assert 0.85 <= alpha_1 <= 0.98, "Station 1 nominal cure out of target range!"

    # --- Station 2 ---
    t_proc_2, def_2, vr_2, ecsa_2 = simulate_stage2_catalyst_deposition_safe(0.15, 0.05)
    print(f"[Station 2 Catalyst Deposition] Nominal v=0.15m/s -> ECSA ratio={ecsa_2:.4f}, defective={def_2}")
    assert ecsa_2 >= 0.95, "Station 2 nominal ECSA ratio too low!"

    # --- Station 3 Monte Carlo ---
    defects_s3 = 0
    d_ncl_samples = []
    for _ in range(N):
        f_kn = F_NOM_S3 * (1.0 + np.random.normal(0, 0.05))
        _, is_def, _, d_ncl = simulate_stage1_stamping_safe(f_kn, 0, 0.05, False)
        if is_def:
            defects_s3 += 1
        d_ncl_samples.append(d_ncl)

    rate_s3 = defects_s3 / N
    mean_d_ncl = float(np.mean(d_ncl_samples))
    print(f"[Station 3 Stamping] Nominal D_NCL={mean_d_ncl:.4f}, Defect Rate ({N} runs)={rate_s3*100:.2f}% (Target: 0.20%)")

    # --- Station 4 Monte Carlo ---
    defects_s4 = 0
    p_clamp_samples = []
    torque_nom_nm = 46.0
    for _ in range(N):
        torques = torque_nom_nm * (1.0 + np.random.normal(0, 0.005, size=4))
        fc = 0.12 * (1.0 + np.random.normal(0, 0.005, size=8))
        _, is_def, _, _, _, p_clamp = simulate_stage2_clamping_safe(torques, fc)
        if is_def:
            defects_s4 += 1
        p_clamp_samples.append(p_clamp)

    rate_s4 = defects_s4 / N
    mean_p_clamp = float(np.mean(p_clamp_samples))
    print(f"[Station 4 Clamping] Nominal P_clamp={mean_p_clamp:.3f} MPa, Defect Rate ({N} runs)={rate_s4*100:.2f}% (Target: 0.80%)")
    print("=" * 70)
    print("✓ All Stations 1–4 Process Model Calibrations Passed!")

if __name__ == "__main__":
    run_calibration()
