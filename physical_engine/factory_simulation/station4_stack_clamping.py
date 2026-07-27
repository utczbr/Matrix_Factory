"""
station4_stack_clamping.py — First-principles JIT Kernel for Station 4 Robotic Stack Assembly / Clamping.

Computes bolt tightening torque, elastic interaction, GDL compression & non-linear stiffness,
porosity, and assembly clamping pressure.
"""

from __future__ import annotations

import numpy as np
import numba

# ----------------------------------------------------------------------
# Group A — Geometry & Fastener Engineering Constants
# ----------------------------------------------------------------------
P_BOLT = 1.25e-3          # m, M8 thread pitch (ISO 68-1)
D2_THREAD = 7.188e-3      # m, M8 pitch diameter
R_BEARING = 5.125e-3      # m, Under-head friction effective radius
D_BOLT = 0.008            # m, M8 nominal diameter
BETA_RAD = np.radians(30.0)  # ISO flank semi-angle (60 deg total)
A_STACK = 0.0225          # m^2, Active area 150x150mm
GDL_T0_UM = 210.0         # um, Uncompressed GDL thickness
GDL_EPS0 = 0.78           # Initial GDL porosity

K_TIME_ACCELERATED = 1.0
K_TIME_INDUSTRIAL = 10.0

TORQUE_NOMINAL_NM = 46.0  # Team target nominal torque -> ~4.22 MPa clamping pressure

GDL_TSOLID_UM = GDL_T0_UM * (1.0 - GDL_EPS0)  # 46.2 um mass conservation

# ----------------------------------------------------------------------
# Group B — Calibrated Physical Constants
# ----------------------------------------------------------------------
GDL_E0_MPA = 2.80                 # MPa, initial elastic modulus at P=0 [Kleemann et al. 2009]
GDL_KS = 28.5                     # GDL non-linear stiffness parameter [Norouzifard & Bahrami 2014]
ELASTIC_COUPLING_COEF = 0.18      # Elastic interaction coefficient between adjacent bolts


@numba.njit(
    numba.types.Tuple((numba.float64, numba.boolean, numba.float64, numba.float64, numba.float64, numba.float64))(
        numba.float64[:], numba.float64[:], numba.boolean, numba.float64
    ),
    nogil=True,
    cache=True,
)
def simulate_stage2_clamping(
    applied_torques: np.ndarray,
    friction_coefficients: np.ndarray,
    is_station_4: bool,
    k_time: float,
):
    """JIT Kernel for Station 4 Clamping.

    Returns:
        proc_time_s (float): Station processing time [s].
        is_defective (bool): True if under/over-clamped or torque imbalanced.
        var_ratio (float): Processing variance ratio.
        gdl_porosity (float): Compressed GDL porosity ε in [0.01, 0.95].
        e_tangent_mpa (float): Tangent elastic modulus of compressed GDL [MPa].
        p_clamp_mpa (float): Clamping pressure [MPa].
    """
    t_base = 24.0 if is_station_4 else 3.0

    f_nom_bolts = np.zeros(4, dtype=numba.float64)
    for i in range(4):
        mu_th = friction_coefficients[i] if friction_coefficients[i] > 0.0 else 0.15
        mu_b = friction_coefficients[i + 4] if friction_coefficients[i + 4] > 0.0 else 0.15
        denom = (
            (P_BOLT / (2.0 * np.pi))
            + (mu_th * D2_THREAD / (2.0 * np.cos(BETA_RAD)))
            + (mu_b * R_BEARING)
        )
        f_nom_bolts[i] = applied_torques[i] / denom

    f_real_bolts = np.zeros(4, dtype=numba.float64)
    f_real_bolts[0] = f_nom_bolts[0] - ELASTIC_COUPLING_COEF * f_nom_bolts[3]
    f_real_bolts[1] = f_nom_bolts[1] - ELASTIC_COUPLING_COEF * f_nom_bolts[0]
    f_real_bolts[2] = f_nom_bolts[2] - ELASTIC_COUPLING_COEF * f_nom_bolts[1]
    f_real_bolts[3] = f_nom_bolts[3] - ELASTIC_COUPLING_COEF * f_nom_bolts[2]

    f_total_n = 0.0
    for i in range(4):
        f_total_n += max(0.0, f_real_bolts[i])

    p_clamp_pa = f_total_n / A_STACK
    p_clamp_mpa = p_clamp_pa / 1.0e6

    t_comp_raw = GDL_T0_UM * (1.0 - p_clamp_mpa / (GDL_E0_MPA + GDL_KS * p_clamp_mpa))
    t_comp_um = max(GDL_TSOLID_UM + 1.0, t_comp_raw)

    gdl_porosity = 1.0 - (1.0 - GDL_EPS0) * (GDL_T0_UM / t_comp_um)
    gdl_porosity = max(0.01, min(0.95, gdl_porosity))

    e_tangent_mpa = GDL_E0_MPA * ((1.0 + (GDL_KS / GDL_E0_MPA) * p_clamp_mpa) ** 2)

    tau_sum = 0.0
    for i in range(4):
        tau_sum += applied_torques[i]
    tau_mean = tau_sum / 4.0

    sq_diff = 0.0
    for i in range(4):
        sq_diff += (applied_torques[i] - tau_mean) ** 2
    tau_std_unbiased = np.sqrt(sq_diff / 3.0)

    under_clamped = p_clamp_mpa < 3.0
    over_clamped = p_clamp_mpa > 5.5
    imbalanced = tau_std_unbiased > (1.2 if is_station_4 else 1.8)
    is_defective = under_clamped or over_clamped or imbalanced

    proc_time_s = k_time * t_base * (1.0 + 0.08 * tau_std_unbiased)
    p_dev = abs(p_clamp_mpa - 4.25) / 4.25
    var_ratio = 1.0 + 0.35 * p_dev + 0.25 * tau_std_unbiased

    return proc_time_s, is_defective, var_ratio, gdl_porosity, e_tangent_mpa, p_clamp_mpa


def simulate_stage2_clamping_safe(
    applied_torques: np.ndarray | list[float],
    friction_coefficients: np.ndarray | list[float],
    is_station_4: bool = True,
    k_time: float = K_TIME_ACCELERATED,
):
    """Input validation wrapper around simulate_stage2_clamping JIT kernel."""
    at = np.asarray(applied_torques, dtype=np.float64)
    fc = np.asarray(friction_coefficients, dtype=np.float64)
    if at.shape != (4,):
        raise ValueError(f"applied_torques must have shape (4,), got {at.shape}")
    if fc.shape != (8,):
        raise ValueError(
            f"friction_coefficients must have shape (8,) [4 mu_th + 4 mu_b], got {fc.shape}"
        )
    if np.any(at < 0):
        raise ValueError("applied_torques cannot contain negative values")
    return simulate_stage2_clamping(at, fc, bool(is_station_4), float(k_time))


def run_calibration_sanity_checks(verbose: bool = True):
    results = {}

    # Check: Nominal 46.0 Nm bolt torque produces p_clamp in [3.0, 5.5] MPa (target ~4.22 MPa)
    friction_default = np.array([0.15] * 8, dtype=np.float64)
    torques_nominais = np.array([TORQUE_NOMINAL_NM] * 4, dtype=np.float64)
    r2 = simulate_stage2_clamping_safe(torques_nominais, friction_default, True)
    p_clamp_mpa = r2[5]

    results["stage2_torque_nominal_dentro_da_faixa"] = {
        "passou": (not r2[1]) and (3.0 <= p_clamp_mpa <= 5.5),
        "is_defective": r2[1],
        "p_clamp_mpa": p_clamp_mpa,
        "gdl_porosity": r2[3],
        "esperado": f"is_defective=False, 3.0 <= p_clamp ({p_clamp_mpa:.3f} MPa) <= 5.5",
    }

    if verbose:
        print("=" * 60)
        print("STATION 4 CLAMPING CALIBRATION SANITY CHECKS")
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
