"""
station1_mea_preparation.py — First-principles JIT Kernel for Station 1 MEA Preparation (Hot-Press Lamination).

Computes resin degree of cure alpha using Kamal-Sourour autocatalytic kinetics:
    dalpha/dt = (K1 + K2 * alpha^m) * (1 - alpha)^n
    K_i = A_i * exp(-E_i / (R * T_press))

Under-cure (alpha < 0.85) increases delamination risk (R_internal penalty).
Over-cure (alpha > 0.98) increases pinhole risk (activity derate fraction).
"""

from __future__ import annotations

import numpy as np
import numba

# ----------------------------------------------------------------------
# Group A — Chemical Kinetics & Process Parameters
# ----------------------------------------------------------------------
R_GAS = 8.3145                     # J/(mol*K) Universal gas constant
A1_CURE = 1.2e4                    # 1/s Pre-exponential factor K1
E1_CURE = 58.2e3                   # J/mol Activation energy K1
A2_CURE = 5.5e6                    # 1/s Pre-exponential factor K2
E2_CURE = 68.5e3                   # J/mol Activation energy K2
M_EXP = 0.48                       # Reaction order m
N_EXP = 1.52                       # Reaction order n

T_PRESS_NOMINAL_K = 433.15         # K (160 deg C) Nominal hot-press temperature
DWELL_TIME_NOMINAL_S = 180.0       # s (3 min) Nominal hot-press dwell time
ALPHA_MIN_BOND = 0.85              # Minimum degree of cure for structural bonding
ALPHA_MAX_SAFE = 0.98              # Maximum degree of cure before thermal degradation / pinholes

K_TIME_ACCELERATED = 1.0
K_TIME_INDUSTRIAL = 10.0
T_BASE_S1 = 5.0                    # Station 1 nominal cycle time [s] in factory.jcm


@numba.njit(nogil=True, cache=True)
def integrate_kamal_sourour(t_press_k: float, dwell_time_s: float, n_steps: int = 100) -> float:
    """Integrate Kamal-Sourour cure rate using RK4 over dwell_time_s."""
    dt = dwell_time_s / float(n_steps)
    k1 = A1_CURE * np.exp(-E1_CURE / (R_GAS * t_press_k))
    k2 = A2_CURE * np.exp(-E2_CURE / (R_GAS * t_press_k))

    alpha = 0.0
    for _ in range(n_steps):
        # RK4 integration step
        def rate(a: float) -> float:
            a_clamped = max(0.0, min(0.9999, a))
            term2 = k2 * (a_clamped ** M_EXP) if a_clamped > 1e-6 else 0.0
            return (k1 + term2) * ((1.0 - a_clamped) ** N_EXP)

        rk1 = rate(alpha)
        rk2 = rate(alpha + 0.5 * dt * rk1)
        rk3 = rate(alpha + 0.5 * dt * rk2)
        rk4 = rate(alpha + dt * rk3)

        alpha += (dt / 6.0) * (rk1 + 2.0 * rk2 + 2.0 * rk3 + rk4)
        alpha = max(0.0, min(0.9999, alpha))

    return alpha


@numba.njit(
    numba.types.Tuple((numba.float64, numba.boolean, numba.float64, numba.float64, numba.float64, numba.float64))(
        numba.float64, numba.float64, numba.float64
    ),
    nogil=True,
    cache=True,
)
def simulate_stage1_mea_prep(
    t_press_k: float,
    dwell_time_s: float,
    k_time: float,
):
    """JIT Kernel for Station 1 MEA Preparation."""
    alpha_final = integrate_kamal_sourour(t_press_k, dwell_time_s)

    delamination_risk = max(0.0, ALPHA_MIN_BOND - alpha_final) / ALPHA_MIN_BOND
    pinhole_risk = max(0.0, alpha_final - ALPHA_MAX_SAFE) / (1.0 - ALPHA_MAX_SAFE)

    is_defective = (alpha_final < ALPHA_MIN_BOND) or (alpha_final > ALPHA_MAX_SAFE)

    temp_dev = abs(t_press_k - T_PRESS_NOMINAL_K) / T_PRESS_NOMINAL_K
    dwell_dev = abs(dwell_time_s - DWELL_TIME_NOMINAL_S) / DWELL_TIME_NOMINAL_S

    proc_time_s = k_time * T_BASE_S1 * (1.0 + 0.15 * temp_dev + 0.10 * dwell_dev)
    var_ratio = 1.0 + 0.30 * delamination_risk + 0.25 * pinhole_risk

    return proc_time_s, is_defective, var_ratio, alpha_final, delamination_risk, pinhole_risk


def simulate_stage1_mea_prep_safe(
    t_press_k: float = T_PRESS_NOMINAL_K,
    dwell_time_s: float = DWELL_TIME_NOMINAL_S,
    k_time: float = K_TIME_ACCELERATED,
):
    """Input validation wrapper around simulate_stage1_mea_prep JIT kernel."""
    if t_press_k < 273.15:
        raise ValueError(f"t_press_k too low: {t_press_k}")
    if dwell_time_s <= 0:
        raise ValueError(f"dwell_time_s must be positive: {dwell_time_s}")
    return simulate_stage1_mea_prep(float(t_press_k), float(dwell_time_s), float(k_time))


def run_calibration_sanity_checks(verbose: bool = True):
    results = {}

    # Check 1: Nominal hot-press (160 deg C, 180s) gives degree of cure alpha in safe range [0.85, 0.98]
    r_nom = simulate_stage1_mea_prep_safe()
    alpha_nom = r_nom[3]
    results["station1_nominal_cure_in_range"] = {
        "passou": (not r_nom[1]) and (ALPHA_MIN_BOND <= alpha_nom <= ALPHA_MAX_SAFE),
        "alpha_final": alpha_nom,
        "is_defective": r_nom[1],
        "esperado": f"0.85 <= alpha ({alpha_nom:.4f}) <= 0.98, is_defective=False",
    }

    # Check 2: Low temperature (130 deg C) results in under-cure (alpha < 0.85) -> defective
    r_cold = simulate_stage1_mea_prep_safe(t_press_k=403.15)
    results["station1_under_cure_detected"] = {
        "passou": r_cold[1] and (r_cold[3] < ALPHA_MIN_BOND),
        "alpha_cold": r_cold[3],
        "delamination_risk": r_cold[4],
    }

    if verbose:
        print("=" * 60)
        print("STATION 1 MEA PREP CALIBRATION SANITY CHECKS")
        print("=" * 60)
        for name, res in results.items():
            status = "PASSOU" if res["passou"] else "FALHOU"
            print(f"[{status}] {name}")
            for k, v in res.items():
                if k != "passou":
                    print(f"          {k}: {v}")
    return results


if __name__ == "__main__":
    run_calibration_sanity_checks()
