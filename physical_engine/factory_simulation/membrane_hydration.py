"""
membrane_hydration.py — 1D Dynamic Membrane Hydration (λ Model).

Implements the Springer–Zawodzinski–Gottesfeld membrane conductivity correlation
and water sorption isotherm for PEMFC membranes.

Reference:
    Springer, T. E., Zawodzinski, T. A., & Gottesfeld, S. (1991).
    Polymer Electrolyte Fuel Cell Model. Journal of The Electrochemical Society, 138(8), 2334.
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


@njit(nogil=True, cache=True)
def _springer_membrane_conductivity(lambda_val: float, T_k: float) -> float:
    """Compute membrane proton conductivity σ_mem [S/cm] via Springer correlation.

    .. math::

        \\sigma_{mem}(\\lambda, T) = (0.005139 \\lambda - 0.00326) \\exp\\left(1268 \\left(\\frac{1}{303.15} - \\frac{1}{T}\\right)\\right)

    Args:
        lambda_val: Membrane water content λ (moles H₂O / mole SO₃⁻), in [1.0, 14.0].
        T_k: Temperature [K].

    Returns:
        Proton conductivity [S/cm].
    """
    lambda_clamped = max(1.0, min(14.0, float(lambda_val)))
    T_safe = max(250.0, min(420.0, float(T_k)))

    sigma_303 = 0.005139 * lambda_clamped - 0.00326
    sigma_303 = max(1e-4, sigma_303)

    temp_scaling = np.exp(1268.0 * (1.0 / 303.15 - 1.0 / T_safe))
    return float(sigma_303 * temp_scaling)


@njit(nogil=True, cache=True)
def _equilibrium_water_content(a_water: float) -> float:
    """Compute equilibrium membrane water content λ from water activity a_w.

    Sorption isotherm (Springer et al. 1991):
        a_w <= 1.0: λ = 0.043 + 17.81 a_w - 39.85 a_w² + 36.0 a_w³
        1.0 < a_w <= 3.0: λ = 14.0 + 1.4 (a_w - 1.0)
    """
    a_safe = max(0.0, min(3.0, float(a_water)))
    if a_safe <= 1.0:
        lam = 0.043 + 17.81 * a_safe - 39.85 * (a_safe ** 2) + 36.0 * (a_safe ** 3)
    else:
        lam = 14.0 + 1.4 * (a_safe - 1.0)
    return float(max(1.0, min(14.0, lam)))


@njit(nogil=True, cache=True)
def compute_membrane_resistance(
    lambda_val: float,
    T_k: float,
    delta_mem_cm: float = 0.005
) -> float:
    """Compute membrane area-specific ohmic resistance R_mem [Ω·cm²].

    Args:
        lambda_val: Membrane water content λ.
        T_k: Temperature [K].
        delta_mem_cm: Membrane thickness [cm] (default 0.005 cm = 50 µm).

    Returns:
        Ohmic resistance [Ω·cm²].
    """
    sigma = _springer_membrane_conductivity(lambda_val, T_k)
    return float(delta_mem_cm / sigma)
