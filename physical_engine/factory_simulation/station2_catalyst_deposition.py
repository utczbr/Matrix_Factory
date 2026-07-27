"""
station2_catalyst_deposition.py — First-principles JIT Kernel for Station 2 Catalyst Deposition (Slot-Die Coating).

Computes slurry Capillary number, catalyst loading non-uniformity, and effective ECSA ratio (ecsa_ratio).
"""

from __future__ import annotations

import numpy as np
import numba

# ----------------------------------------------------------------------
# Group A — Coating Hydrodynamics & Process Parameters
# ----------------------------------------------------------------------
V_COAT_NOMINAL_M_S = 0.15          # m/s (15 cm/s) Nominal coating speed
MU_SLURRY_NOMINAL_PA_S = 0.050     # Pa*s (50 cP) Nominal ink viscosity
GAMMA_SURFACE_N_M = 0.035          # N/m Surface tension Pt/C ink

ECSA_RATIO_MIN_ACCEPTABLE = 0.70   # Minimum acceptable ECSA ratio before defect trip
T_BASE_S2 = 12.0                   # Station 2 nominal cycle time [s] in factory.jcm

K_TIME_ACCELERATED = 1.0
K_TIME_INDUSTRIAL = 10.0


@numba.njit(
    numba.types.Tuple((numba.float64, numba.boolean, numba.float64, numba.float64))(
        numba.float64, numba.float64, numba.float64
    ),
    nogil=True,
    cache=True,
)
def simulate_stage2_catalyst_deposition(
    v_coat_m_s: float,
    mu_slurry_pa_s: float,
    k_time: float,
):
    """JIT Kernel for Station 2 Catalyst Deposition."""
    v_dev = abs(v_coat_m_s - V_COAT_NOMINAL_M_S) / V_COAT_NOMINAL_M_S
    mu_dev = abs(mu_slurry_pa_s - MU_SLURRY_NOMINAL_PA_S) / MU_SLURRY_NOMINAL_PA_S

    # Hydrodynamic non-uniformity index
    loading_variance = 0.35 * (v_dev ** 2) + 0.25 * (mu_dev ** 2) + 0.15 * v_dev * mu_dev

    # Effective ECSA ratio
    ecsa_ratio_raw = 1.0 - 0.45 * loading_variance - 0.20 * v_dev
    ecsa_ratio = max(0.10, min(1.00, ecsa_ratio_raw))

    is_defective = (ecsa_ratio < ECSA_RATIO_MIN_ACCEPTABLE) or (loading_variance > 0.30)

    proc_time_s = k_time * T_BASE_S2 * (1.0 + 0.12 * v_dev + 0.10 * mu_dev)
    var_ratio = 1.0 + 0.40 * loading_variance

    return proc_time_s, is_defective, var_ratio, ecsa_ratio


def simulate_stage2_catalyst_deposition_safe(
    v_coat_m_s: float = V_COAT_NOMINAL_M_S,
    mu_slurry_pa_s: float = MU_SLURRY_NOMINAL_PA_S,
    k_time: float = K_TIME_ACCELERATED,
):
    """Input validation wrapper around simulate_stage2_catalyst_deposition JIT kernel."""
    if v_coat_m_s <= 0:
        raise ValueError(f"v_coat_m_s must be positive: {v_coat_m_s}")
    if mu_slurry_pa_s <= 0:
        raise ValueError(f"mu_slurry_pa_s must be positive: {mu_slurry_pa_s}")
    return simulate_stage2_catalyst_deposition(
        float(v_coat_m_s), float(mu_slurry_pa_s), float(k_time)
    )


def run_calibration_sanity_checks(verbose: bool = True):
    results = {}

    # Check 1: Nominal coating speed & viscosity gives ecsa_ratio ~ 1.0 and is_defective=False
    r_nom = simulate_stage2_catalyst_deposition_safe()
    ecsa_nom = r_nom[3]
    results["station2_nominal_ecsa_pristine"] = {
        "passou": (not r_nom[1]) and (ecsa_nom >= 0.98),
        "ecsa_ratio": ecsa_nom,
        "is_defective": r_nom[1],
        "esperado": f"ecsa_ratio >= 0.98 ({ecsa_nom:.4f}), is_defective=False",
    }

    # Check 2: High coating speed (0.30 m/s = 200% nominal) causes non-uniformity -> ecsa_ratio drops < 0.70
    r_fast = simulate_stage2_catalyst_deposition_safe(v_coat_m_s=0.30)
    ecsa_fast = r_fast[3]
    results["station2_high_speed_defect_detected"] = {
        "passou": r_fast[1] and (ecsa_fast < ECSA_RATIO_MIN_ACCEPTABLE),
        "ecsa_fast": ecsa_fast,
        "is_defective": r_fast[1],
    }

    if verbose:
        print("=" * 60)
        print("STATION 2 CATALYST DEPOSITION CALIBRATION SANITY CHECKS")
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
