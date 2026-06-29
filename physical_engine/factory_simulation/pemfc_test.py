"""
PEMFC Model — Empirical Convergence Verification Suite.

Tests the Newton-Raphson solver, Nernst potential bounds, subtractive
sign convention, legacy contamination guard, batch sweep consistency,
and voltage monotonicity.

Reference: doc2 §3, doc5 Phase 1 success criteria.
"""

import numpy as np
import pytest

from physical_engine.factory_simulation.pemfc_model import (
    PEMFCConstants,
    SOLVER_DID_NOT_CONVERGE,
    calculate_nernst_potential,
    calculate_pemfc_voltage,
    newton_raphson_solver,
    batch_polarization_sweep,
)


# Standard operating conditions for tests
_T = 353.15          # 80 °C
_A_H2 = 1.5          # Dimensionless H₂ activity
_A_O2 = 1.0          # Dimensionless O₂ activity
_R_INT = 0.1         # Ω·cm²
_N_CELLS = 200


class TestNernstPotential:
    """Tests for ``calculate_nernst_potential``."""

    def test_standard_conditions(self):
        """At STP activities (1.0, 1.0), E_ocv should be close to 1.229 V."""
        E = calculate_nernst_potential(298.15, 1.0, 1.0)
        # Activity term vanishes at a_h2=1 and a_o2=1 ⇒ ln(1·1^0.5) = 0
        assert abs(E - 1.229) < 0.001

    def test_temperature_dependence(self):
        """E_ocv decreases with increasing temperature."""
        E_low = calculate_nernst_potential(300.0, 1.0, 1.0)
        E_high = calculate_nernst_potential(360.0, 1.0, 1.0)
        assert E_low > E_high

    def test_h2_activity_out_of_bounds_low(self):
        """ValueError for a_h2 < 0.5."""
        with pytest.raises(ValueError, match="H2 activity"):
            calculate_nernst_potential(353.15, 0.3, 1.0)

    def test_h2_activity_out_of_bounds_high(self):
        """ValueError for a_h2 > 10.0."""
        with pytest.raises(ValueError, match="H2 activity"):
            calculate_nernst_potential(353.15, 11.0, 1.0)

    def test_o2_activity_out_of_bounds(self):
        """ValueError for a_o2 outside [0.5, 10.0]."""
        with pytest.raises(ValueError, match="O2 activity"):
            calculate_nernst_potential(353.15, 1.0, 0.1)


class TestPEMFCVoltage:
    """Tests for ``calculate_pemfc_voltage``."""

    def test_subtractive_convention(self):
        """V_cell must be LESS than E_ocv for any j > 0 (fuel cell convention)."""
        for j in [0.01, 0.1, 0.5, 1.0, 1.5, 2.0, 2.4]:
            V_stack, eta_act, eta_ohm, eta_conc, E_ocv = calculate_pemfc_voltage(
                j, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
            )
            V_cell = V_stack / _N_CELLS
            assert V_cell < E_ocv, (
                f"Subtractive convention violated at j={j}: "
                f"V_cell={V_cell:.4f} >= E_ocv={E_ocv:.4f}"
            )

    def test_voltage_monotonicity(self):
        """V(j) must be monotonically decreasing."""
        j_values = np.linspace(0.01, 2.45, 50)
        voltages = []
        for j in j_values:
            V, *_ = calculate_pemfc_voltage(j, _T, _A_H2, _A_O2, _R_INT, _N_CELLS)
            voltages.append(V)

        for i in range(1, len(voltages)):
            assert voltages[i] <= voltages[i - 1], (
                f"Monotonicity violated: V[{i}]={voltages[i]:.4f} > "
                f"V[{i-1}]={voltages[i-1]:.4f} at j={j_values[i]:.4f}"
            )

    def test_c1_patch_region(self):
        """Voltage computation in the C¹ penalty region (ratio > 0.99)."""
        j_boundary = 0.99 * PEMFCConstants.j_lim_pemfc  # = 2.475
        j_inside = 2.49  # ratio = 0.996

        V_b, *_ = calculate_pemfc_voltage(j_boundary, _T, _A_H2, _A_O2, _R_INT, _N_CELLS)
        V_i, *_ = calculate_pemfc_voltage(j_inside, _T, _A_H2, _A_O2, _R_INT, _N_CELLS)

        # Voltage should still decrease past the patch boundary
        assert V_i < V_b

    def test_overpotentials_positive(self):
        """All overpotentials must be non-negative for j > 0."""
        for j in [0.1, 1.0, 2.0, 2.4]:
            _, eta_act, eta_ohm, eta_conc, _ = calculate_pemfc_voltage(
                j, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
            )
            assert eta_act >= 0, f"eta_act negative at j={j}"
            assert eta_ohm >= 0, f"eta_ohm negative at j={j}"
            assert eta_conc >= 0, f"eta_conc negative at j={j}"


class TestNewtonRaphsonSolver:
    """Tests for ``newton_raphson_solver``."""

    def test_penalty_region_convergence(self):
        """Convergence at j = 2.49 A/cm² (ratio=0.996, inside C¹ penalty region).

        This is the critical doc5 Phase 1 success criterion.  The point lies
        inside the penalty-patched region of the Jacobian; convergence must
        be empirically verified, not assumed.
        """
        j_test = 2.49
        V_target, *_ = calculate_pemfc_voltage(
            j_test, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
        )

        j_solved, converged = newton_raphson_solver(
            V_target, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
        )

        assert converged, (
            f"Newton-Raphson did NOT converge at j=2.49 (penalty region). "
            f"Last j={j_solved:.6f}"
        )
        assert abs(j_solved - j_test) < 0.01, (
            f"Solution j={j_solved:.6f} deviates from target j={j_test}"
        )

    def test_mid_range_convergence(self):
        """Convergence at j = 1.0 A/cm² (well within normal operating range)."""
        j_test = 1.0
        V_target, *_ = calculate_pemfc_voltage(
            j_test, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
        )

        j_solved, converged = newton_raphson_solver(
            V_target, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
        )

        assert converged
        assert abs(j_solved - j_test) < 0.001

    def test_low_current_convergence(self):
        """Convergence near the activation-dominated region."""
        j_test = 0.05
        V_target, *_ = calculate_pemfc_voltage(
            j_test, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
        )

        j_solved, converged = newton_raphson_solver(
            V_target, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
        )

        assert converged
        assert abs(j_solved - j_test) < 0.01


class TestLegacyContaminationGuard:
    """Tests for the z_pemfc runtime contamination guard."""

    def test_z_pemfc_equals_4(self):
        """PEMFCConstants.z_pemfc must be exactly 4."""
        assert PEMFCConstants.z_pemfc == 4

    def test_constants_are_frozen(self):
        """PEMFCConstants must be immutable (frozen dataclass)."""
        with pytest.raises(AttributeError):
            PEMFCConstants.z_pemfc = 2  # type: ignore[misc]


class TestBatchSweep:
    """Tests for ``batch_polarization_sweep``."""

    def test_consistency_with_scalar(self):
        """Vectorized results must match individual scalar evaluations."""
        j_values = np.array([0.1, 0.5, 1.0, 1.5, 2.0, 2.4])
        numba_threads = 2

        voltages_batch, flags = batch_polarization_sweep(
            j_values, _T, _A_H2, _A_O2, _R_INT, _N_CELLS, numba_threads
        )

        for i, j in enumerate(j_values):
            V_scalar, *_ = calculate_pemfc_voltage(
                j, _T, _A_H2, _A_O2, _R_INT, _N_CELLS
            )
            assert abs(voltages_batch[i] - V_scalar) < 1e-10, (
                f"Batch/scalar mismatch at j={j}: "
                f"batch={voltages_batch[i]:.10f}, scalar={V_scalar:.10f}"
            )

    def test_rejects_overlimit_current(self):
        """Must raise ValueError if any j >= j_lim."""
        j_values = np.array([1.0, 2.5])  # 2.5 = j_lim
        with pytest.raises(ValueError, match="j_lim"):
            batch_polarization_sweep(
                j_values, _T, _A_H2, _A_O2, _R_INT, _N_CELLS, 1
            )

    def test_twelve_point_sweep(self):
        """Standard 12-point diagnostic sweep produces all valid voltages."""
        j_values = np.linspace(0.05, 2.4, 12)
        numba_threads = max(1, 2)

        voltages, flags = batch_polarization_sweep(
            j_values, _T, _A_H2, _A_O2, _R_INT, _N_CELLS, numba_threads
        )

        assert voltages.shape == (12,)
        assert np.all(np.isfinite(voltages))
        assert flags == 0
