"""
Cathode Air BOP Subsystem — Verification Suite.

Tests air mass flow rate, compressor parasitic power, and net power output.

Reference: doc2 §3, Larminie & Dicks 2003.
"""

import numpy as np
import pytest

from physical_engine.factory_simulation.cathode_air_bop import (
    calculate_cathode_air_flow_rate,
    calculate_compressor_power,
    calculate_net_stack_power,
)


class TestCathodeAirBOP:
    """Tests for cathode air supply balance-of-plant subsystem."""

    def test_air_flow_rate_scaling(self):
        """Air flow rate scales linearly with stack current and cell count."""
        m_dot_100a = calculate_cathode_air_flow_rate(100.0, 200, lambda_air=2.0)
        m_dot_200a = calculate_cathode_air_flow_rate(200.0, 200, lambda_air=2.0)

        assert m_dot_100a > 0.0
        assert abs(m_dot_200a - 2.0 * m_dot_100a) < 1e-6

    def test_compressor_power_bounds_and_scaling(self):
        """Compressor power is zero at zero flow and increases with pressure ratio."""
        w_zero = calculate_compressor_power(0.0, 101325.0, 202650.0)
        assert w_zero == 0.0

        w_low_p = calculate_compressor_power(0.05, 101325.0, 150000.0)
        w_high_p = calculate_compressor_power(0.05, 101325.0, 250000.0)
        assert w_high_p > w_low_p

    def test_net_power_calculation(self):
        """P_net = P_gross - W_comp."""
        P_gross = 50000.0  # 50 kW
        W_comp = 4000.0    # 4 kW
        P_net = calculate_net_stack_power(P_gross, W_comp)
        assert P_net == 46000.0
