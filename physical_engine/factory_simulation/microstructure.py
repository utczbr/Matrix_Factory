"""
microstructure.py — Bruggeman/Archie Microstructure & Assembly Contact Resistance Model.

Computes interfacial contact resistance R_contact [Ω·cm²] between bipolar plate
micro-grooves and compressed Gas Diffusion Layer (GDL) under clamping pressure P_assembly.

References:
    - Bruggeman, D. A. G. (1935). Berechnung verschiedener physikalischer Konstanten von heterogenen Substanzen.
    - VDI 2230 / ISO 16047 Stack Assembly Clamping Standards.
"""

from __future__ import annotations

import numpy as np

try:
    from numba import njit
except ImportError:  # pragma: no cover
    def njit(*args, **kwargs):
        def _wrap(fn):
            return fn
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return _wrap

# ----------------------------------------------------------------------
# GRUPO B -- Constantes de CALIBRACAO FISICA (calibradas com literatura primaria)
# Rastreabilidade: Mason et al. (2012) [DOI: 10.1016/j.jpowsour.2012.07.021],
# El-Kharouf et al. (2012) [DOI: 10.1016/j.jpowsour.2012.02.046].
# ----------------------------------------------------------------------
R_CONTACT_0 = 0.0042      # Ω·cm² (4.20 mΩ·cm²) [Revestido TiAlN/CrN, Mason et al. 2012]
R_CONTACT_UNCOATED = 0.0185 # Ω·cm² (18.50 mΩ·cm²) [316L Sem Revestimento, El-Kharouf et al. 2012]
P_NOMINAL_MPA = 4.25      # MPa [DECIDIDO PELO TIME — target clamping pressure]
BRUGGEMAN_EXP = 1.5      # Standard Bruggeman exponent for fibrous porous media


@njit(nogil=True, cache=True)
def compute_effective_porosity_conductivity(
    sigma_bulk: float,
    gdl_porosity: float,
    m_exponent: float = BRUGGEMAN_EXP,
) -> float:
    """Compute effective electrical/ionic conductivity via Bruggeman relation.

    .. math::

        \\sigma_{eff} = \\sigma_{bulk} (1 - \\varepsilon)^m

    Args:
        sigma_bulk: Bulk phase conductivity [S/cm].
        gdl_porosity: GDL porosity ε in [0.01, 0.95].
        m_exponent: Bruggeman exponent (default 1.5).

    Returns:
        Effective conductivity [S/cm].
    """
    eps_safe = max(0.01, min(0.95, float(gdl_porosity)))
    return float(sigma_bulk * ((1.0 - eps_safe) ** m_exponent))


@njit(nogil=True, cache=True)
def compute_contact_resistance(
    p_assembly_mpa: float,
    gdl_porosity: float = 0.78,
    r_contact_0: float = R_CONTACT_0,
) -> float:
    """Compute interfacial contact resistance R_contact [Ω·cm²].

    U-shaped contact impedance curve:
    - Under-clamping (P < 3.0 MPa): micro-contact area drops, raising contact resistance.
    - Over-clamping (P > 5.5 MPa): channel intrusion & fiber crushing distort contact interface.

    Args:
        p_assembly_mpa: Assembly clamping pressure [MPa].
        gdl_porosity: GDL porosity ε.
        r_contact_0: Nominal contact resistance [Ω·cm²] at 4.25 MPa.

    Returns:
        Interfacial contact resistance [Ω·cm²].
    """
    p_safe = max(0.5, float(p_assembly_mpa))
    p_dev = abs(p_safe - P_NOMINAL_MPA) / P_NOMINAL_MPA

    # Impedance penalty from clamping deviation
    r_contact = r_contact_0 * (1.0 + 0.35 * p_dev + 0.25 * (p_dev ** 2))
    return float(max(0.0, r_contact))


def run_calibration_sanity_checks(verbose: bool = True):
    results = {}

    # Check 1: At nominal pressure 4.25 MPa, R_contact == R_CONTACT_0 (0.0042 Ohm*cm^2)
    rc_nom = compute_contact_resistance(P_NOMINAL_MPA)
    results["r_contact_nominal_matches"] = {
        "passou": abs(rc_nom - R_CONTACT_0) < 1e-6,
        "r_contact_nom": rc_nom,
        "esperado": R_CONTACT_0,
    }

    # Check 2: U-shaped response: both under-clamping (2.0 MPa) and over-clamping (6.0 MPa) increase R_contact
    rc_under = compute_contact_resistance(2.0)
    rc_over = compute_contact_resistance(6.0)
    results["r_contact_ushaped_curve"] = {
        "passou": (rc_under > rc_nom) and (rc_over > rc_nom),
        "rc_under_2mpa": rc_under,
        "rc_over_6mpa": rc_over,
        "rc_nom": rc_nom,
    }

    # Check 3: Effective conductivity via Bruggeman relation drops as porosity increases
    sigma_bulk = 100.0
    sigma_eff_low_porosity = compute_effective_porosity_conductivity(sigma_bulk, 0.4)  # 60% solid
    sigma_eff_high_porosity = compute_effective_porosity_conductivity(sigma_bulk, 0.8) # 20% solid
    results["bruggeman_porosity_scaling"] = {
        "passou": sigma_eff_low_porosity > sigma_eff_high_porosity > 0.0,
        "sigma_eff_eps_0.4": sigma_eff_low_porosity,
        "sigma_eff_eps_0.8": sigma_eff_high_porosity,
    }

    if verbose:
        print("=" * 60)
        print("MICROSTRUCTURE CALIBRATION SANITY CHECKS")
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

