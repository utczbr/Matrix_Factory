"""
cathode_air_bop.py — Cathode Air-Supply BOP Subsystem.

Models cathode air supply mass flow rate, stoichiometry, and centrifugal
compressor/blower parasitic power consumption.

Reference:
    Larminie, J., & Dicks, A. (2003). Fuel Cell Systems Explained. Wiley.
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

_F: float = 96485.33212      # Faraday constant [C/mol]
_M_AIR: float = 0.02897       # Air molar mass [kg/mol]
_CP_AIR: float = 1005.0       # Air specific heat capacity [J/(kg·K)]
_GAMMA_AIR: float = 1.4       # Air heat capacity ratio (Cp/Cv)


@njit(nogil=True, cache=True)
def calculate_cathode_air_flow_rate(
    I_total_a: float,
    N_cells: int,
    lambda_air: float = 2.0
) -> float:
    """Compute required cathode air mass flow rate m_dot_air [kg/s].

    .. math::

        \\dot{m}_{air} = \\lambda_{air} \\cdot \\frac{N_{cells} \\cdot I_{total}}{4 F} \\cdot \\frac{M_{air}}{0.21}

    Args:
        I_total_a: Total stack current [A].
        N_cells: Number of cells in stack.
        lambda_air: Air stoichiometry ratio (default 2.0).

    Returns:
        Air mass flow rate [kg/s].
    """
    I_safe = max(0.0, float(I_total_a))
    lam_safe = max(1.0, float(lambda_air))

    n_o2_moles_sec = (N_cells * I_safe) / (4.0 * _F)
    m_dot = lam_safe * n_o2_moles_sec * (_M_AIR / 0.21)
    return float(m_dot)


@njit(nogil=True, cache=True)
def calculate_compressor_power(
    m_dot_air_kg_s: float,
    P_in_pa: float = 101325.0,
    P_out_pa: float = 202650.0,
    T_in_k: float = 298.15,
    eta_comp: float = 0.75
) -> float:
    """Compute air compressor parasitic power W_comp [W].

    .. math::

        W_{comp} = \\frac{\\dot{m}_{air} C_{p,air} T_{in}}{\\eta_{comp}}
                   \\left[\\left(\\frac{P_{out}}{P_{in}}\\right)^{\\frac{\\gamma-1}{\\gamma}} - 1\\right]

    Args:
        m_dot_air_kg_s: Air mass flow rate [kg/s].
        P_in_pa: Inlet pressure [Pa] (default 1 atm).
        P_out_pa: Delivery pressure [Pa] (default 2 atm).
        T_in_k: Inlet air temperature [K] (default 298.15 K).
        eta_comp: Isentropic compressor efficiency in (0, 1] (default 0.75).

    Returns:
        Compressor power [W].
    """
    m_dot_safe = max(0.0, float(m_dot_air_kg_s))
    if m_dot_safe <= 1e-12:
        return 0.0

    p_ratio = max(1.0, P_out_pa / max(1000.0, P_in_pa))
    exponent = (_GAMMA_AIR - 1.0) / _GAMMA_AIR
    eta_safe = max(0.1, min(1.0, float(eta_comp)))

    work_ideal = m_dot_safe * _CP_AIR * T_in_k * (p_ratio ** exponent - 1.0)
    return float(work_ideal / eta_safe)


@njit(nogil=True, cache=True)
def calculate_net_stack_power(
    P_gross_w: float,
    W_comp_w: float
) -> float:
    """Compute net stack electrical power P_net = P_gross - W_comp [W]."""
    return float(P_gross_w - W_comp_w)
