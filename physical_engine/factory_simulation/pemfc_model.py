"""
PEMFC Electrochemical Model — Station 5 End-of-Line Test Bench.

Implements a Proton Exchange Membrane Fuel Cell model using the
**subtractive** sign convention (fuel cell, NOT electrolyzer):

    V_stack(j) = N_cells × (E_ocv − η_act − η_ohm − η_conc)

This module is **strictly isolated** from the legacy electrolyzer code
(``components/electrolysis/pem_electrolyzer.py``) via ``__all__``
module-level isolation and a hard runtime guard on ``z_pemfc = 4``.

Key Equations (doc2 §3):
    - Nernst:  E = 1.229 − 0.85e-3·(T−298.15) + (RT/2F)·ln(a_H2·a_O2^0.5)
    - Activation:  η_act = (RT / αzF) · ln(j / j0)
    - Ohmic:  η_ohm = j · R_internal
    - Concentration:  η_conc = −B · ln(1 − j/j_lim)  [with C¹ patch at 0.99]

All core compute functions are decorated with ``@njit(nogil=True, cache=True)``
for Numba JIT compilation.  The ``batch_polarization_sweep`` uses
``numba.prange`` with a pre-allocated 2-D scratchpad indexed by
``i % numba_threads`` (NOT ``get_thread_id()`` — doc4 §4.2 Numba defect).

Reference: doc2 §3, doc4 §4, doc5 Phase 1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Numba import with graceful fallback
# ---------------------------------------------------------------------------
try:
    from numba import njit, prange
    import numba
    NUMBA_AVAILABLE = True
except ImportError:  # pragma: no cover
    NUMBA_AVAILABLE = False
    prange = range  # type: ignore[assignment]

    def njit(*args, **kwargs):  # type: ignore[misc]
        """Passthrough decorator when Numba is unavailable."""
        def _wrap(fn):
            return fn
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return _wrap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module isolation — prevents parameter cross-contamination (doc2 §3.1)
# ---------------------------------------------------------------------------
__all__ = [
    "calculate_nernst_potential",
    "calculate_pemfc_voltage",
    "newton_raphson_solver",
    "batch_polarization_sweep",
    "PEMFCConstants",
    "OHMIC_DEGRADATION",
    "MASS_TRANSPORT_STARVATION",
    "THERMAL_SHUTDOWN",
    "LOW_ACTIVATION",
    "SOLVER_DID_NOT_CONVERGE",
]

# ---------------------------------------------------------------------------
# Failure flag bitmask (doc4 §2 — BatchTestResponse.failure_flags)
#
# Single source of truth for the bitmask: sim_bridge_server.py imports these
# rather than redefining them, so the flag values and the physics that set
# them can never drift apart.
# ---------------------------------------------------------------------------
OHMIC_DEGRADATION: int = 0x01          # bit 0 — set in batch_polarization_sweep
MASS_TRANSPORT_STARVATION: int = 0x02  # bit 1 — set by sim_bridge_server (monotonicity check)
THERMAL_SHUTDOWN: int = 0x04           # bit 2 — set in batch_polarization_sweep
LOW_ACTIVATION: int = 0x08             # bit 3 — set in batch_polarization_sweep
SOLVER_DID_NOT_CONVERGE: int = 0x10    # bit 4

# ---------------------------------------------------------------------------
# QC thresholds for the end-of-line test bench (doc2 §3, station5 spec)
# ---------------------------------------------------------------------------
OHMIC_DEGRADATION_ETA_V: float = 0.35
"""Per-cell ohmic overpotential [V] above which the stack is flagged as
ohmically degraded (membrane/contact resistance too high)."""

THERMAL_SHUTDOWN_TEMP_K: float = 358.15
"""Operating temperature [K] (~85 degC) above which the PEM membrane is at
risk of drying out; the test bench refuses to certify a stack tested above
this temperature."""

LOW_ACTIVATION_ACTIVITY_FLOOR: float = 0.7
"""Reactant activity floor. j0/alpha (the catalyst kinetic parameters) are
fixed constants in this model — there is no per-stack "catalyst health"
input — so genuine catalyst degradation cannot be represented directly.
As a reachable proxy, a stack tested under starved reactant supply
(a_h2 or a_o2 below this floor) is flagged, since starvation pushes the
cell into the same activation-dominated regime a degraded catalyst would."""

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_R: float = 8.314462618      # J/(mol·K)  — universal gas constant
_F: float = 96485.33212      # C/mol      — Faraday constant


# ---------------------------------------------------------------------------
# PEMFC kinetic constants (doc2 §3.1)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _PEMFCConstantsData:
    """Immutable PEMFC ORR kinetic parameters.

    These values are for the **4-electron** oxygen reduction reaction
    (ORR) pathway.  The electrolyzer uses ``z = 2`` (OER/HER) — never
    share constants across the two models.
    """

    j0_orr: float = 1e-9       # Exchange current density  [A/cm²]
    z_pemfc: int = 4            # Electron transfer number (ORR)
    alpha_orr: float = 0.5      # Charge transfer coefficient
    j_lim_pemfc: float = 2.5    # Limiting current density  [A/cm²]
    B_conc: float = 0.05        # Concentration loss coefficient


PEMFCConstants = _PEMFCConstantsData()

# ---------------------------------------------------------------------------
# Runtime contamination guard — survives ``python -O`` (no assert).
# ---------------------------------------------------------------------------
if PEMFCConstants.z_pemfc != 4:
    raise RuntimeError(
        "PEMFC constant contamination detected: "
        f"z_pemfc = {PEMFCConstants.z_pemfc} (expected 4). "
        "Legacy electrolyzer constants (z=2) must never be imported "
        "into this module."
    )


# ===================================================================
# JIT-compiled core functions
# ===================================================================

@njit(nogil=True, cache=True)
def calculate_nernst_potential(
    T: float, a_h2: float, a_o2: float
) -> float:
    """Compute the open-circuit Nernst potential for a single PEMFC cell.

    .. math::

        E_{ocv} = 1.229 - 0.85 \\times 10^{-3} (T - 298.15)
                  + \\frac{R T}{2 F} \\ln(a_{H_2} \\cdot a_{O_2}^{0.5})

    Args:
        T: Stack temperature [K].
        a_h2: Dimensionless H₂ activity (P_H2 / P_ref).
        a_o2: Dimensionless O₂ activity (P_O2 / P_ref).

    Returns:
        Open-circuit voltage [V].

    Raises:
        ValueError: If activities are outside the valid range [0.5, 10.0].
    """
    # Explicit validation — no ``assert`` (survives ``-O``)
    if not (0.5 <= a_h2 <= 10.0):
        raise ValueError("H2 activity out of bounds")
    if not (0.5 <= a_o2 <= 10.0):
        raise ValueError("O2 activity out of bounds")

    R = 8.314462618
    F = 96485.33212
    E_rev_std = 1.229

    E_ocv = (
        E_rev_std
        - 0.85e-3 * (T - 298.15)
        + (R * T) / (2.0 * F) * np.log(a_h2 * a_o2 ** 0.5)
    )
    return E_ocv


@njit(nogil=True, cache=True)
def calculate_pemfc_voltage(
    j: float,
    T: float,
    a_h2: float,
    a_o2: float,
    R_internal: float,
    N_cells: int,
) -> tuple:
    """Compute the stack voltage at a given current density.

    Uses the **subtractive** fuel cell convention:

    .. math::

        V_{stack} = N_{cells} \\times (E_{ocv} - \\eta_{act}
                    - \\eta_{ohm} - \\eta_{conc})

    Includes a C¹ continuity patch for the concentration overpotential
    at ``j / j_lim > 0.99`` to prevent logarithmic divergence.

    Args:
        j: Current density [A/cm²].  Must be > 0.
        T: Temperature [K].
        a_h2: H₂ activity.
        a_o2: O₂ activity.
        R_internal: Area-specific resistance [Ω·cm²].
        N_cells: Number of cells in the stack.

    Returns:
        Tuple ``(V_stack, eta_act, eta_ohm, eta_conc, E_ocv)``.
    """
    R = 8.314462618
    F = 96485.33212
    alpha = 0.5       # alpha_orr
    z = 4             # z_pemfc
    j0 = 1e-9         # j0_orr
    j_lim = 2.5       # j_lim_pemfc
    B = 0.05           # B_conc

    E_ocv = calculate_nernst_potential(T, a_h2, a_o2)

    # --- Activation overpotential (singularity guard at j → 0) ---
    j_safe = max(j, 1e-10)
    eta_act = (R * T) / (alpha * z * F) * np.log(j_safe / j0)

    # --- Ohmic overpotential ---
    eta_ohm = j * R_internal

    # --- Concentration overpotential with C¹ continuity patch ---
    ratio = j / j_lim
    penalty_slope = B / (j_lim * 0.01)  # Analytical C¹ continuity

    if ratio <= 0.99:
        eta_conc = -B * np.log(1.0 - ratio)
    else:
        # Asymptotic bound: bypass divergent logarithm
        eta_conc = -B * np.log(0.01) + penalty_slope * (ratio - 0.99)

    # --- Stack voltage (subtractive convention) ---
    V_cell = E_ocv - eta_act - eta_ohm - eta_conc
    V_stack = N_cells * V_cell

    return (V_stack, eta_act, eta_ohm, eta_conc, E_ocv)


@njit(nogil=True, cache=True)
def newton_raphson_solver(
    V_target: float,
    T: float,
    a_h2: float,
    a_o2: float,
    R_internal: float,
    N_cells: int,
) -> tuple:
    """Solve for the current density *j* that produces *V_target*.

    Uses Newton-Raphson iteration with a closed-form analytic Jacobian
    (no finite-difference derivatives).

    Convergence criteria:
        - Absolute voltage tolerance: ``tol = 1e-4``
        - Maximum iterations: ``max_iter = 50``

    Args:
        V_target: Desired stack voltage [V].
        T: Temperature [K].
        a_h2: H₂ activity.
        a_o2: O₂ activity.
        R_internal: Area-specific resistance [Ω·cm²].
        N_cells: Number of cells in the stack.

    Returns:
        Tuple ``(j_solution, converged)`` where *converged* is True
        if ``|V(j) - V_target| < tol`` within *max_iter* iterations.
    """
    R = 8.314462618
    F = 96485.33212
    alpha = 0.5
    z = 4
    j0 = 1e-9
    j_lim = 2.5
    B = 0.05

    tol = 1e-4
    max_iter = 50

    # Initial guess: mid-range current density
    j = 1.0

    for _ in range(max_iter):
        # --- Forward evaluation ---
        V_stack, eta_act, eta_ohm, eta_conc, E_ocv = calculate_pemfc_voltage(
            j, T, a_h2, a_o2, R_internal, N_cells
        )

        residual = V_stack - V_target

        if abs(residual) < tol:
            return (j, True)

        # --- Analytic Jacobian: dV_stack/dj ---
        j_safe = max(j, 1e-10)

        # d(eta_act)/dj
        deta_act_dj = (R * T) / (alpha * z * F * j_safe)

        # d(eta_ohm)/dj
        deta_ohm_dj = R_internal

        # d(eta_conc)/dj with C¹ patch
        ratio = j / j_lim
        penalty_slope = B / (j_lim * 0.01)

        if ratio <= 0.99:
            deta_conc_dj = B / (j_lim - j)
        else:
            deta_conc_dj = penalty_slope / j_lim

        # dV_stack/dj = N_cells * (-deta_act - deta_ohm - deta_conc)
        dV_dj = N_cells * (-deta_act_dj - deta_ohm_dj - deta_conc_dj)

        if abs(dV_dj) < 1e-20:
            # Jacobian is essentially zero — cannot continue
            return (j, False)

        # Newton step with bracket clamping
        j_new = j - residual / dV_dj
        j = max(1e-10, min(j_new, 0.999 * j_lim))

    # Did not converge within max_iter
    return (j, False)


@njit(nogil=True, cache=True, parallel=True)
def batch_polarization_sweep(
    current_densities: np.ndarray,
    T: float,
    a_h2: float,
    a_o2: float,
    R_internal: float,
    N_cells: int,
    numba_threads: int,
) -> tuple:
    """Vectorized polarization curve computation via ``numba.prange``.

    Pre-allocates a 2-D scratchpad to avoid NRT heap contention across
    multiprocess daemons.  Thread isolation uses ``i % numba_threads``
    (NOT ``get_thread_id()`` — doc4 §4.2 Numba defect).

    Args:
        current_densities: Array of *j* values to evaluate [A/cm²].
        T: Temperature [K].
        a_h2: H₂ activity.
        a_o2: O₂ activity.
        R_internal: Area-specific resistance [Ω·cm²].
        N_cells: Number of cells in the stack.
        numba_threads: Number of Numba threads for scratchpad sizing.

    Returns:
        Tuple ``(voltages, failure_flags)`` where *failure_flags* is
        a ``uint32`` bitmask (0 if all points computed successfully).

    Raises:
        ValueError: If any ``current_densities >= j_lim_pemfc``.
    """
    j_lim = 2.5
    n = current_densities.shape[0]

    # Input validation BEFORE the parallel loop
    for k in range(n):
        if current_densities[k] >= j_lim:
            raise ValueError(
                "current_densities must be strictly less than j_lim_pemfc"
            )

    voltages = np.empty(n, dtype=np.float64)
    # Per-thread scratchpad: [V_stack, eta_act, eta_ohm, eta_conc, E_ocv]
    scratch = np.empty((numba_threads, 5), dtype=np.float64)
    # Per-thread flag accumulator — avoids a shared-write race inside prange.
    flag_scratch = np.zeros(numba_threads, dtype=np.uint32)

    for i in prange(n):
        j = current_densities[i]
        idx = i % numba_threads

        V_stack, eta_act, eta_ohm, eta_conc, E_ocv = calculate_pemfc_voltage(
            j, T, a_h2, a_o2, R_internal, N_cells
        )

        scratch[idx, 0] = V_stack
        scratch[idx, 1] = eta_act
        scratch[idx, 2] = eta_ohm
        scratch[idx, 3] = eta_conc
        scratch[idx, 4] = E_ocv

        voltages[i] = V_stack

        # OHMIC_DEGRADATION: ohmic overpotential exceeds the healthy ceiling
        # at any tested point (membrane/contact resistance too high).
        #
        # NOTE: OHMIC_DEGRADATION is a plain Python int at module scope (it's
        # also imported and used outside any @njit function, e.g. in
        # sim_bridge_server.py). Numba infers such literals as int64. OR-ing
        # an int64 against a uint32 accumulator makes Numba's type unifier
        # fall back to float64 as the "common" type (it can't safely unify
        # uint32 and int64), and float64 has no |= implementation — hence
        # the explicit np.uint32(...) cast at every OR site below.
        if eta_ohm > OHMIC_DEGRADATION_ETA_V:
            flag_scratch[idx] |= np.uint32(OHMIC_DEGRADATION)

    failure = np.uint32(0)
    for t in range(numba_threads):
        failure |= flag_scratch[t]

    # THERMAL_SHUTDOWN: the requested test temperature alone is enough to
    # evaluate this — constant across the sweep, so it's checked once here
    # rather than per-point.
    if T > THERMAL_SHUTDOWN_TEMP_K:
        failure |= np.uint32(THERMAL_SHUTDOWN)

    # LOW_ACTIVATION: reactant starvation proxy (see constant docstring for
    # why catalyst-kinetic degradation itself can't be modeled directly).
    if a_h2 < LOW_ACTIVATION_ACTIVITY_FLOOR or a_o2 < LOW_ACTIVATION_ACTIVITY_FLOOR:
        failure |= np.uint32(LOW_ACTIVATION)

    return (voltages, failure)