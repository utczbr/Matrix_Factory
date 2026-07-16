# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
# cython: nonecheck=False, initializedcheck=False
"""
_numba_ops_core.pyx — Compiled Cython kernels for physical_engine.optimization.

This module provides hardened, compiled equivalents of hot-path functions
from _numba_ops_core_python.py. Only functions that have been migrated
and passed numerical parity tests are included here.

Migration Phase A: LUT interpolation kernels
Migration Phase B: Mix-property subtree (mass-weighted LUT lookups)

All functions use typed memoryviews for C-contiguous double arrays,
matching the Numba contract of the Python fallback.
"""

import numpy as np
cimport numpy as cnp
from libc.math cimport log, exp, tan, sqrt, pow, fabs

cnp.import_array()


# =============================================================================
# PHASE A — LUT Interpolation Kernels
# =============================================================================

cpdef (int, int, double, double) get_interp_weights_jit(
    double[::1] grid_x,
    double[::1] grid_y,
    double x,
    double y,
):
    """
    Calculate bilinear interpolation weights once for reuse across multiple properties.

    Returns:
        (ix, iy, wx, wy) — indices of top-left corner and interpolation weights.

    Uses binary search (bisect) for O(log N) grid lookup, matching the
    Numba fallback's np.searchsorted behavior.
    """
    cdef int ix, iy
    cdef double wx, wy
    cdef int nx = grid_x.shape[0]
    cdef int ny = grid_y.shape[0]
    cdef double x0, x1, y0, y1

    # ── X grid search ─────────────────────────────────────────────────────
    if x <= grid_x[0]:
        ix = 0
        wx = 0.0
    elif x >= grid_x[nx - 1]:
        ix = nx - 2
        wx = 1.0
    else:
        ix = _bisect_left(grid_x, x, nx) - 1
        x0 = grid_x[ix]
        x1 = grid_x[ix + 1]
        wx = (x - x0) / (x1 - x0)

    # ── Y grid search ─────────────────────────────────────────────────────
    if y <= grid_y[0]:
        iy = 0
        wy = 0.0
    elif y >= grid_y[ny - 1]:
        iy = ny - 2
        wy = 1.0
    else:
        iy = _bisect_left(grid_y, y, ny) - 1
        y0 = grid_y[iy]
        y1 = grid_y[iy + 1]
        wy = (y - y0) / (y1 - y0)

    return ix, iy, wx, wy


cpdef double interp_from_weights_jit(
    double[:, ::1] data,
    int ix,
    int iy,
    double wx,
    double wy,
):
    """
    Apply pre-calculated bilinear interpolation weights to a 2D data grid.

    f(x, y) = (1-wx)(1-wy)f00 + wx(1-wy)f10 + (1-wx)wy·f01 + wx·wy·f11
    """
    cdef double f00, f10, f01, f11

    f00 = data[ix, iy]
    f10 = data[ix + 1, iy]
    f01 = data[ix, iy + 1]
    f11 = data[ix + 1, iy + 1]

    return (
        (1.0 - wx) * (1.0 - wy) * f00
        + wx * (1.0 - wy) * f10
        + (1.0 - wx) * wy * f01
        + wx * wy * f11
    )


cpdef double bilinear_interp_jit(
    double[::1] grid_x,
    double[::1] grid_y,
    double[:, ::1] data,
    double x,
    double y,
):
    """
    Perform 2D bilinear interpolation on a regular grid.

    f(x, y) = (1-wx)(1-wy)f₀₀ + wx(1-wy)f₁₀ + (1-wx)wy·f₀₁ + wx·wy·f₁₁

    Clamps query coordinates to the grid bounds (extrapolation = nearest).
    """
    cdef int ix, iy
    cdef int nx = grid_x.shape[0]
    cdef int ny = grid_y.shape[0]
    cdef double x0, x1, y0, y1, dx, dy, wx, wy
    cdef double q00, q01, q10, q11

    # ── X index ───────────────────────────────────────────────────────────
    if x <= grid_x[0]:
        ix = 1
    elif x >= grid_x[nx - 1]:
        ix = nx - 1
    else:
        ix = _bisect_left(grid_x, x, nx)
        if ix == 0:
            ix = 1

    # ── Y index ───────────────────────────────────────────────────────────
    if y <= grid_y[0]:
        iy = 1
    elif y >= grid_y[ny - 1]:
        iy = ny - 1
    else:
        iy = _bisect_left(grid_y, y, ny)
        if iy == 0:
            iy = 1

    x0 = grid_x[ix - 1]
    x1 = grid_x[ix]
    y0 = grid_y[iy - 1]
    y1 = grid_y[iy]

    q00 = data[ix - 1, iy - 1]
    q01 = data[ix - 1, iy]
    q10 = data[ix, iy - 1]
    q11 = data[ix, iy]

    dx = x1 - x0
    dy = y1 - y0

    if dx == 0.0:
        wx = 0.0
    else:
        wx = (x - x0) / dx

    if dy == 0.0:
        wy = 0.0
    else:
        wy = (y - y0) / dy

    return (
        q00 * (1.0 - wx) * (1.0 - wy)
        + q10 * wx * (1.0 - wy)
        + q01 * (1.0 - wx) * wy
        + q11 * wx * wy
    )


def batch_bilinear_interp_jit(
    double[::1] grid_x,
    double[::1] grid_y,
    double[:, ::1] data,
    double[::1] x_arr,
    double[::1] y_arr,
):
    """
    Vectorized 2D bilinear interpolation over coordinate arrays.

    This is a serial loop in Cython (no OpenMP prange in Phase A).
    Still significantly faster than pure Python due to C-level execution
    and elimination of interpreter overhead.

    Note: The Numba fallback uses parallel=True / prange. The Cython
    version can be upgraded to use OpenMP prange in a future phase if
    profiling shows it is the bottleneck.

    Args:
        grid_x: Sorted x coordinates (1D, C-contiguous).
        grid_y: Sorted y coordinates (1D, C-contiguous).
        data: 2D lookup table (C-contiguous).
        x_arr: Query x coordinates (1D, C-contiguous).
        y_arr: Query y coordinates (1D, C-contiguous, same length as x_arr).

    Returns:
        np.ndarray: Interpolated values (float64).
    """
    cdef int n = x_arr.shape[0]
    cdef cnp.ndarray[double, ndim=1] results = np.zeros(n, dtype=np.float64)
    cdef double[::1] results_view = results
    cdef int i

    for i in range(n):
        results_view[i] = bilinear_interp_jit(grid_x, grid_y, data, x_arr[i], y_arr[i])

    return results


# =============================================================================
# PHASE B — Mix-Property Subtree
# =============================================================================

cpdef double get_mix_cp_jit(
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, :, ::1] C_luts,
    double[::1] weights,
    int ix,
    int iy,
    double wx,
    double wy,
):
    """
    Calculate mixture Cp (mass weighted) using pre-calculated interpolation weights.

    cp_mix = Σ(w_i × Cp_i(P, T))
    """
    cdef double cp_mix = 0.0
    cdef int n = weights.shape[0]
    cdef int i
    cdef double c_val

    for i in range(n):
        if weights[i] > 1e-9:
            c_val = interp_from_weights_jit(C_luts[i], ix, iy, wx, wy)
            cp_mix += weights[i] * c_val
    return cp_mix


cpdef double get_mix_enthalpy_fast_jit(
    double[:, :, ::1] H_luts,
    double[::1] weights,
    int ix,
    int iy,
    double wx,
    double wy,
):
    """
    Calculate mixture enthalpy (mass weighted) using pre-calculated weights.

    h_mix = Σ(w_i × H_i(P, T))
    """
    cdef double h_mix = 0.0
    cdef int n = weights.shape[0]
    cdef int i
    cdef double val

    for i in range(n):
        if weights[i] > 1e-9:
            val = interp_from_weights_jit(H_luts[i], ix, iy, wx, wy)
            h_mix += weights[i] * val
    return h_mix


cpdef double get_mix_density_jit(
    double[:, :, ::1] D_luts,
    double[::1] weights,
    int ix,
    int iy,
    double wx,
    double wy,
):
    """
    Calculate mixture density (Amagat's Law / Volume Additivity).

    rho_mix = 1 / Σ(w_i / rho_i)
    """
    cdef double sum_vol_spec = 0.0
    cdef int n = weights.shape[0]
    cdef int i
    cdef double rho_i

    for i in range(n):
        if weights[i] > 1e-9:
            rho_i = interp_from_weights_jit(D_luts[i], ix, iy, wx, wy)
            if rho_i > 1e-6:
                sum_vol_spec += weights[i] / rho_i

    if sum_vol_spec > 1e-9:
        return 1.0 / sum_vol_spec
    return 0.0


cpdef double calculate_mixture_density_jit(
    double p_pa,
    double T_k,
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, :, ::1] D_luts,
    double[::1] weights,
):
    """
    Calculate mixture density using stacked LUTs.

    Computes interpolation weights from (P, T), then delegates to
    get_mix_density_jit for the mass-weighted volume-additivity calculation.
    """
    cdef int ix, iy
    cdef double wx, wy

    ix, iy, wx, wy = get_interp_weights_jit(P_grid, T_grid, p_pa, T_k)
    return get_mix_density_jit(D_luts, weights, ix, iy, wx, wy)


cpdef double get_mix_entropy_fast_jit(
    double[:, :, ::1] S_luts,
    double[::1] weights,
    double[::1] mole_fracs,
    double M_mix_kg_mol,
    double sum_ylny,
    int ix,
    int iy,
    double wx,
    double wy,
):
    """
    Calculate mixture entropy (mass weighted + ideal mixing term).

    s_mix = Σ(w_i × S_i) - (R / M_mix) × Σ(y_i × ln(y_i))

    The mixing term is always positive (since Σ(y ln y) < 0 for a mixture),
    representing the entropy increase from mixing ideal gases.
    """
    cdef double R_UNIVERSAL = 8.314462618
    cdef double s_base = 0.0
    cdef double s_mixing, R_mix, val
    cdef int n = weights.shape[0]
    cdef int i

    # Base entropy from species LUTs
    for i in range(n):
        if weights[i] > 1e-9:
            val = interp_from_weights_jit(S_luts[i], ix, iy, wx, wy)
            s_base += weights[i] * val

    # Ideal mixing term
    if M_mix_kg_mol > 1e-9:
        R_mix = R_UNIVERSAL / M_mix_kg_mol
        s_mixing = -R_mix * sum_ylny
    else:
        s_mixing = 0.0

    return s_base + s_mixing


# =============================================================================
# PHASE C — SCALAR THERMO / UTILITIES
# =============================================================================

cpdef double calculate_water_psat_jit(double T_k):
    """
    Calculate Saturation Pressure of Water (Pa) using Antoine Equation.
    Valid range: 273K - 647K (Critical point).
    """
    cdef double A, B, C
    cdef double p_log10, p_bar

    if T_k < 373.15:
        A, B, C = 5.40221, 1838.675, -31.737
    else:
        A, B, C = 5.20389, 1733.926, -39.485

    p_log10 = A - (B / (T_k + C))
    p_bar = pow(10.0, p_log10)
    return p_bar * 100000.0


cpdef double solve_water_T_from_H_jit(double target_h_j_kg, double P_pa, double T_guess_k):
    """
    Newton-Raphson solver to find Temperature from Enthalpy for Liquid Water.
    """
    cdef double T_iter = T_guess_k
    cdef double tol = 0.01
    cdef double Cp_water = 4184.0
    cdef double T_ref = 273.15
    cdef double h_calc, error, dT
    cdef int i

    for i in range(10):
        h_calc = Cp_water * (T_iter - T_ref)
        error = h_calc - target_h_j_kg
        if fabs(error) < (tol * Cp_water):
            return T_iter

        dT = error / Cp_water
        T_iter -= dT

        if T_iter < 273.15:
            T_iter = 273.15
        if T_iter > 647.0:
            T_iter = 647.0

    return T_iter


cpdef double solve_rachford_rice_single_condensable(double z_condensable, double K_value):
    """
    Computes vapor fraction for a binary system with one condensable component.
    """
    cdef double beta

    if K_value >= 1.0:
        return 1.0

    if z_condensable < 1e-12:
        return 1.0

    if z_condensable <= K_value:
        return 1.0

    beta = (1.0 - z_condensable) / (1.0 - K_value)

    if beta < 0.0:
        beta = 0.0
    elif beta > 1.0:
        beta = 1.0

    return beta


cpdef double calculate_mixture_enthalpy(
    double temperature,
    double[::1] mole_fractions,
    double[::1] h_formations,
    double[:, ::1] cp_coeffs_matrix,
    double T_ref=298.15,
):
    """Calculate molar enthalpy of a mixture using NASA polynomial integration."""
    cdef double h_mix = 0.0
    cdef int n = mole_fractions.shape[0]
    cdef int i
    cdef double h_form, A, B, C, D, E
    cdef double delta_h, h_species
    cdef double T2, T3, T4, Tr2, Tr3, Tr4

    T2 = temperature * temperature
    T3 = T2 * temperature
    T4 = T3 * temperature
    Tr2 = T_ref * T_ref
    Tr3 = Tr2 * T_ref
    Tr4 = Tr3 * T_ref

    for i in range(n):
        if mole_fractions[i] < 1e-12:
            continue

        h_form = h_formations[i]
        A = cp_coeffs_matrix[i, 0]
        B = cp_coeffs_matrix[i, 1]
        C = cp_coeffs_matrix[i, 2]
        D = cp_coeffs_matrix[i, 3]
        E = cp_coeffs_matrix[i, 4]

        if temperature > 0.0 and T_ref > 0.0:
            delta_h = (
                A * (temperature - T_ref)
                + 0.5 * B * (T2 - Tr2)
                + (1.0 / 3.0) * C * (T3 - Tr3)
                + 0.25 * D * (T4 - Tr4)
                - E * (1.0 / temperature - 1.0 / T_ref)
            )
        else:
            delta_h = (
                A * (temperature - T_ref)
                + 0.5 * B * (T2 - Tr2)
                + (1.0 / 3.0) * C * (T3 - Tr3)
                + 0.25 * D * (T4 - Tr4)
            )

        h_species = h_form + delta_h
        h_mix += mole_fractions[i] * h_species

    return h_mix


cpdef double calculate_mixture_cp(
    double temperature,
    double[::1] mole_fractions,
    double[:, ::1] cp_coeffs_matrix,
    double T_ref=298.15,
):
    """Calculate mixture molar heat capacity at constant pressure."""
    cdef double cp_mix = 0.0
    cdef int n = mole_fractions.shape[0]
    cdef int i
    cdef double A, B, C, D, E
    cdef double cp_species

    for i in range(n):
        if mole_fractions[i] < 1e-12:
            continue

        A = cp_coeffs_matrix[i, 0]
        B = cp_coeffs_matrix[i, 1]
        C = cp_coeffs_matrix[i, 2]
        D = cp_coeffs_matrix[i, 3]
        E = cp_coeffs_matrix[i, 4]

        if temperature > 0.0:
            cp_species = (
                A
                + B * temperature
                + C * (temperature * temperature)
                + D * (temperature * temperature * temperature)
                + E / (temperature * temperature)
            )
        else:
            cp_species = (
                A
                + B * temperature
                + C * (temperature * temperature)
                + D * (temperature * temperature * temperature)
            )

        cp_mix += mole_fractions[i] * cp_species

    return cp_mix


# =============================================================================
# PHASE C — PEM ELECTROLYZER
# =============================================================================

cpdef double calculate_pem_voltage_jit(
    double j,
    double T,
    double P_op,
    double R,
    double F,
    int z,
    double alpha,
    double j0,
    double j_lim,
    double delta_mem,
    double sigma_base,
    double P_ref,
):
    """Calculate PEM electrolyzer cell voltage."""
    cdef double U_rev_T, pressure_ratio, nernst_correction, U_rev
    cdef double j_safe, eta_act, eta_ohm, eta_conc

    U_rev_T = 1.229 - 0.9e-3 * (T - 298.15)
    pressure_ratio = P_op / P_ref
    nernst_correction = (R * T) / (z * F) * log(pressure_ratio ** 1.5)
    U_rev = U_rev_T + nernst_correction

    j_safe = j if j > 1e-10 else 1e-10
    eta_act = (R * T) / (alpha * z * F) * log(j_safe / j0)
    eta_ohm = j * (delta_mem / sigma_base)

    if j >= j_lim:
        eta_conc = 100.0
    else:
        eta_conc = (R * T) / (z * F) * log(j_lim / (j_lim - j_safe))

    return U_rev + eta_act + eta_ohm + eta_conc


cpdef double solve_pem_j_jit(
    double target_power_W,
    double T,
    double P_op,
    double Area_Total,
    double P_bop_fixo,
    double k_bop_var,
    double j_guess,
    double R,
    double F,
    int z,
    double alpha,
    double j0,
    double j_lim,
    double delta_mem,
    double sigma_base,
    double P_ref,
    int max_iter=50,
    double tol=1e-4,
):
    """Solve for current density that matches target power setpoint."""
    cdef double x = j_guess
    cdef int i
    cdef double V_c, I_t, P_stack, P_total, fx
    cdef double delta, x_delta, V_c_d, I_t_d, P_stack_d, P_total_d, fx_delta, dfx

    for i in range(max_iter):
        V_c = calculate_pem_voltage_jit(x, T, P_op, R, F, z, alpha, j0, j_lim, delta_mem, sigma_base, P_ref)
        I_t = x * Area_Total
        P_stack = I_t * V_c
        P_total = P_stack * (1.0 + k_bop_var) + P_bop_fixo
        fx = P_total - target_power_W

        if fabs(fx) < tol:
            return x

        delta = 1e-5
        x_delta = x + delta
        V_c_d = calculate_pem_voltage_jit(x_delta, T, P_op, R, F, z, alpha, j0, j_lim, delta_mem, sigma_base, P_ref)
        I_t_d = x_delta * Area_Total
        P_stack_d = I_t_d * V_c_d
        P_total_d = P_stack_d * (1.0 + k_bop_var) + P_bop_fixo
        fx_delta = P_total_d - target_power_W

        dfx = (fx_delta - fx) / delta
        if dfx == 0.0:
            break

        x = x - fx / dfx
        if x < 1e-6:
            x = 1e-6

    return x


# =============================================================================
# PHASE C — SPLINES / INTERPOLATION
# =============================================================================

cpdef double eval_cubic_spline(
    double x_val,
    double[::1] breaks,
    double[:, ::1] coeffs,
):
    """Evaluate cubic spline at x_val using pre-computed coefficients."""
    cdef int n_breaks = breaks.shape[0]
    cdef int idx
    cdef double dx, a, b, c, d, x_i

    if x_val <= breaks[0]:
        return coeffs[0, 0]

    if x_val >= breaks[n_breaks - 1]:
        idx = n_breaks - 2
        dx = breaks[n_breaks - 1] - breaks[idx]
        a = coeffs[idx, 0]
        b = coeffs[idx, 1]
        c = coeffs[idx, 2]
        d = coeffs[idx, 3]
        return a + dx * (b + dx * (c + dx * d))

    idx = _bisect_left(breaks, x_val, n_breaks) - 1
    if idx < 0:
        idx = 0
    if idx >= n_breaks - 1:
        idx = n_breaks - 2

    x_i = breaks[idx]
    dx = x_val - x_i

    a = coeffs[idx, 0]
    b = coeffs[idx, 1]
    c = coeffs[idx, 2]
    d = coeffs[idx, 3]

    return a + dx * (b + dx * (c + dx * d))


cpdef double bilinear_interp_liquid(
    double[::1] grid_p,
    double[::1] grid_t,
    double[:, ::1] data,
    double p,
    double t,
):
    """Bilinear interpolation with liquid water bounds clamping."""
    cdef double p_safe = p
    cdef double t_safe = t

    if p_safe < 1e5:
        p_safe = 1e5
    if p_safe > 20e5:
        p_safe = 20e5

    if t_safe < 273.15:
        t_safe = 273.15
    if t_safe > 373.15:
        t_safe = 373.15

    return bilinear_interp_jit(grid_p, grid_t, data, p_safe, t_safe)


# =============================================================================
# PHASE C — HEAT TRANSFER CORRELATIONS
# =============================================================================

cpdef double dry_cooler_ntu_effectiveness(double ntu, double r):
    """Calculate effectiveness for unmixed-mixed crossflow heat exchanger."""
    cdef double term

    if ntu <= 0.0:
        return 0.0

    if fabs(r - 1.0) < 1e-6:
        return ntu / (1.0 + ntu)

    term = exp(-ntu * (1.0 + r))
    return (1.0 - term) / (1.0 + r * term)


cpdef double counter_flow_ntu_effectiveness(double ntu, double r):
    """Calculate effectiveness for counter-flow heat exchanger."""
    cdef double term

    if ntu <= 0.0:
        return 0.0

    if fabs(r - 1.0) < 1e-6:
        return ntu / (1.0 + ntu)

    term = exp(-ntu * (1.0 - r))
    return (1.0 - term) / (1.0 - r * term)


cpdef double calculate_reynolds_flux(
    double mass_flow_kg_s,
    double flow_area_m2,
    double d_hydraulic,
    double visc_pa_s,
):
    """Calculate Reynolds number using mass flux."""
    cdef double G

    if flow_area_m2 <= 1e-9 or visc_pa_s <= 1e-9:
        return 0.0
    G = mass_flow_kg_s / flow_area_m2
    return (G * d_hydraulic) / visc_pa_s


cpdef double calculate_nusselt_dittus_boelter(double re, double pr, bint is_heating):
    """Dittus-Boelter correlation for internal turbulent flow."""
    cdef double exponent

    if re < 2300.0:
        return 3.66

    exponent = 0.4 if is_heating else 0.3
    return 0.023 * (re ** 0.8) * (pr ** exponent)


cpdef double calculate_nusselt_crossflow(double re, double pr):
    """Simplified Zukauskas correlation for crossflow over tube banks."""
    if re < 100.0:
        return 1.0
    return 0.27 * (re ** 0.63) * (pr ** 0.33)


# =============================================================================
# PHASE C — FLASH / CYCLONE
# =============================================================================

cpdef double solve_ph_flash_jit(
    double h_target_molar,
    double[::1] mole_fractions,
    double[::1] h_formations,
    double[:, ::1] cp_coeffs_matrix,
    double T_guess,
    double tol=0.05,
    int max_iter=10,
):
    """Find T such that H_mix(T) = h_target using Newton-Raphson."""
    cdef double T = T_guess
    cdef int i
    cdef double h_calc, cp_calc, delta_T

    for i in range(max_iter):
        h_calc = calculate_mixture_enthalpy(T, mole_fractions, h_formations, cp_coeffs_matrix)
        cp_calc = calculate_mixture_cp(T, mole_fractions, cp_coeffs_matrix)

        if fabs(cp_calc) < 1e-4:
            break

        delta_T = (h_target_molar - h_calc) / cp_calc
        T = T + delta_T

        if fabs(delta_T) < tol:
            break

        if T < 275.0:
            T = 275.0
        elif T > 5000.0:
            T = 5000.0

    return T


cpdef double _antoine_psat_water(double T_k):
    """Antoine equation for water saturation pressure (Pa)."""
    cdef double T_C = T_k - 273.15
    cdef double val, p_mmhg

    if T_C < 0.01:
        T_C = 0.01

    val = 8.07131 - 1730.63 / (233.426 + T_C)
    p_mmhg = pow(10.0, val)
    return p_mmhg * 133.322


cpdef tuple solve_cyclone_mechanics(
    double Q_gas_m3s,
    double rho_g,
    double rho_l,
    double mu_g,
    double D_element_m,
    double vane_angle_rad,
    int N_tubes,
):
    """Compute cyclone separation performance and hydrodynamics."""
    cdef double D_hub, Area_annulus, v_axial, v_tan
    cdef double r_mean, g_spin, L_sep, t_res, s_drift
    cdef double density_diff, d50_sq, d50_microns
    cdef double Xi, delta_P_pa
    cdef double pi = 3.141592653589793

    if N_tubes <= 0 or Q_gas_m3s <= 1e-9:
        return 0.0, 0.0, 0.0, 0.0

    D_hub = 0.3 * D_element_m
    Area_annulus = (pi / 4.0) * (D_element_m * D_element_m - D_hub * D_hub)

    v_axial = Q_gas_m3s / (N_tubes * Area_annulus)
    v_tan = v_axial * tan(vane_angle_rad)

    r_mean = (D_element_m + D_hub) / 4.0
    g_spin = (v_tan * v_tan) / r_mean

    L_sep = 3.0 * D_element_m
    t_res = L_sep / v_axial if v_axial > 1e-9 else 1e6
    s_drift = (D_element_m - D_hub) / 2.0

    density_diff = rho_l - rho_g
    if density_diff > 0.0 and g_spin > 0.0 and t_res > 0.0:
        d50_sq = (18.0 * mu_g * s_drift) / (density_diff * g_spin * t_res)
        d50_microns = sqrt(d50_sq) * 1e6
    else:
        d50_microns = 0.0

    Xi = 4.8
    delta_P_pa = Xi * 0.5 * rho_g * (v_axial * v_axial)

    return d50_microns, delta_P_pa, v_axial, v_tan


# =============================================================================
# INTERNAL HELPERS (cdef — not exported to Python)
# =============================================================================

cdef int _bisect_left(double[::1] arr, double val, int n) noexcept nogil:
    """
    Binary search equivalent to np.searchsorted(arr, val, side='left').

    Returns insertion point for val in sorted arr[0:n] such that
    all elements arr[:result] < val. Pure C, no GIL.

    Matches np.searchsorted default (side='left') behavior exactly.
    """
    cdef int lo = 0
    cdef int hi = n
    cdef int mid

    while lo < hi:
        mid = (lo + hi) >> 1
        if arr[mid] < val:
            lo = mid + 1
        else:
            hi = mid
    return lo

import numpy as np
cimport numpy as cnp
from libc.math cimport exp

# =============================================================================
# TANK STATE CONSTANTS
# =============================================================================
# Matches physical_engine.core.enums.TankState
cdef int TANK_STATE_IDLE = 0
cdef int TANK_STATE_FILLING = 1
cdef int TANK_STATE_DISCHARGING = 2
cdef int TANK_STATE_FULL = 3
cdef int TANK_STATE_EMPTY = 4
cdef int TANK_STATE_MAINTENANCE = 5

# =============================================================================
# STORAGE OPERATIONS
# =============================================================================

cpdef int find_available_tank(
    int[::1] states,
    double[::1] masses,
    double[::1] capacities,
    double min_capacity=0.0,
):
    """Identifies the first storage unit capable of accepting mass."""
    cdef int i
    cdef int n = states.shape[0]
    cdef double available_capacity

    for i in range(n):
        available_capacity = capacities[i] - masses[i]
        if (states[i] == TANK_STATE_IDLE or states[i] == TANK_STATE_EMPTY) and available_capacity >= min_capacity:
            return i
    return -1


cpdef int find_fullest_tank(
    int[::1] states,
    double[::1] masses,
    double min_mass=0.0,
):
    """Selects the optimal tank for discharge based on mass inventory."""
    cdef int i
    cdef int n = states.shape[0]
    cdef double max_mass = -1.0
    cdef int best_idx = -1

    for i in range(n):
        if (states[i] == TANK_STATE_IDLE or states[i] == TANK_STATE_FULL) and masses[i] >= min_mass:
            if masses[i] > max_mass:
                max_mass = masses[i]
                best_idx = i

    return best_idx


cpdef void batch_pressure_update(
    double[::1] masses,
    double[::1] volumes,
    double[::1] pressures,
    double temperature,
    double gas_constant=4124.0,
):
    """Update pressures for all tanks using ideal gas law (in-place)."""
    cdef int i
    cdef int n = masses.shape[0]
    cdef double density

    for i in range(n):
        if volumes[i] > 0.0:
            density = masses[i] / volumes[i]
            pressures[i] = density * gas_constant * temperature
        else:
            pressures[i] = 0.0


cpdef void batch_pressure_update_vector_T(
    double[::1] masses,
    double[::1] volumes,
    double[::1] pressures,
    double[::1] temperatures,
    double gas_constant,
):
    """Update pressures using ideal gas law with PER-TANK temperature (in-place)."""
    cdef int i
    cdef int n = masses.shape[0]
    cdef double density

    for i in range(n):
        if volumes[i] > 0.0:
            density = masses[i] / volumes[i]
            pressures[i] = density * gas_constant * temperatures[i]
        else:
            pressures[i] = 0.0


cpdef tuple distribute_mass_to_tanks(
    double total_mass,
    int[::1] states,
    double[::1] masses,
    double[::1] capacities,
):
    """Distribute mass across available tanks, filling sequentially."""
    cdef int i
    cdef int n = masses.shape[0]
    cdef double remaining = total_mass
    cdef double available_capacity, mass_to_add

    for i in range(n):
        if remaining <= 0.0:
            break

        if not (states[i] == TANK_STATE_IDLE or states[i] == TANK_STATE_EMPTY):
            continue

        available_capacity = capacities[i] - masses[i]
        mass_to_add = remaining if remaining < available_capacity else available_capacity

        masses[i] += mass_to_add
        remaining -= mass_to_add

        if masses[i] >= capacities[i] * 0.99:
            states[i] = TANK_STATE_FULL

    return np.asarray(masses), remaining


cpdef tuple distribute_mass_and_energy(
    double total_mass,
    double T_in,
    int[::1] states,
    double[::1] masses,
    double[::1] temperatures,
    double[::1] capacities,
    double gamma=1.41,
):
    """Distribute mass and update temperatures based on enthalpy addition."""
    cdef int i
    cdef int n = masses.shape[0]
    cdef double remaining = total_mass
    cdef double available_capacity, mass_to_add
    cdef double m_old, T_old, numerator, denom, T_new

    for i in range(n):
        if remaining <= 0.0:
            break

        if not (states[i] == TANK_STATE_IDLE or states[i] == TANK_STATE_EMPTY):
            continue

        available_capacity = capacities[i] - masses[i]
        mass_to_add = remaining if remaining < available_capacity else available_capacity

        if mass_to_add > 0.0:
            m_old = masses[i]
            T_old = temperatures[i]

            # Energy Balance (Adiabatic mixing)
            if m_old > 0.0:
                numerator = (m_old * T_old) + (mass_to_add * gamma * T_in)
                denom = m_old + mass_to_add
                T_new = numerator / denom
            else:
                T_new = gamma * T_in
                if T_new > 500.0:
                    T_new = 500.0
            
            masses[i] += mass_to_add
            temperatures[i] = T_new
            remaining -= mass_to_add

            if masses[i] >= capacities[i] * 0.99:
                states[i] = TANK_STATE_FULL

    return np.asarray(masses), np.asarray(temperatures), remaining


cpdef double calculate_total_mass_by_state(
    int[::1] states,
    double[::1] masses,
    int target_state,
):
    """Calculate total mass in tanks matching a specific state."""
    cdef int i
    cdef int n = states.shape[0]
    cdef double total = 0.0

    for i in range(n):
        if states[i] == target_state:
            total += masses[i]

    return total


cpdef tuple simulate_filling_timestep(
    double production_rate,
    double dt,
    int[::1] tank_states,
    double[::1] tank_masses,
    double[::1] tank_capacities,
):
    """Simulate one timestep of production filling tanks."""
    cdef double production = production_rate * dt
    cdef double overflow

    _, overflow = distribute_mass_to_tanks(
        production,
        tank_states,
        tank_masses,
        tank_capacities
    )
    
    cdef double stored = production - overflow
    return stored, overflow


cpdef void apply_heat_loss_batch(
    double[::1] temperatures,
    double[::1] masses,
    double T_amb,
    double dt_seconds,
    double UA,
    double Cv,
):
    """Apply Newton's Law of Cooling (Thermal Relaxation)."""
    cdef int i
    cdef int n = temperatures.shape[0]
    cdef double tau, decay

    for i in range(n):
        if masses[i] > 1e-6:
            tau = (masses[i] * Cv) / UA
            if tau < 1e-9:
                 temperatures[i] = T_amb
            else:
                decay = exp(-dt_seconds / tau)
                temperatures[i] = T_amb + (temperatures[i] - T_amb) * decay
        else:
            temperatures[i] = T_amb


# =============================================================================
# STORAGE MPC (Model Predictive Control)
# =============================================================================

cpdef double calculate_storage_mpc_factor(
    double current_soc,
    double total_capacity_kg,
    double[::1] production_profile_kg_h,
    double[::1] demand_profile_kg_h,
    double dt_hours,
    double soc_limit_high=0.98,
    int horizon_steps=60,
):
    """Simplified MPC: Calculates action factor to prevent storage overflow."""
    if total_capacity_kg <= 1e-6:
        return 0.0

    cdef double sim_soc = current_soc
    cdef double max_violation_kg = 0.0
    cdef double cum_potential_production_kg = 0.0
    
    cdef int prod_len = production_profile_kg_h.shape[0]
    cdef int demand_len = demand_profile_kg_h.shape[0]
    cdef int steps = prod_len if prod_len < horizon_steps else horizon_steps
    
    cdef int i
    cdef double prod, dem, step_prod_kg, delta_mass, delta_soc
    cdef double current_excess_soc, limit_violation_soc, total_violation_soc, total_violation_kg
    cdef double reduction_ratio, factor
    
    for i in range(steps):
        prod = production_profile_kg_h[i]
        dem = demand_profile_kg_h[i] if i < demand_len else 0.0
        
        step_prod_kg = prod * dt_hours
        cum_potential_production_kg += step_prod_kg
        
        delta_mass = (prod - dem) * dt_hours
        delta_soc = delta_mass / total_capacity_kg
        sim_soc += delta_soc
        
        current_excess_soc = 0.0
        if sim_soc > 1.0:
            current_excess_soc = sim_soc - 1.0
            sim_soc = 1.0 
            
        limit_violation_soc = 0.0
        if sim_soc > soc_limit_high:
            limit_violation_soc = sim_soc - soc_limit_high
            
        total_violation_soc = limit_violation_soc + current_excess_soc
        total_violation_kg = total_violation_soc * total_capacity_kg
        
        if total_violation_kg > max_violation_kg:
            max_violation_kg = total_violation_kg

    if max_violation_kg <= 1e-6:
        return 1.0
        
    if cum_potential_production_kg <= 1e-6:
        return 0.0 

    reduction_ratio = max_violation_kg / cum_potential_production_kg
    factor = 1.0 - reduction_ratio
    
    if factor < 0.0:
        return 0.0
    if factor > 1.0:
        return 1.0
    
    return factor

import numpy as np
cimport numpy as cnp
from libc.math cimport fabs

# =============================================================================
# ELECTRIC BOILER & FLASH JIT KERNELS
# =============================================================================

cpdef double calc_boiler_outlet_enthalpy(
    double h_in_j_kg,
    double mass_flow_kg_h,
    double power_input_w,
    double efficiency,
):
    """Computes outlet enthalpy based on the First Law of Thermodynamics (Steady Flow)."""
    cdef double q_net_w, q_net_j_h, delta_h

    # Zero Flow Protection
    if mass_flow_kg_h <= 1e-6:
        return h_in_j_kg
        
    q_net_w = power_input_w * efficiency
    q_net_j_h = q_net_w * 3600.0  # W (J/s) to J/h
    delta_h = q_net_j_h / mass_flow_kg_h
    
    return h_in_j_kg + delta_h


cpdef cnp.ndarray calc_boiler_batch_scenario(
    double[::1] h_in_array,
    double[::1] flow_array,
    double[::1] power_array,
    double efficiency,
):
    """Vectorized version for rapid scenario analysis."""
    cdef int n = h_in_array.shape[0]
    cdef int i
    
    # Allocate numpy array and create a fast memoryview for the loop
    cdef cnp.ndarray[double, ndim=1] h_out_array = np.zeros(n, dtype=np.float64)
    cdef double[::1] h_out_view = h_out_array
    
    for i in range(n):
        h_out_view[i] = calc_boiler_outlet_enthalpy(
            h_in_array[i],
            flow_array[i],
            power_array[i],
            efficiency
        )
        
    return h_out_array


cpdef double solve_temperature_from_enthalpy_jit(
    double h_target,
    double pressure_pa,
    double T_guess,
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, ::1] H_lut,
    double[:, ::1] C_lut,
    double cp_default=4180.0,
    double tol=0.01,
    int max_iter=20,
):
    """Newton-Raphson solver for T given h_target at constant P."""
    cdef double T = T_guess
    cdef int n_P = P_grid.shape[0]
    cdef int n_T = T_grid.shape[0]
    
    cdef double P_clamped, T_clamped
    cdef int ip, it, idx
    cdef double P0, P1, wp, T0, T1, wt
    cdef double h00, h01, h10, h11, h_current
    cdef double c00, c01, c10, c11, cp_current
    cdef double residual, T_new
    cdef int iter_count
    
    # Clamp pressure to grid bounds
    P_clamped = pressure_pa
    if P_clamped < P_grid[0]: P_clamped = P_grid[0]
    if P_clamped > P_grid[n_P - 1]: P_clamped = P_grid[n_P - 1]
    
    # Find pressure brackets (Linear search, efficient for small grids)
    ip = 0
    for idx in range(1, n_P):
        if P_grid[idx] >= P_clamped:
            ip = idx
            break
    if ip == 0:
        ip = 1
        
    P0 = P_grid[ip - 1]
    P1 = P_grid[ip]
    if P1 != P0:
        wp = (P_clamped - P0) / (P1 - P0)
    else:
        wp = 0.0
        
    for iter_count in range(max_iter):
        # Clamp temperature to grid bounds
        T_clamped = T
        if T_clamped < T_grid[0]: T_clamped = T_grid[0]
        if T_clamped > T_grid[n_T - 1]: T_clamped = T_grid[n_T - 1]
        
        # Find temperature brackets
        it = 0
        for idx in range(1, n_T):
            if T_grid[idx] >= T_clamped:
                it = idx
                break
        if it == 0:
            it = 1
            
        T0 = T_grid[it - 1]
        T1 = T_grid[it]
        if T1 != T0:
            wt = (T_clamped - T0) / (T1 - T0)
        else:
            wt = 0.0
            
        # Bilinear interpolation for H
        h00 = H_lut[ip - 1, it - 1]
        h01 = H_lut[ip - 1, it]
        h10 = H_lut[ip, it - 1]
        h11 = H_lut[ip, it]
        
        h_current = (
            h00 * (1.0 - wp) * (1.0 - wt) +
            h10 * wp * (1.0 - wt) +
            h01 * (1.0 - wp) * wt +
            h11 * wp * wt
        )
        
        # Bilinear interpolation for Cp
        c00 = C_lut[ip - 1, it - 1]
        c01 = C_lut[ip - 1, it]
        c10 = C_lut[ip, it - 1]
        c11 = C_lut[ip, it]
        
        cp_current = (
            c00 * (1.0 - wp) * (1.0 - wt) +
            c10 * wp * (1.0 - wt) +
            c01 * (1.0 - wp) * wt +
            c11 * wp * wt
        )
        
        if cp_current < 100.0:
            cp_current = cp_default
            
        # Newton-Raphson step
        residual = h_target - h_current
        T_new = T + residual / cp_current
        
        # Clamp to LUT temperature bounds
        if T_new < 273.15: T_new = 273.15
        if T_new > 1200.0: T_new = 1200.0
        
        # Check convergence
        if fabs(T_new - T) < tol:
            return T_new
            
        T = T_new
        
    return T


cpdef tuple calc_boiler_flash_jit(
    double h_out,
    double pressure_pa,
    double T_in,
    double[::1] P_sat_grid,
    double[::1] T_sat_grid,
    double[::1] H_liq_sat,
    double[::1] H_vap_sat,
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, ::1] H_lut,
    double[:, ::1] C_lut,
):
    """Flash calculation for water/steam boiler."""
    cdef int n_sat = P_sat_grid.shape[0]
    cdef double P_min = P_sat_grid[0]
    cdef double P_max = P_sat_grid[n_sat - 1]
    
    cdef double t_sat, h_sat_liq, h_sat_vap
    cdef int idx, i
    cdef double P0, P1, w, denom, vapor_frac, T_out
    cdef int phase
    
    # 1. Interpolate saturation properties at current pressure
    if pressure_pa <= P_min:
        t_sat = T_sat_grid[0]
        h_sat_liq = H_liq_sat[0]
        h_sat_vap = H_vap_sat[0]
    elif pressure_pa >= P_max:
        t_sat = T_sat_grid[n_sat - 1]
        h_sat_liq = H_liq_sat[n_sat - 1]
        h_sat_vap = H_vap_sat[n_sat - 1]
    else:
        idx = 0
        for i in range(1, n_sat):
            if P_sat_grid[i] >= pressure_pa:
                idx = i
                break
        
        P0 = P_sat_grid[idx - 1]
        P1 = P_sat_grid[idx]
        if P1 != P0:
            w = (pressure_pa - P0) / (P1 - P0)
        else:
            w = 0.0
            
        t_sat = T_sat_grid[idx - 1] * (1.0 - w) + T_sat_grid[idx] * w
        h_sat_liq = H_liq_sat[idx - 1] * (1.0 - w) + H_liq_sat[idx] * w
        h_sat_vap = H_vap_sat[idx - 1] * (1.0 - w) + H_vap_sat[idx] * w
        
    # 2. Flash calculation
    if h_out < h_sat_liq:
        # Subcooled liquid
        T_out = solve_temperature_from_enthalpy_jit(
            h_out, pressure_pa, t_sat - 10.0,
            P_grid, T_grid, H_lut, C_lut, 4180.0, 0.01, 20
        )
        return T_out, 0.0, 0
        
    elif h_out > h_sat_vap:
        # Superheated vapor
        T_out = solve_temperature_from_enthalpy_jit(
            h_out, pressure_pa, t_sat + 10.0,
            P_grid, T_grid, H_lut, C_lut, 2080.0, 0.01, 20
        )
        return T_out, 1.0, 2
        
    else:
        # Saturated mixture
        denom = h_sat_vap - h_sat_liq
        if denom > 1e-6:
            vapor_frac = (h_out - h_sat_liq) / denom
        else:
            vapor_frac = 0.0
        return t_sat, vapor_frac, 1


cpdef tuple calc_boiler_batch_full(
    double[::1] h_in_array,
    double[::1] flow_array,
    double[::1] power_array,
    double[::1] pressure_array,
    double[::1] T_in_array,
    double efficiency,
    bint is_water,
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, ::1] H_lut,
    double[:, ::1] C_lut,
    double[::1] P_sat_grid,
    double[::1] T_sat_grid,
    double[::1] H_liq_sat,
    double[::1] H_vap_sat,
    double cp_gas=14304.0,
):
    """Full batch electric boiler processing with T(h) solving."""
    cdef int n = h_in_array.shape[0]
    cdef int i
    
    # Initialize output numpy arrays
    cdef cnp.ndarray[double, ndim=1] h_out = np.zeros(n, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] T_out = np.zeros(n, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] vapor_frac = np.zeros(n, dtype=np.float64)
    cdef cnp.ndarray[int, ndim=1] phase = np.zeros(n, dtype=np.int32)
    
    # Memoryviews for fast C-level access inside the loop
    cdef double[::1] h_out_view = h_out
    cdef double[::1] T_out_view = T_out
    cdef double[::1] v_frac_view = vapor_frac
    cdef int[::1] phase_view = phase
    
    cdef double delta_h
    
    for i in range(n):
        # 1. Calculate outlet enthalpy
        h_out_view[i] = calc_boiler_outlet_enthalpy(
            h_in_array[i],
            flow_array[i],
            power_array[i],
            efficiency
        )
        
        # 2. Solve for temperature
        if is_water:
            T_out_view[i], v_frac_view[i], phase_view[i] = calc_boiler_flash_jit(
                h_out_view[i], pressure_array[i], T_in_array[i],
                P_sat_grid, T_sat_grid, H_liq_sat, H_vap_sat,
                P_grid, T_grid, H_lut, C_lut
            )
        else:
            delta_h = h_out_view[i] - h_in_array[i]
            T_out_view[i] = T_in_array[i] + delta_h / cp_gas
            v_frac_view[i] = 0.0
            phase_view[i] = 2  # Always gas
            
    return h_out, T_out, vapor_frac, phase

import numpy as np
cimport numpy as cnp
from libc.math cimport pow, fabs

# =============================================================================
# COMPRESSION JIT KERNELS
# =============================================================================

cpdef double calculate_compression_work(
    double p1,
    double p2,
    double mass,
    double temperature,
    double efficiency=0.75,
    double gamma=1.41,
    double gas_constant=4124.0,
):
    """Computes energy requirement for polytropic compression."""
    if p1 <= 0.0:
        return 0.0
        
    cdef double pressure_ratio = p2 / p1
    cdef double exponent = (gamma - 1.0) / gamma
    cdef double work = (
        (gamma / (gamma - 1.0)) *
        (mass * gas_constant * temperature / efficiency) *
        (pow(pressure_ratio, exponent) - 1.0)
    )

    return work


cpdef tuple calculate_compression_realgas_jit(
    double p_in_pa,
    double p_out_pa,
    double T_in_k,
    double efficiency,
    double[::1] P_grid,
    double[::1] T_grid,
    double[::1] S_grid,
    double[:, ::1] H_lut,
    double[:, ::1] S_lut,
    double[:, ::1] C_lut,
    double[:, ::1] H_from_PS_lut,
):
    """Calculate real-gas polytropic compression using JIT-compiled LUT lookups."""
    cdef double s_in, h_in, h_out_isen, w_isen, w_actual, h_out_actual
    cdef double gamma, exponent, T_guess, T_out_k
    
    # 1. Inlet State
    s_in = bilinear_interp_jit(P_grid, T_grid, S_lut, p_in_pa, T_in_k)
    h_in = bilinear_interp_jit(P_grid, T_grid, H_lut, p_in_pa, T_in_k)    
    
    # 2. Isentropic Outlet State (Constant Entropy)
    h_out_isen = bilinear_interp_jit(P_grid, S_grid, H_from_PS_lut, p_out_pa, s_in)
    
    # 3. Actual Work
    w_isen = h_out_isen - h_in
    w_actual = w_isen / efficiency
    
    # 4. Actual Outlet Enthalpy
    h_out_actual = h_in + w_actual
    
    # 5. Solve for Outlet Temperature
    gamma = 1.41
    exponent = (gamma - 1.0) / gamma
    T_guess = T_in_k * pow((p_out_pa / p_in_pa), exponent)
    
    if T_guess < 273.15: 
        T_guess = 273.15
    if T_guess > 1200.0: 
        T_guess = 1200.0
    
    T_out_k = solve_temperature_from_enthalpy_jit(
        h_out_actual,
        p_out_pa,
        T_guess,
        P_grid,
        T_grid,
        H_lut,
        C_lut,
        4180.0, 
        0.01, 
        20
    )
    
    return w_actual, T_out_k, h_out_actual


cpdef tuple calculate_mixture_compression_jit(
    double p_in_pa,
    double p_out_pa,
    double T_in_k,
    double efficiency,
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, :, ::1] H_luts,
    double[:, :, ::1] S_luts,
    double[:, :, ::1] C_luts,
    double[::1] weights,
    double[::1] mole_fracs,
    double M_mix_kg_mol,
    double sum_ylny,
):
    """Calculate real-gas mixture compression using JIT and Cp-based derivatives."""
    cdef int ix_in, iy_in, ix_out, iy_out, ix_iso, iy_iso, ix_act, iy_act
    cdef double wx_in, wy_in, wx_out, wy_out, wx_iso, wy_iso, wx_act, wy_act
    cdef double s_in, h_in, T_guess, s_guess, diff, cp_mix, ds_dt, delta_T
    cdef double h_out_isen, w_isen, w_actual, h_out_actual, T_act, h_val, cp_val
    cdef int iter_count
    
    # 1. Inlet State
    ix_in, iy_in, wx_in, wy_in = get_interp_weights_jit(P_grid, T_grid, p_in_pa, T_in_k)
    s_in = get_mix_entropy_fast_jit(S_luts, weights, mole_fracs, M_mix_kg_mol, sum_ylny, ix_in, iy_in, wx_in, wy_in)
    h_in = get_mix_enthalpy_fast_jit(H_luts, weights, ix_in, iy_in, wx_in, wy_in)
    
    # 2. Isentropic Step
    T_guess = T_in_k * pow((p_out_pa / p_in_pa), 0.286)
    
    if T_guess < 200.0: T_guess = 200.0
    if T_guess > 1200.0: T_guess = 1200.0
    
    for iter_count in range(8):
        ix_out, iy_out, wx_out, wy_out = get_interp_weights_jit(P_grid, T_grid, p_out_pa, T_guess)
        s_guess = get_mix_entropy_fast_jit(S_luts, weights, mole_fracs, M_mix_kg_mol, sum_ylny, ix_out, iy_out, wx_out, wy_out)
        
        diff = s_guess - s_in
        if fabs(diff) < 1e-4: 
            break
            
        cp_mix = get_mix_cp_jit(P_grid, T_grid, C_luts, weights, ix_out, iy_out, wx_out, wy_out)
        if fabs(cp_mix) < 1e-9: cp_mix = 14000.0 
        
        ds_dt = cp_mix / T_guess
        delta_T = diff / ds_dt
        
        if delta_T > 50.0: delta_T = 50.0
        if delta_T < -50.0: delta_T = -50.0
        
        T_guess = T_guess - delta_T
        if T_guess < 100.0: T_guess = 100.0
        if T_guess > 2000.0: T_guess = 2000.0
        
    ix_iso, iy_iso, wx_iso, wy_iso = get_interp_weights_jit(P_grid, T_grid, p_out_pa, T_guess)
    h_out_isen = get_mix_enthalpy_fast_jit(H_luts, weights, ix_iso, iy_iso, wx_iso, wy_iso)
    
    # 3. Work
    w_isen = h_out_isen - h_in
    w_actual = w_isen / efficiency
    h_out_actual = h_in + w_actual
    
    # 4. Actual Outlet T
    T_act = T_guess 
    
    for iter_count in range(8):
        ix_act, iy_act, wx_act, wy_act = get_interp_weights_jit(P_grid, T_grid, p_out_pa, T_act)
        
        h_val = get_mix_enthalpy_fast_jit(H_luts, weights, ix_act, iy_act, wx_act, wy_act)
        cp_val = get_mix_cp_jit(P_grid, T_grid, C_luts, weights, ix_act, iy_act, wx_act, wy_act)
        
        diff = h_val - h_out_actual
        if fabs(diff) < 1.0:
            break
            
        if fabs(cp_val) < 1e-9: cp_val = 14000.0
        
        delta_T = diff / cp_val
        if delta_T > 50.0: delta_T = 50.0
        if delta_T < -50.0: delta_T = -50.0
        
        T_act = T_act - delta_T
        if T_act < 100.0: T_act = 100.0
        if T_act > 2000.0: T_act = 2000.0
        
    return w_actual, T_act, h_out_actual


cpdef double _compute_T_out_for_P_jit(
    double p_in_pa,
    double p_out_pa,
    double T_in_k,
    double efficiency,
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, :, ::1] H_luts,
    double[:, :, ::1] S_luts,
    double[:, :, ::1] C_luts,
    double[::1] weights,
    double[::1] mole_fracs,
    double M_mix_kg_mol,
    double sum_ylny,
):
    """Compute outlet temperature for given P_out (helper for bisection)."""
    cdef int ix_in, iy_in, ix_out, iy_out, ix_iso, iy_iso, ix_act, iy_act
    cdef double wx_in, wy_in, wx_out, wy_out, wx_iso, wy_iso, wx_act, wy_act
    cdef double s_in, h_in, T_guess, s_guess, diff, cp_mix, ds_dt, delta_T
    cdef double h_out_isen, w_isen, w_actual, h_out_actual, T_act, h_val, cp_val
    cdef int iter_count
    
    # Inlet state
    ix_in, iy_in, wx_in, wy_in = get_interp_weights_jit(P_grid, T_grid, p_in_pa, T_in_k)
    s_in = get_mix_entropy_fast_jit(S_luts, weights, mole_fracs, M_mix_kg_mol, sum_ylny, ix_in, iy_in, wx_in, wy_in)
    h_in = get_mix_enthalpy_fast_jit(H_luts, weights, ix_in, iy_in, wx_in, wy_in)
    
    # Initial guess
    T_guess = T_in_k * pow((p_out_pa / p_in_pa), 0.286)
    if T_guess < 200.0: T_guess = 200.0
    if T_guess > 1200.0: T_guess = 1200.0
    
    # Newton for isentropic T
    for iter_count in range(6):
        ix_out, iy_out, wx_out, wy_out = get_interp_weights_jit(P_grid, T_grid, p_out_pa, T_guess)
        s_guess = get_mix_entropy_fast_jit(S_luts, weights, mole_fracs, M_mix_kg_mol, sum_ylny, ix_out, iy_out, wx_out, wy_out)
        
        diff = s_guess - s_in
        if fabs(diff) < 1e-3:
            break
        
        cp_mix = get_mix_cp_jit(P_grid, T_grid, C_luts, weights, ix_out, iy_out, wx_out, wy_out)
        if fabs(cp_mix) < 1e-9: cp_mix = 14000.0
        
        ds_dt = cp_mix / T_guess
        delta_T = diff / ds_dt
        if delta_T > 30.0: delta_T = 30.0
        if delta_T < -30.0: delta_T = -30.0
        
        T_guess = T_guess - delta_T
        if T_guess < 100.0: T_guess = 100.0
        if T_guess > 1500.0: T_guess = 1500.0
    
    # Get isentropic enthalpy
    ix_iso, iy_iso, wx_iso, wy_iso = get_interp_weights_jit(P_grid, T_grid, p_out_pa, T_guess)
    h_out_isen = get_mix_enthalpy_fast_jit(H_luts, weights, ix_iso, iy_iso, wx_iso, wy_iso)
    
    # Actual work and outlet enthalpy
    w_isen = h_out_isen - h_in
    w_actual = w_isen / efficiency
    h_out_actual = h_in + w_actual
    
    # Newton for actual T
    T_act = T_guess
    for iter_count in range(6):
        ix_act, iy_act, wx_act, wy_act = get_interp_weights_jit(P_grid, T_grid, p_out_pa, T_act)
        h_val = get_mix_enthalpy_fast_jit(H_luts, weights, ix_act, iy_act, wx_act, wy_act)
        
        diff = h_val - h_out_actual
        if fabs(diff) < 10.0:  
            break
        
        cp_val = get_mix_cp_jit(P_grid, T_grid, C_luts, weights, ix_act, iy_act, wx_act, wy_act)
        if fabs(cp_val) < 1e-9: cp_val = 14000.0
        
        delta_T = diff / cp_val
        if delta_T > 30.0: delta_T = 30.0
        if delta_T < -30.0: delta_T = -30.0
        
        T_act = T_act - delta_T
        if T_act < 100.0: T_act = 100.0
        if T_act > 2000.0: T_act = 2000.0
    
    return T_act


cpdef tuple solve_temp_limited_pressure_jit(
    double p_in_pa,
    double p_max_pa,
    double T_in_k,
    double T_max_k,
    double efficiency,
    double[::1] P_grid,
    double[::1] T_grid,
    double[:, :, ::1] H_luts,
    double[:, :, ::1] S_luts,
    double[:, :, ::1] C_luts,
    double[::1] weights,
    double[::1] mole_fracs,
    double M_mix_kg_mol,
    double sum_ylny,
):
    """Solve for maximum outlet pressure that satisfies temperature constraint."""
    cdef double T_at_max, p_low, p_high, p_mid, T_mid
    cdef double w_act, T_out, h_out, p_out_final
    cdef int iter_count
    
    # 1. Check if target pressure is achievable
    T_at_max = _compute_T_out_for_P_jit(
        p_in_pa, p_max_pa, T_in_k, efficiency,
        P_grid, T_grid, H_luts, S_luts, C_luts,
        weights, mole_fracs, M_mix_kg_mol, sum_ylny
    )
    
    if T_at_max <= T_max_k:
        w_act, T_out, h_out = calculate_mixture_compression_jit(
            p_in_pa, p_max_pa, T_in_k, efficiency,
            P_grid, T_grid, H_luts, S_luts, C_luts,
            weights, mole_fracs, M_mix_kg_mol, sum_ylny
        )
        return p_max_pa, T_out, w_act
    
    # 2. Bisection search for P_out such that T_out = T_max
    p_low = p_in_pa
    p_high = p_max_pa
    
    for iter_count in range(25):  
        p_mid = (p_low + p_high) * 0.5
        
        T_mid = _compute_T_out_for_P_jit(
            p_in_pa, p_mid, T_in_k, efficiency,
            P_grid, T_grid, H_luts, S_luts, C_luts,
            weights, mole_fracs, M_mix_kg_mol, sum_ylny
        )
        
        if T_mid <= T_max_k:
            p_low = p_mid
        else:
            p_high = p_mid
        
        # Convergence check
        if fabs(p_high - p_low) / p_low < 0.001:
            break
    
    # 3. Calculate final compression at converged pressure
    p_out_final = p_low
    w_act, T_out, h_out = calculate_mixture_compression_jit(
        p_in_pa, p_out_final, T_in_k, efficiency,
        P_grid, T_grid, H_luts, S_luts, C_luts,
        weights, mole_fracs, M_mix_kg_mol, sum_ylny
    )
    
    return p_out_final, T_out, w_act

import numpy as np
cimport numpy as cnp
from libc.math cimport exp, fabs

# =============================================================================
# REACTOR MODELS (DEOXO PFR)
# =============================================================================

cpdef tuple solve_deoxo_pfr_step(
    double L_total,
    int steps,
    double T_in,
    double P_in_pa,
    double molar_flow_total,
    double y_o2_in,
    double k0,
    double Ea,
    double R,
    double delta_H,
    double U_a,
    double T_jacket,
    double Area,
    double Cp_mix,
    double y_o2_target=0.0,
):
    """Integrates the Plug Flow Reactor (PFR) equations for catalytic deoxygenation."""
    cdef double L_curr = 0.0
    cdef double dL = L_total / 100.0
    cdef double X = 0.0
    cdef double T = T_in
    cdef double T_max = T_in

    cdef double F_o2_in = molar_flow_total * y_o2_in
    cdef int max_iter = 10000
    
    cdef cnp.ndarray[double, ndim=1] L_hist = np.zeros(max_iter + 1, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] T_hist = np.zeros(max_iter + 1, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] X_hist = np.zeros(max_iter + 1, dtype=np.float64)
    
    cdef double[::1] L_view = L_hist
    cdef double[::1] T_view = T_hist
    cdef double[::1] X_view = X_hist
    
    L_view[0] = 0.0
    T_view[0] = T_in
    X_view[0] = 0.0
    cdef int step_count = 1

    if F_o2_in <= 1e-12:
        return 0.0, T_in, T_in, L_hist[:1], T_hist[:1], X_hist[:1]

    cdef double current_y_o2, dx_est, dt_est, dL_target, dL_temp
    cdef double X_next, T_next, k_eff, y_loc, C_o2, r, gen, rem
    cdef double k1_X, k1_T, k2_X, k2_T, k3_X, k3_T, k4_X, k4_T
    cdef double x_k, t_k
    cdef int _iter

    for _iter in range(max_iter):
        if L_curr >= L_total:
            break
            
        current_y_o2 = y_o2_in * (1.0 - X)
        if y_o2_target > 0.0 and current_y_o2 <= y_o2_target:
            dx_est = 0.0
            dt_est = 0.0 
            if U_a > 0.0:
                dt_est = (Area / (molar_flow_total * Cp_mix)) * (-U_a * (T - T_jacket))
            
            dL = L_total - L_curr
            if dL > L_total / 100.0:
                dL = L_total / 100.0
                
            X_next = X
            T_next = T + dt_est * dL
            
            X = X_next
            T = T_next
            L_curr += dL
            if step_count < max_iter:
                L_view[step_count] = L_curr
                T_view[step_count] = T
                X_view[step_count] = X
                step_count += 1
            continue

        # Estimate gradients for adaptive step
        if X >= 1.0:
            dx_est = 0.0
            dt_est = (Area / (molar_flow_total * Cp_mix)) * (-U_a * (T - T_jacket))
        else:
            k_eff = k0 * exp(-Ea / (R * T))
            y_loc = y_o2_in * (1.0 - X)
            if y_loc < 0.0: y_loc = 0.0
            C_o2 = (P_in_pa * y_loc) / (R * T)
            r = k_eff * C_o2
            dx_est = (Area / F_o2_in) * r
            gen = -delta_H * r
            rem = U_a * (T - T_jacket)
            dt_est = (Area / (molar_flow_total * Cp_mix)) * (gen - rem)

        if dx_est > 1e-9:
            dL_target = 0.005 / dx_est
        else:
            dL_target = L_total * 0.1

        if fabs(dt_est) > 1e-9:
            dL_temp = 5.0 / fabs(dt_est)
            if dL_temp < dL_target:
                dL_target = dL_temp

        dL = L_total - L_curr
        if dL_target < dL:
            dL = dL_target
        if dL < 1e-6:
            dL = 1e-6

        # --- Inline RK4 Steps ---
        k1_X = dx_est
        k1_T = dt_est

        # K2
        x_k = X + 0.5 * dL * k1_X
        t_k = T + 0.5 * dL * k1_T
        if x_k >= 1.0:
            k2_X = 0.0
            k2_T = (Area / (molar_flow_total * Cp_mix)) * (-U_a * (t_k - T_jacket))
        else:
            k_eff = k0 * exp(-Ea / (R * t_k))
            y_loc = y_o2_in * (1.0 - x_k)
            if y_loc < 0.0: y_loc = 0.0
            C_o2 = (P_in_pa * y_loc) / (R * t_k)
            r = k_eff * C_o2
            k2_X = (Area / F_o2_in) * r
            k2_T = (Area / (molar_flow_total * Cp_mix)) * (-delta_H * r - U_a * (t_k - T_jacket))

        # K3
        x_k = X + 0.5 * dL * k2_X
        t_k = T + 0.5 * dL * k2_T
        if x_k >= 1.0:
            k3_X = 0.0
            k3_T = (Area / (molar_flow_total * Cp_mix)) * (-U_a * (t_k - T_jacket))
        else:
            k_eff = k0 * exp(-Ea / (R * t_k))
            y_loc = y_o2_in * (1.0 - x_k)
            if y_loc < 0.0: y_loc = 0.0
            C_o2 = (P_in_pa * y_loc) / (R * t_k)
            r = k_eff * C_o2
            k3_X = (Area / F_o2_in) * r
            k3_T = (Area / (molar_flow_total * Cp_mix)) * (-delta_H * r - U_a * (t_k - T_jacket))

        # K4
        x_k = X + dL * k3_X
        t_k = T + dL * k3_T
        if x_k >= 1.0:
            k4_X = 0.0
            k4_T = (Area / (molar_flow_total * Cp_mix)) * (-U_a * (t_k - T_jacket))
        else:
            k_eff = k0 * exp(-Ea / (R * t_k))
            y_loc = y_o2_in * (1.0 - x_k)
            if y_loc < 0.0: y_loc = 0.0
            C_o2 = (P_in_pa * y_loc) / (R * t_k)
            r = k_eff * C_o2
            k4_X = (Area / F_o2_in) * r
            k4_T = (Area / (molar_flow_total * Cp_mix)) * (-delta_H * r - U_a * (t_k - T_jacket))

        X_next = X + (dL / 6.0) * (k1_X + 2.0*k2_X + 2.0*k3_X + k4_X)
        T_next = T + (dL / 6.0) * (k1_T + 2.0*k2_T + 2.0*k3_T + k4_T)

        X = X_next
        if X > 1.0: X = 1.0
        T = T_next
        if T > T_max:
            T_max = T
        L_curr += dL
        
        if step_count < max_iter:
            L_view[step_count] = L_curr
            T_view[step_count] = T
            X_view[step_count] = X
            step_count += 1

    return X, T, T_max, L_hist[:step_count], T_hist[:step_count], X_hist[:step_count]


cpdef tuple solve_deoxo_multizone_jit(
    double[::1] L_zones,
    double[::1] k0_zones,
    double[::1] U_a_zones,
    double T_in,
    double P_in_pa,
    double molar_flow_total,
    double y_o2_in,
    double Ea,
    double R,
    double delta_H,
    double T_jacket,
    double Area,
    double Cp_mix,
    double y_o2_target,
    int max_steps_per_zone=50,
):
    """Simulates a multi-zone PFR in a single JIT-compiled pass."""
    cdef int num_zones = L_zones.shape[0]
    cdef int total_max_points = num_zones * (max_steps_per_zone + 1) + 1
    
    cdef cnp.ndarray[double, ndim=1] L_hist_arr = np.zeros(total_max_points, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] T_hist_arr = np.zeros(total_max_points, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] X_hist_arr = np.zeros(total_max_points, dtype=np.float64)
    cdef double[::1] L_hist = L_hist_arr
    cdef double[::1] T_hist = T_hist_arr
    cdef double[::1] X_hist = X_hist_arr
    
    cdef int current_idx = 0
    cdef double L_cumulative_offset = 0.0
    cdef double T_curr = T_in
    cdef double y_o2_curr = y_o2_in
    cdef double T_max_global = T_in
    cdef double X_global = 0.0
    
    L_hist[0] = 0.0
    T_hist[0] = T_in
    X_hist[0] = 0.0
    current_idx = 1
    
    cdef double flow_Cp = molar_flow_total * Cp_mix
    
    cdef int z, step
    cdef double L_zone, k0, U_a, X_local, T_local, F_o2_in_zone, NTU, dL, L_local
    cdef double x_k, t_k, dx1, dt1, dx2, dt2, dx3, dt3, dx4, dt4, k_eff, y_loc, C_o2, r
    cdef double X_next, T_next, current_global_X
    
    for z in range(num_zones):
        L_zone = L_zones[z]
        if L_zone <= 1e-6:
            continue
            
        k0 = k0_zones[z]
        U_a = U_a_zones[z]
        
        X_local = 0.0
        T_local = T_curr
        F_o2_in_zone = molar_flow_total * y_o2_curr
        
        if F_o2_in_zone <= 1e-12:
            L_cumulative_offset += L_zone
            L_hist[current_idx] = L_cumulative_offset
            if U_a > 0.0 and flow_Cp > 0.0:
                NTU = (U_a * Area * L_zone) / flow_Cp
                T_curr = T_jacket + (T_local - T_jacket) * exp(-NTU)
            T_hist[current_idx] = T_curr
            X_hist[current_idx] = X_global
            current_idx += 1
            continue

        dL = L_zone / max_steps_per_zone
        L_local = 0.0
        
        for step in range(max_steps_per_zone):
            # K1
            x_k = X_local
            t_k = T_local
            if x_k >= 1.0:
                dx1 = 0.0
                dt1 = (Area / flow_Cp) * (-U_a * (t_k - T_jacket))
            else:
                k_eff = k0 * exp(-Ea / (R * t_k))
                y_loc = y_o2_curr * (1.0 - x_k)
                if y_loc < 0.0: y_loc = 0.0
                C_o2 = (P_in_pa * y_loc) / (R * t_k)
                r = k_eff * C_o2
                dx1 = (Area / F_o2_in_zone) * r
                dt1 = (Area / flow_Cp) * (-delta_H * r - U_a * (t_k - T_jacket))

            # K2
            x_k = X_local + 0.5 * dL * dx1
            t_k = T_local + 0.5 * dL * dt1
            if x_k >= 1.0:
                dx2 = 0.0
                dt2 = (Area / flow_Cp) * (-U_a * (t_k - T_jacket))
            else:
                k_eff = k0 * exp(-Ea / (R * t_k))
                y_loc = y_o2_curr * (1.0 - x_k)
                if y_loc < 0.0: y_loc = 0.0
                C_o2 = (P_in_pa * y_loc) / (R * t_k)
                r = k_eff * C_o2
                dx2 = (Area / F_o2_in_zone) * r
                dt2 = (Area / flow_Cp) * (-delta_H * r - U_a * (t_k - T_jacket))

            # K3
            x_k = X_local + 0.5 * dL * dx2
            t_k = T_local + 0.5 * dL * dt2
            if x_k >= 1.0:
                dx3 = 0.0
                dt3 = (Area / flow_Cp) * (-U_a * (t_k - T_jacket))
            else:
                k_eff = k0 * exp(-Ea / (R * t_k))
                y_loc = y_o2_curr * (1.0 - x_k)
                if y_loc < 0.0: y_loc = 0.0
                C_o2 = (P_in_pa * y_loc) / (R * t_k)
                r = k_eff * C_o2
                dx3 = (Area / F_o2_in_zone) * r
                dt3 = (Area / flow_Cp) * (-delta_H * r - U_a * (t_k - T_jacket))

            # K4
            x_k = X_local + dL * dx3
            t_k = T_local + dL * dt3
            if x_k >= 1.0:
                dx4 = 0.0
                dt4 = (Area / flow_Cp) * (-U_a * (t_k - T_jacket))
            else:
                k_eff = k0 * exp(-Ea / (R * t_k))
                y_loc = y_o2_curr * (1.0 - x_k)
                if y_loc < 0.0: y_loc = 0.0
                C_o2 = (P_in_pa * y_loc) / (R * t_k)
                r = k_eff * C_o2
                dx4 = (Area / F_o2_in_zone) * r
                dt4 = (Area / flow_Cp) * (-delta_H * r - U_a * (t_k - T_jacket))

            X_next = X_local + (dL / 6.0) * (dx1 + 2.0*dx2 + 2.0*dx3 + dx4)
            T_next = T_local + (dL / 6.0) * (dt1 + 2.0*dt2 + 2.0*dt3 + dt4)
            
            X_local = X_next
            if X_local > 1.0: X_local = 1.0
            if X_local < 0.0: X_local = 0.0
            T_local = T_next
            L_local += dL
            
            if T_local > T_max_global:
                T_max_global = T_local
                
            L_hist[current_idx] = L_cumulative_offset + L_local
            T_hist[current_idx] = T_local
            
            current_global_X = 1.0 - (1.0 - X_global) * (1.0 - X_local)
            X_hist[current_idx] = current_global_X
            
            current_idx += 1
            
        L_cumulative_offset += L_zone
        T_curr = T_local
        X_global = 1.0 - (1.0 - X_global) * (1.0 - X_local)
        y_o2_curr = y_o2_curr * (1.0 - X_local)
        
    return X_global, T_curr, T_max_global, L_hist_arr[:current_idx], T_hist_arr[:current_idx], X_hist_arr[:current_idx]


# =============================================================================
# SOEC MODELS
# =============================================================================

cpdef tuple simulate_soec_step_jit(
    double reference_power,
    double[::1] real_powers,
    int[::1] real_states,
    double[::1] real_limits,
    int[::1] virtual_map,
    double uniform_module_max_limit,
    double power_standby_mw,
    double power_first_step_mw,
    double ramp_step_mw,
    double minimum_total_power=0.0,
):
    """Executes the dispatch control logic for a multi-module SOEC plant."""
    cdef int n = virtual_map.shape[0]
    cdef int i, idx, target_module_id, target_index, N_ceil, N_floor
    cdef double requested_power = 0.0
    cdef double difference, broken_number, numerator, base_limit_term, standby_term, new_limit_calc
    cdef double tolerance = 0.005
    cdef double inactive_limit_const, abs_diff, sign_diff
    
    # Internal state tracking mapped to virtual topology
    cdef cnp.ndarray[double, ndim=1] powers_v_arr = np.empty(n, dtype=np.float64)
    cdef cnp.ndarray[int, ndim=1] states_v_arr = np.empty(n, dtype=np.int32)
    cdef cnp.ndarray[double, ndim=1] active_limit_arr = np.empty(n, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] difference_to_limit_arr = np.empty(n, dtype=np.float64)
    cdef cnp.ndarray[double, ndim=1] movement_arr = np.empty(n, dtype=np.float64)
    
    cdef double[::1] powers_v = powers_v_arr
    cdef int[::1] states_v = states_v_arr
    cdef double[::1] active_limit = active_limit_arr
    cdef double[::1] difference_to_limit = difference_to_limit_arr
    cdef double[::1] movement = movement_arr
    
    for i in range(n):
        idx = virtual_map[i]
        powers_v[i] = real_powers[idx]
        states_v[i] = real_states[idx]
        active_limit[i] = real_limits[idx]
        requested_power += powers_v[i]
        
    difference = reference_power - requested_power
    
    for i in range(n):
        if states_v[i] == 3 and fabs(powers_v[i] - uniform_module_max_limit) < tolerance:
            states_v[i] = 4
            
    if fabs(difference) < 0.01:
        for i in range(n):
            if states_v[i] == 2 or states_v[i] == 5:
                states_v[i] = 3
                
        for i in range(n):
            idx = virtual_map[i]
            real_powers[idx] = powers_v[i]
            real_states[idx] = states_v[i]
            real_limits[idx] = active_limit[i]
            
        return np.asarray(real_powers), np.asarray(real_states), np.asarray(real_limits)
        
    numerator = reference_power - minimum_total_power
    if numerator < 0.0: numerator = 0.0
    
    broken_number = numerator / uniform_module_max_limit
    
    if broken_number == <double>(<int>broken_number):
        N_ceil = <int>broken_number
    else:
        N_ceil = <int>broken_number + 1
        
    if broken_number > 0.01 and fabs(broken_number - N_ceil) < 0.001:
        target_module_id = <int>N_ceil + 1
    else:
        target_module_id = <int>N_ceil
        
    if target_module_id < 1: target_module_id = 1
    if target_module_id > n + 1: target_module_id = n + 1
    target_index = target_module_id - 1
    
    N_floor = <int>broken_number
    base_limit_term = uniform_module_max_limit * N_floor
    standby_term = 0.0
    new_limit_calc = reference_power - base_limit_term - standby_term
    
    if new_limit_calc > power_standby_mw + tolerance and new_limit_calc < power_first_step_mw - tolerance:
        new_limit_calc = power_standby_mw
        
    if difference > 0.0:
        inactive_limit_const = power_standby_mw
        if target_module_id > n:
            for i in range(n):
                active_limit[i] = uniform_module_max_limit
        else:
            active_limit[target_index] = new_limit_calc if new_limit_calc > inactive_limit_const else inactive_limit_const
            for i in range(target_index):
                active_limit[i] = uniform_module_max_limit
            for i in range(target_index + 1, n):
                active_limit[i] = inactive_limit_const
    else:
        if fabs(reference_power - minimum_total_power) < 0.01:
            for i in range(n):
                active_limit[i] = power_standby_mw
        else:
            active_limit[target_index] = new_limit_calc if new_limit_calc > power_standby_mw else power_standby_mw
            for i in range(target_index):
                active_limit[i] = uniform_module_max_limit
            for i in range(target_index + 1, n):
                active_limit[i] = power_standby_mw
                
    for i in range(n):
        difference_to_limit[i] = active_limit[i] - powers_v[i]
        abs_diff = fabs(difference_to_limit[i])
        sign_diff = 1.0 if difference_to_limit[i] >= 0.0 else -1.0
        movement[i] = (abs_diff if abs_diff < ramp_step_mw else ramp_step_mw) * sign_diff
        
    for i in range(n):
        if fabs(powers_v[i] - power_standby_mw) < tolerance and difference_to_limit[i] > tolerance:
            powers_v[i] = power_first_step_mw
            movement[i] = 0.0
            
    for i in range(n):
        powers_v[i] += movement[i]
        
    for i in range(n):
        if (powers_v[i] > power_standby_mw + tolerance) and (powers_v[i] < power_first_step_mw - tolerance):
            powers_v[i] = power_standby_mw
            
    for i in range(n):
        if powers_v[i] <= power_standby_mw + tolerance:
            powers_v[i] = power_standby_mw
            
    for i in range(n):
        if fabs(powers_v[i] - power_standby_mw) < tolerance:
            states_v[i] = 1 
        elif fabs(powers_v[i] - uniform_module_max_limit) < tolerance:
            states_v[i] = 4 
        elif fabs(powers_v[i] - active_limit[i]) < tolerance:
            states_v[i] = 3 
        elif difference_to_limit[i] > 0:
            states_v[i] = 2 
        else:
            states_v[i] = 5 
            
    for i in range(n):
        idx = virtual_map[i]
        real_powers[idx] = powers_v[i]
        real_states[idx] = states_v[i]
        real_limits[idx] = active_limit[i]
        
    return np.asarray(real_powers), np.asarray(real_states), np.asarray(real_limits)


cpdef double calculate_h2_production_dynamic(
    double[::1] powers_mw,
    double nominal_mw,
    double[::1] breaks,
    double[:, ::1] coeffs,
    double[::1] deg_factors,
    double dt,
):
    """Calculate total H₂ production using load-dependent efficiency (vectorized)."""
    cdef double total_h2 = 0.0
    cdef double energy_factor = dt * 1000.0
    cdef int i
    cdef int n = powers_mw.shape[0]
    cdef double p_mw, load_pct, base_sec, actual_sec, h2_kg
    
    for i in range(n):
        p_mw = powers_mw[i]
        
        if p_mw < 0.01:
            continue
            
        load_pct = (p_mw / nominal_mw) * 100.0
        
        # `eval_cubic_spline` uses standard Python scoping in Cython, 
        # so it must be available/imported in the final `.pyx` block.
        base_sec = eval_cubic_spline(load_pct, breaks, coeffs)
        
        actual_sec = base_sec * deg_factors[i]
        
        if actual_sec < 1.0:
            actual_sec = 1.0
            
        h2_kg = (p_mw * energy_factor) / actual_sec
        total_h2 += h2_kg
        
    return total_h2

import numpy as np
cimport numpy as cnp
from libc.math cimport exp, log, pow, fabs

# =============================================================================
# FLASH SOLVERS & THERMAL EXCHANGERS
# =============================================================================

cpdef double solve_uv_flash(
    double target_u_molar,
    double volume_m3,
    double total_moles,
    double[::1] mole_fractions,
    double[::1] h_formations,
    double[:, ::1] cp_coeffs_matrix,
    double T_guess,
    double R_gas=8.314,
    double tol=1e-4,
    int max_iter=50,
):
    """Solve for temperature given internal energy and volume (UV flash)."""
    cdef double T = T_guess
    cdef int i
    cdef double h_mix, u_calc, f, cp_mix, df, T_new

    if total_moles <= 0.0 or volume_m3 <= 0.0:
        return T_guess

    for i in range(max_iter):
        h_mix = calculate_mixture_enthalpy(T, mole_fractions, h_formations, cp_coeffs_matrix, 298.15)
        u_calc = h_mix - R_gas * T
        f = u_calc - target_u_molar

        if fabs(f) < tol:
            return T

        cp_mix = calculate_mixture_cp(T, mole_fractions, cp_coeffs_matrix, 298.15)
        df = cp_mix - R_gas

        if df == 0.0:
            break

        T_new = T - f / df

        if T_new < 10.0:
            T_new = 10.0
        if T_new > 5000.0:
            T_new = 5000.0

        if fabs(T_new - T) < tol:
            return T_new

        T = T_new

    return T


cpdef tuple solve_interchanger_flash_jit(
    double z_h2o_mole,
    double M_mix_feed,
    double P_system,
    double h_target,
    double T_h_in,
    double[::1] lut_mass_fracs,
    double[:, :, ::1] stacked_H,
    double[::1] P_grid,
    double[::1] T_grid,
    int max_iter=40,
    double tol=100.0,
):
    """JIT-compiled interchanger outlet flash solver."""
    cdef int n_fluids = stacked_H.shape[0]
    cdef int n_p = P_grid.shape[0]
    cdef int n_t = T_grid.shape[0]
    cdef bint was_clamped = False
    cdef double P_lookup = P_system
    
    if P_lookup < P_grid[0]:
        P_lookup = P_grid[0]
        was_clamped = True
    elif P_lookup > P_grid[n_p - 1]:
        P_lookup = P_grid[n_p - 1]
        was_clamped = True

    cdef int ix_p, iy_t, ix_pw
    cdef double p0, p1, wp
    
    if P_lookup <= P_grid[0]:
        ix_p = 0
        wp = 0.0
    elif P_lookup >= P_grid[n_p - 1]:
        ix_p = n_p - 2
        wp = 1.0
    else:
        # Assumes `_bisect_left` is defined in the same `.pyx` file 
        ix_p = _bisect_left(P_grid, P_lookup, n_p) - 1
        p0 = P_grid[ix_p]
        p1 = P_grid[ix_p + 1]
        wp = (P_lookup - p0) / (p1 - p0)

    cdef double MW_H2O = 0.018015
    cdef double mw_inerts_avg = 0.028
    
    if (1.0 - z_h2o_mole) > 1e-9:
        mw_inerts_avg = (M_mix_feed - z_h2o_mole * MW_H2O) / (1.0 - z_h2o_mole)

    cdef double T_lo = 273.16
    cdef double T_hi = T_h_in if T_h_in > 500.0 else 500.0
    cdef double T_sol = T_h_in
    cdef double beta_sol = 1.0

    cdef int iteration, i
    cdef double T_mid, P_sat, K_w, beta, n_gas, n_liq, y_w
    cdef double mw_gas, mw_liq, mass_gas, mass_liq, total_mass_calc
    cdef double psi_gas, psi_liq, w_w_gas, T_lookup, wt, t0, t1
    cdef double h_inert_spec, total_w_inert, w_i, f00, f10, f01, f11, h_i
    cdef double p_h2o, pw0, pw1, wpw, h_vap_w, h_gas_spec, h_liq_w, h_calc
    
    for iteration in range(max_iter):
        T_mid = 0.5 * (T_lo + T_hi)

        # Assumes `_antoine_psat_water` is available in this `.pyx` scope
        P_sat = _antoine_psat_water(T_mid)
        K_w = P_sat / P_system
        
        if K_w >= 1.0 or z_h2o_mole < 1e-12 or z_h2o_mole <= K_w:
            beta = 1.0
        else:
            beta = (1.0 - z_h2o_mole) / (1.0 - K_w)
            if beta < 0.0:
                beta = 0.0
            elif beta > 1.0:
                beta = 1.0

        n_gas = beta
        n_liq = 1.0 - beta

        if beta < 0.9999 and K_w < 1.0:
            y_w = K_w
        else:
            y_w = z_h2o_mole

        mw_gas = y_w * MW_H2O + (1.0 - y_w) * mw_inerts_avg
        mw_liq = MW_H2O

        mass_gas = n_gas * mw_gas
        mass_liq = n_liq * mw_liq
        total_mass_calc = mass_gas + mass_liq

        psi_gas = 1.0
        if total_mass_calc > 0.0:
            psi_gas = mass_gas / total_mass_calc
        psi_liq = 1.0 - psi_gas

        w_w_gas = 0.0
        if mw_gas > 0.0:
            w_w_gas = (y_w * MW_H2O) / mw_gas

        T_lookup = T_mid
        if T_lookup < T_grid[0]:
            T_lookup = T_grid[0]
            was_clamped = True
        elif T_lookup > T_grid[n_t - 1]:
            T_lookup = T_grid[n_t - 1]
            was_clamped = True

        if T_lookup <= T_grid[0]:
            iy_t = 0
            wt = 0.0
        elif T_lookup >= T_grid[n_t - 1]:
            iy_t = n_t - 2
            wt = 1.0
        else:
            iy_t = _bisect_left(T_grid, T_lookup, n_t) - 1
            t0 = T_grid[iy_t]
            t1 = T_grid[iy_t + 1]
            wt = (T_lookup - t0) / (t1 - t0)

        h_inert_spec = 0.0
        total_w_inert = 0.0
        
        for i in range(n_fluids):
            w_i = lut_mass_fracs[i]
            if w_i < 1e-12:
                continue
            if i == 5:
                continue
                
            f00 = stacked_H[i, ix_p, iy_t]
            f10 = stacked_H[i, ix_p + 1, iy_t]
            f01 = stacked_H[i, ix_p, iy_t + 1]
            f11 = stacked_H[i, ix_p + 1, iy_t + 1]
            h_i = (1.0 - wp) * (1.0 - wt) * f00 + wp * (1.0 - wt) * f10 + (1.0 - wp) * wt * f01 + wp * wt * f11
            
            h_inert_spec += w_i * h_i
            total_w_inert += w_i

        if total_w_inert > 0.0:
            h_inert_spec /= total_w_inert

        p_h2o = P_grid[0] if P_grid[0] > (P_system * (y_w if y_w > 1e-6 else 1e-6)) else (P_system * (y_w if y_w > 1e-6 else 1e-6))
        if p_h2o > P_grid[n_p - 1]:
            p_h2o = P_grid[n_p - 1]
            
        if p_h2o <= P_grid[0]:
            ix_pw = 0
            wpw = 0.0
        elif p_h2o >= P_grid[n_p - 1]:
            ix_pw = n_p - 2
            wpw = 1.0
        else:
            ix_pw = _bisect_left(P_grid, p_h2o, n_p) - 1
            pw0 = P_grid[ix_pw]
            pw1 = P_grid[ix_pw + 1]
            wpw = (p_h2o - pw0) / (pw1 - pw0)

        h_vap_w = ((1.0 - wpw) * (1.0 - wt) * stacked_H[5, ix_pw, iy_t] +
                   wpw * (1.0 - wt) * stacked_H[5, ix_pw + 1, iy_t] +
                   (1.0 - wpw) * wt * stacked_H[5, ix_pw, iy_t + 1] +
                   wpw * wt * stacked_H[5, ix_pw + 1, iy_t + 1])

        h_gas_spec = w_w_gas * h_vap_w + (1.0 - w_w_gas) * h_inert_spec

        h_liq_w = ((1.0 - wp) * (1.0 - wt) * stacked_H[5, ix_p, iy_t] +
                   wp * (1.0 - wt) * stacked_H[5, ix_p + 1, iy_t] +
                   (1.0 - wp) * wt * stacked_H[5, ix_p, iy_t + 1] +
                   wp * wt * stacked_H[5, ix_p + 1, iy_t + 1])

        h_calc = psi_gas * h_gas_spec + psi_liq * h_liq_w

        if fabs(h_calc - h_target) < tol:
            T_sol = T_mid
            beta_sol = beta
            break

        if h_calc > h_target:
            T_hi = T_mid
        else:
            T_lo = T_mid

        T_sol = T_mid
        beta_sol = beta

    return T_sol, beta_sol, was_clamped


cpdef tuple solve_dry_cooler_thermal_jit(
    double m_dot_gas,
    double cp_gas,
    double T_gas_in_k,
    double glycol_flow_kg_s,
    double glycol_cp,
    double T_glycol_in_k,
    double tqc_u,
    double tqc_area,
    double T_air_in_k,
    double dc_u,
    double dc_area,
    double dc_air_flow_kg_s,
    double cp_air,
    bint use_dc,
    double flow_area_gas,
    double flow_area_glycol,
    double d_tube_in,
    double d_tube_out,
    double mu_gas,
    double k_gas,
    double pr_gas,
    double mu_glycol,
    double k_glycol,
    double pr_glycol,
    double k_tube_wall,
    double r_foul_glycol,
    bint use_dynamic_u,
):
    """Fused JIT kernel for dry cooler TQC + DC thermal solution (P5)."""
    cdef double u_tqc = tqc_u
    cdef double G_gas, Re_gas, Nu_gas, h_gas, G_gly, Re_gly, Nu_gly, h_gly
    cdef double r_in, r_out, R_total
    
    if use_dynamic_u and flow_area_gas > 0.0 and flow_area_glycol > 0.0:
        G_gas = m_dot_gas / flow_area_gas
        Re_gas = (G_gas * d_tube_in / mu_gas) if mu_gas > 0.0 else 0.0
        
        if Re_gas > 0.0 and pr_gas > 0.0:
            Nu_gas = 0.023 * pow(Re_gas, 0.8) * pow(pr_gas, 0.3)
        else:
            Nu_gas = 3.66
        h_gas = (Nu_gas * k_gas / d_tube_in) if d_tube_in > 0.0 else 500.0

        G_gly = glycol_flow_kg_s / flow_area_glycol
        Re_gly = (G_gly * d_tube_out / mu_glycol) if mu_glycol > 0.0 else 0.0
        
        if Re_gly > 0.0 and pr_glycol > 0.0:
            Nu_gly = 0.023 * pow(Re_gly, 0.8) * pow(pr_glycol, 0.4)
        else:
            Nu_gly = 3.66
        h_gly = (Nu_gly * k_glycol / d_tube_out) if d_tube_out > 0.0 else 200.0

        r_in = d_tube_in / 2.0
        r_out = d_tube_out / 2.0
        if h_gas > 0.0 and h_gly > 0.0 and k_tube_wall > 0.0:
            R_total = (1.0 / h_gas +
                       r_in * log(r_out / r_in) / k_tube_wall +
                       (r_in / r_out) / h_gly +
                       r_foul_glycol)
            if R_total > 0.0:
                u_tqc = 1.0 / R_total

    # --- TQC (Counter-Flow) ---
    cdef double C_hot = m_dot_gas * cp_gas
    cdef double C_cold = glycol_flow_kg_s * glycol_cp
    cdef double C_min_tqc = C_hot if C_hot < C_cold else C_cold
    cdef double C_max_tqc = C_hot if C_hot > C_cold else C_cold
    
    cdef double eff_tqc = 0.0
    cdef double Q_tqc = 0.0
    cdef double R_tqc, NTU_tqc, exp_val, denom, Q_max_tqc
    
    if C_min_tqc > 1e-9:
        R_tqc = (C_min_tqc / C_max_tqc) if C_max_tqc > 1e-9 else 0.0
        NTU_tqc = (u_tqc * tqc_area) / C_min_tqc
        
        if fabs(R_tqc - 1.0) < 1e-9:
            eff_tqc = NTU_tqc / (1.0 + NTU_tqc)
        else:
            exp_val = exp(-NTU_tqc * (1.0 - R_tqc))
            denom = 1.0 - R_tqc * exp_val
            if fabs(denom) > 1e-12:
                eff_tqc = (1.0 - exp_val) / denom
            else:
                eff_tqc = 1.0
                
        Q_max_tqc = C_min_tqc * (T_gas_in_k - T_glycol_in_k)
        Q_tqc = eff_tqc * Q_max_tqc

    cdef double T_gas_out_k = (T_gas_in_k - Q_tqc / C_hot) if C_hot > 1e-9 else T_gas_in_k
    cdef double T_glycol_hot_k = (T_glycol_in_k + Q_tqc / C_cold) if C_cold > 1e-9 else T_glycol_in_k

    # --- DC (Cross-Flow) ---
    cdef double eff_dc = 0.0
    cdef double Q_dc = 0.0
    cdef double T_glycol_cold_k = T_glycol_hot_k
    cdef double C_air, C_min_dc, C_max_dc, R_dc, NTU_dc, Q_max_dc
    
    if use_dc:
        C_air = dc_air_flow_kg_s * cp_air
        C_min_dc = C_cold if C_cold < C_air else C_air
        C_max_dc = C_cold if C_cold > C_air else C_air

        if C_min_dc > 1e-9:
            R_dc = (C_min_dc / C_max_dc) if C_max_dc > 1e-9 else 0.0
            NTU_dc = (dc_u * dc_area) / C_min_dc
            
            if NTU_dc > 0.0 and R_dc > 0.0:
                eff_dc = 1.0 - exp((pow(NTU_dc, 0.22) / R_dc) * (exp(-R_dc * pow(NTU_dc, 0.78)) - 1.0))
            elif NTU_dc > 0.0:
                eff_dc = 1.0 - exp(-NTU_dc)
                
            Q_max_dc = C_min_dc * (T_glycol_hot_k - T_air_in_k)
            Q_dc = eff_dc * Q_max_dc

        T_glycol_cold_k = (T_glycol_hot_k - Q_dc / C_cold) if C_cold > 1e-9 else T_glycol_hot_k

    return T_gas_out_k, T_glycol_hot_k, T_glycol_cold_k, Q_tqc, Q_dc, eff_tqc, eff_dc


cpdef double calculate_dynamic_u_fouled(
    double h_in,
    double h_out,
    double d_in,
    double d_out,
    double k_wall,
    double r_foul_in,
    double r_foul_out,
):
    """Calculate overall heat transfer coefficient U with fouling."""
    if h_in <= 1e-6 or h_out <= 1e-6:
        return 0.0
    
    if d_in <= 0.0 or d_out < d_in:
        return 0.0
        
    cdef double area_ratio, t_wall, r_wall, r_conv_in, r_conv_out, r_total
    
    if fabs(d_out - d_in) < 1e-9:
        area_ratio = 1.0
        t_wall = 0.002
        r_wall = t_wall / k_wall
    else:
        area_ratio = d_out / d_in
        r_wall = (d_out * log(d_out / d_in)) / (2.0 * k_wall)
        
    r_conv_in = area_ratio / h_in
    r_conv_out = 1.0 / h_out
    
    r_total = r_conv_in + (r_foul_in * area_ratio) + r_wall + r_foul_out + r_conv_out
    
    if r_total > 0.0:
        return 1.0 / r_total
    return 0.0

import numpy as np
cimport numpy as cnp
from libc.math cimport log, exp

# =============================================================================
# CONSTANTS & MODULE GLOBALS
# =============================================================================
# Python-visible module globals — exported from the compiled extension so
# the shim (numba_ops.py) can re-export them without the Python fallback.
# Matches CANONICAL_FLUID_ORDER: H2, O2, N2, CO2, CH4, H2O, CO.

GAS_CP_COEFFS = np.array([
    [29.11, -0.1916e-2, 0.4003e-5, -0.8704e-9, 0.0],  # H2
    [29.96, 4.18e-3, -1.67e-6, 0.0, 0.0],             # O2
    [28.98, -0.1571e-2, 0.8081e-5, -2.873e-9, 0.0],   # N2
    [22.26, 5.98e-2, -3.50e-5, 7.47e-9, 0.0],         # CO2
    [19.89, 5.02e-2, 1.27e-5, -1.10e-8, 0.0],         # CH4
    [32.24, 1.92e-3, 1.06e-5, -3.60e-9, 0.0],         # H2O (vap)
    [29.14, -0.1571e-2, 0.8081e-5, -2.873e-9, 0.0]    # CO
], dtype=np.float64)

GAS_MW = np.array(
    [2.016, 32.0, 28.014, 44.01, 16.04, 18.015, 28.01],
    dtype=np.float64
)
GAS_MW_KG_MOL = GAS_MW * 1e-3

LIQ_CP_COEFFS = np.array([75.3, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
LIQ_MW = 18.015

# Henry's Law constants (van't Hoff form)
HENRY_H2_H298 = 1300.0   # L·atm/mol at 298.15 K
HENRY_H2_C    = 500.0    # K  (temperature coefficient = -ΔH_sol/R)
HENRY_H2_MW   = 0.002016 # kg/mol
HENRY_O2_H298 = 770.0    # L·atm/mol at 298.15 K
HENRY_O2_C    = 1700.0   # K
HENRY_O2_MW   = 0.031998 # kg/mol

# C-typed aliases for use by internal kernels (avoid Python overhead).
cdef double[:, ::1] _GAS_CP_COEFFS  = GAS_CP_COEFFS
cdef double[::1]    _GAS_MW         = GAS_MW
cdef double[::1]    _LIQ_CP_COEFFS  = LIQ_CP_COEFFS
cdef double         _LIQ_MW         = LIQ_MW

# =============================================================================
# STREAM COMPOSITION & ENTHALPY
# =============================================================================

cpdef tuple fast_composition_properties(double[::1] mass_fracs):
    """Compute mole fractions, molar mass, and entropy mixing term in one pass."""
    cdef int n = mass_fracs.shape[0]
    
    # Matches CANONICAL_FLUID_ORDER
    cdef double[7] mw_arr = [0.002016, 0.032, 0.028014, 0.04401, 0.01604, 0.018015, 0.02801]
    
    cdef double total_moles = 0.0
    cdef cnp.ndarray[double, ndim=1] moles_arr = np.empty(n, dtype=np.float64)
    cdef double[::1] moles = moles_arr
    cdef int i
    cdef double m

    for i in range(n):
        if mass_fracs[i] > 0.0:
            m = mass_fracs[i] / mw_arr[i]
            moles[i] = m
            total_moles += m
        else:
            moles[i] = 0.0

    cdef double M_mix = 0.0
    cdef double sum_ylny = 0.0
    cdef cnp.ndarray[double, ndim=1] mole_fracs_arr = np.zeros(n, dtype=np.float64)
    cdef double[::1] mole_fracs = mole_fracs_arr
    cdef double inv_total, y

    if total_moles > 1e-15:
        inv_total = 1.0 / total_moles
        for i in range(n):
            if moles[i] > 0.0:
                y = moles[i] * inv_total
                mole_fracs[i] = y
                M_mix += y * mw_arr[i]
                sum_ylny += y * log(y)
    else:
        M_mix = 0.028

    return mole_fracs_arr, M_mix, sum_ylny


cpdef double _integral_cp(double t, double[:] coeffs):
    """Integral of Cp(T) from 0 to T.

    Promoted from cdef to cpdef so it is callable from Python (required
    for API compatibility — _integral_cp is listed in __all__).
    Accepts non-contiguous slices (e.g. rows of _GAS_CP_COEFFS).
    """
    cdef double A = coeffs[0]
    cdef double B = coeffs[1]
    cdef double C = coeffs[2]
    cdef double D = coeffs[3]
    cdef double E = coeffs[4]
    return (A * t +
            B * t*t / 2.0 +
            C * t*t*t / 3.0 +
            D * t*t*t*t / 4.0 -
            E / t)



cpdef double calculate_stream_enthalpy_jit(
    double T_k,
    double[::1] mass_fracs,
    double h2o_liq_frac,
):
    """Calculate specific enthalpy (J/kg) using C-level integration arrays."""
    cdef double t_ref = 298.15
    cdef double h_total = 0.0
    cdef int n = mass_fracs.shape[0]
    cdef int i
    cdef double w_i, dh_mol, h_spec, dh_mol_liq, h_liq
    
    # 1. Gas Species
    for i in range(n):
        w_i = mass_fracs[i]
        if w_i > 1e-12:
            dh_mol = _integral_cp(T_k, _GAS_CP_COEFFS[i]) - _integral_cp(t_ref, _GAS_CP_COEFFS[i])
            h_spec = dh_mol * 1000.0 / _GAS_MW[i] 
            h_total += w_i * h_spec
            
    # 2. Liquid Water
    if h2o_liq_frac > 1e-12:
        dh_mol_liq = _integral_cp(T_k, _LIQ_CP_COEFFS) - _integral_cp(t_ref, _LIQ_CP_COEFFS)
        h_liq = dh_mol_liq * 1000.0 / _LIQ_MW
        h_total += h2o_liq_frac * h_liq
        
    return h_total


cpdef double calculate_dissolved_gas_mg_kg_jit(
    double temperature_k,
    double gas_partial_pressure_pa,
    double species_H298,
    double species_C,
    double species_MW_kg_mol,
):
    """JIT-compiled Henry's Law calculation for dissolved gas concentration."""
    if temperature_k <= 0.0 or gas_partial_pressure_pa <= 0.0:
        return 0.0
    
    cdef double T0 = 298.15
    cdef double H_T = species_H298 * exp(species_C * (1.0 / temperature_k - 1.0 / T0))
    cdef double p_atm = gas_partial_pressure_pa / 101325.0
    cdef double c_mol_L = p_atm / H_T
    cdef double mw_g_mol = species_MW_kg_mol * 1000.0
    cdef double c_mg_kg = c_mol_L * mw_g_mol * 1000.0
    
    return c_mg_kg


cpdef double get_mixture_enthalpy_fast(
    double[:, :, ::1] stacked_H,
    double[::1] P_grid,
    double[::1] T_grid,
    double[::1] mass_fracs,
    double P_sys,
    double T_k,
):
    """Calculate mixture specific enthalpy in a single JIT call."""
    cdef double h_mix = 0.0
    cdef int n_fluids = mass_fracs.shape[0]
    cdef int n_p = P_grid.shape[0]
    cdef int n_t = T_grid.shape[0]

    cdef double p_min = P_grid[0]
    cdef double p_max = P_grid[n_p - 1]
    cdef double t_min = T_grid[0]
    cdef double t_max = T_grid[n_t - 1]

    cdef double P_lookup = P_sys
    if P_lookup < p_min: P_lookup = p_min
    elif P_lookup > p_max: P_lookup = p_max

    cdef double T_lookup = T_k
    if T_lookup < t_min: T_lookup = t_min
    elif T_lookup > t_max: T_lookup = t_max

    cdef int ix, iy
    ix = _bisect_left(P_grid, P_lookup, n_p)
    if ix == 0: ix = 1
    elif ix >= n_p: ix = n_p - 1

    iy = _bisect_left(T_grid, T_lookup, n_t)
    if iy == 0: iy = 1
    elif iy >= n_t: iy = n_t - 1

    cdef double p0 = P_grid[ix - 1]
    cdef double p1 = P_grid[ix]
    cdef double t0 = T_grid[iy - 1]
    cdef double t1 = T_grid[iy]

    cdef double wp = (P_lookup - p0) / (p1 - p0) if p1 != p0 else 0.0
    cdef double wt = (T_lookup - t0) / (t1 - t0) if t1 != t0 else 0.0

    cdef int i
    cdef double w_i, q00, q01, q10, q11, h_i

    for i in range(n_fluids):
        w_i = mass_fracs[i]
        if w_i < 1e-12:
            continue

        q00 = stacked_H[i, ix - 1, iy - 1]
        q01 = stacked_H[i, ix - 1, iy]
        q10 = stacked_H[i, ix, iy - 1]
        q11 = stacked_H[i, ix, iy]

        h_i = (
            q00 * (1.0 - wp) * (1.0 - wt) +
            q10 * wp * (1.0 - wt) +
            q01 * (1.0 - wp) * wt +
            q11 * wp * wt
        )
        h_mix += w_i * h_i

    return h_mix


cpdef cnp.ndarray remap_canonical_to_lut(
    double[::1] canonical_fracs,
    double h2o_liq_frac,
    int[::1] species_map,
):
    """Remap a canonical mass fraction array to a LUT-ordered array."""
    cdef int n_lut = species_map.shape[0]
    cdef cnp.ndarray[double, ndim=1] lut_fracs_arr = np.zeros(n_lut, dtype=np.float64)
    cdef double[::1] lut_fracs = lut_fracs_arr
    cdef int i, idx

    for i in range(n_lut):
        idx = species_map[i]
        if idx >= 0:
            lut_fracs[i] = canonical_fracs[idx]

    # Fold H2O_liq into H2O slot
    for i in range(n_lut):
        if species_map[i] == 5:  # Canonical index for H2O is 5
            lut_fracs[i] += h2o_liq_frac
            break

    return lut_fracs_arr


def warmup_jit_kernels(lut_mgr=None):
    """
    Dummy placeholder to satisfy API requirements.
    
    Cython extensions are built Ahead-of-Time (AOT), meaning they do not 
    require runtime warmup to trigger LLVM compilation like Numba. 
    """
    pass