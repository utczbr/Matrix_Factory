"""
station3_bipolar_plate_stamping.py — First-principles JIT Kernel for Station 3 Bipolar Plate Stamping.

Computes Archard tool wear and NCL ductile damage index for 316L bipolar plate stamping.
"""

from __future__ import annotations

import numpy as np
import numba

# ----------------------------------------------------------------------
# Group A — Traceable Engineering Constants
# ----------------------------------------------------------------------
F_NOM_S3 = 120.0          # kN, Nominal press force Station 3
A_STACK = 0.0225          # m^2, Active area 150x150mm

K_TIME_ACCELERATED = 1.0
K_TIME_INDUSTRIAL = 10.0

N_CHANNELS = 60
CHANNEL_WIDTH_MM = 1.0
CHANNEL_ENGAGED_LENGTH_MM = 20.0
A_CHANNEL_M2 = (CHANNEL_WIDTH_MM * 1e-3) * (CHANNEL_ENGAGED_LENGTH_MM * 1e-3)
A_TOTAL_CHANNELS_M2 = N_CHANNELS * A_CHANNEL_M2  # 0.0012 m^2

# ----------------------------------------------------------------------
# Group B — Calibrated Physical Constants
# ----------------------------------------------------------------------
K_WEAR_PVD = 3.50e-6              # mm^3/(N*m) [Fernandes et al. 2017]
K_WEAR_DUPLEX = 1.47e-10          # mm^3/(N*m) [Bitay et al. 2021]
GAMMA_ARCHARD = 1.35              # Archard pressure exponent
W_CRIT = 0.75                     # Critical wear ratio w/t_coating
C_CRIT_NCL = 0.35                 # NCL ductile damage threshold
K_STRENGTH_316L = 1280.0          # MPa, strength coefficient 316L
N_HARDENING_316L = 0.43           # Strain hardening exponent 316L

R_DIE_MM = 0.15                   # mm, die shoulder radius
H_COATING_MM = 0.003              # 3.0 um nominal PVD coating thickness
THETA_DIE_RAD = np.radians(10.0)  # Die draft angle
MU0_FRICTION = 0.12               # Clean friction coefficient
ALPHA_F_FRICTION = 0.45           # Friction acceleration coefficient

# Calibrated so nominal zero-wear condition (press_force=120kN, w0=0.05) gives D_NCL ~ 0.863 (< 1.0)
EPS_P_SCALE = 0.1456


@numba.njit(
    numba.types.Tuple((numba.float64, numba.boolean, numba.float64, numba.float64))(
        numba.float64, numba.int64, numba.float64, numba.boolean, numba.float64
    ),
    nogil=True,
    cache=True,
)
def simulate_stage1_stamping(
    press_force_kn: float,
    die_stroke_count: int,
    w0_initial_wear: float,
    use_duplex_coating: bool,
    k_time: float,
):
    """JIT Kernel for Station 3 Bipolar Plate Stamping."""
    f_nom = F_NOM_S3
    t_base = 3.0  # Station 3 real timing (matching factory.jcm)
    k_wear = K_WEAR_DUPLEX if use_duplex_coating else K_WEAR_PVD

    # 1. Archard Wear Model
    wear_raw = w0_initial_wear + k_wear * float(die_stroke_count) * (
        (press_force_kn / f_nom) ** GAMMA_ARCHARD
    )
    wear_ratio = min(0.99999, max(0.0, wear_raw))

    # 2. NCL Damage Index
    mu_local = MU0_FRICTION + ALPHA_F_FRICTION * wear_ratio
    eps_p_final = EPS_P_SCALE * (press_force_kn / f_nom)

    sigma_mem_mpa = (press_force_kn * 1000.0 / A_TOTAL_CHANNELS_M2) / 1.0e6
    sigma_flow_mpa = K_STRENGTH_316L * (max(eps_p_final, 1e-6) ** N_HARDENING_316L)
    sigma_1_mpa = sigma_mem_mpa * np.exp(mu_local * THETA_DIE_RAD) + sigma_flow_mpa

    if eps_p_final > 1e-4:
        work_plastic = (sigma_1_mpa / K_STRENGTH_316L) * (
            eps_p_final ** (1.0 - N_HARDENING_316L)
        ) / (1.0 - N_HARDENING_316L)
        damage_ncl = work_plastic / C_CRIT_NCL
    else:
        damage_ncl = 0.0

    damage_index = min(2.0, max(0.0, damage_ncl))
    is_defective = (damage_index > 1.0) or (wear_ratio >= W_CRIT)

    force_dev = abs(press_force_kn - f_nom) / f_nom
    proc_time_s = k_time * t_base * (1.0 + 0.12 * force_dev + 0.18 * wear_ratio)
    var_ratio = 1.0 + 0.40 * wear_ratio + 0.30 * (damage_index ** 2)

    return proc_time_s, is_defective, var_ratio, damage_index


def simulate_stage1_stamping_safe(
    press_force_kn: float,
    die_stroke_count: int,
    w0_initial_wear: float,
    use_duplex_coating: bool,
    k_time: float = K_TIME_ACCELERATED,
):
    """Input validation wrapper around simulate_stage1_stamping JIT kernel."""
    if press_force_kn < 0:
        raise ValueError(f"press_force_kn negative: {press_force_kn}")
    if die_stroke_count < 0:
        raise ValueError(f"die_stroke_count negative: {die_stroke_count}")
    if not (0.0 <= w0_initial_wear < 1.0):
        raise ValueError(f"w0_initial_wear out of range [0, 1): {w0_initial_wear}")
    return simulate_stage1_stamping(
        float(press_force_kn),
        int(die_stroke_count),
        float(w0_initial_wear),
        bool(use_duplex_coating),
        float(k_time),
    )


def run_calibration_sanity_checks(verbose: bool = True):
    results = {}

    # Check 1: Nominal condition must NOT be marked defective (damage_index < 1.0)
    r = simulate_stage1_stamping_safe(F_NOM_S3, 0, 0.05, False)
    results["stage1_nominal_nao_defeituoso"] = {
        "passou": (r[1] is False or r[1] == 0) and (r[3] < 1.0),
        "damage_index": r[3],
        "esperado": "damage_index < 1.0 (~0.863), is_defective=False",
    }

    # Check 2: Defect rate under 5% force noise stays close to 0.2% S3 target
    rng = np.random.default_rng(42)
    n_samples = 50_000
    forcas = rng.normal(F_NOM_S3, 0.05 * F_NOM_S3, n_samples)
    n_defeitos = sum(
        1 for f in forcas
        if simulate_stage1_stamping(max(0.0, f), 0, 0.05, False, K_TIME_ACCELERATED)[1]
    )
    taxa_empirica = n_defeitos / n_samples
    alvo = 0.002
    results["stage1_taxa_defeito_proxima_do_alvo_real_S3"] = {
        "passou": 0.0 <= taxa_empirica <= 0.01,
        "taxa_empirica": f"{taxa_empirica * 100:.3f}%",
        "alvo": f"{alvo * 100:.2f}%",
    }

    if verbose:
        print("=" * 60)
        print("STATION 3 STAMPING CALIBRATION SANITY CHECKS")
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
