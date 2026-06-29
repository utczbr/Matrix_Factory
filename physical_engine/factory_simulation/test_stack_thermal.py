"""
Stack Thermal Model — Verification Suite.

Tests Yonkist number validation, steady-state convergence with correct
temperature ordering (T_core > T_skin > T_coolant), chiller coupling,
zero-heat decay, and energy conservation.

Reference: doc2 §4.4, doc5 Phase 1
"""

import numpy as np
import pytest

from physical_engine.factory_simulation.stack_thermal_model import StackThermalModel


def _make_model(**kwargs) -> StackThermalModel:
    """Create a StackThermalModel with test-friendly defaults."""
    defaults = dict(
        mass_core_kg=25.0,
        mass_skin_kg=25.0,
        cp_core=500.0,
        cp_skin=500.0,
        h_internal=500.0,
        h_external=25.0,
        A_internal=1.0,
        A_external=2.0,
        k_stack=20.0,
        L_char=0.05,
        T_initial=298.15,
    )
    defaults.update(kwargs)
    return StackThermalModel(**defaults)


class TestYonkistValidation:
    """Tests for the Yonkist number criterion."""

    def test_known_values(self):
        """Verify Yo and Bi computation against hand-calculated values."""
        model = _make_model(h_external=25.0, L_char=0.05, k_stack=20.0)

        # Bi = h_ext * L / k = 25 * 0.05 / 20 = 0.0625
        expected_Bi = 25.0 * 0.05 / 20.0

        # q_gen_vol = 1000 W/m³, delta_T = 10 K
        # Yo = 1000 * 0.05² / (20 * 10) = 1000 * 0.0025 / 200 = 0.0125
        expected_Yo = 1000.0 * 0.05**2 / (20.0 * 10.0)

        Yo, Bi, is_valid = model.validate_yonkist(1000.0, 10.0)

        assert abs(Bi - expected_Bi) < 1e-10
        assert abs(Yo - expected_Yo) < 1e-10
        assert is_valid  # 0.0125 < 0.0625

    def test_violation_detected(self):
        """Yonkist violation (Yo >= Bi) logs warning and returns invalid."""
        model = _make_model(h_external=1.0, L_char=0.1, k_stack=1.0)
        # Bi = 1 * 0.1 / 1 = 0.1
        # With high q_gen and small delta_T, Yo can exceed Bi
        # Yo = 100000 * 0.01 / (1 * 1) = 1000
        Yo, Bi, is_valid = model.validate_yonkist(100000.0, 1.0)
        assert not is_valid
        assert Yo > Bi

    def test_zero_heat_generation(self):
        """Zero heat generation gives Yo = 0, always valid."""
        model = _make_model()
        Yo, Bi, is_valid = model.validate_yonkist(0.0, 10.0)
        assert Yo == 0.0
        assert is_valid


class TestSteadyStateConvergence:
    """Tests for thermal equilibrium behaviour."""

    def test_temperature_ordering(self):
        """At steady state: T_core > T_skin > T_coolant."""
        model = _make_model(T_initial=298.15)
        T_coolant = 298.15
        Q_gen = 500.0  # 500 W constant heat

        dt = 0.1  # seconds
        for _ in range(50000):
            model.step(dt, Q_gen, T_coolant)

        assert model.T_core > model.T_skin, (
            f"Expected T_core > T_skin, got {model.T_core:.2f} <= {model.T_skin:.2f}"
        )
        assert model.T_skin > T_coolant, (
            f"Expected T_skin > T_coolant, got {model.T_skin:.2f} <= {T_coolant:.2f}"
        )

    def test_convergence_flatness(self):
        """After enough steps, dT/dt ≈ 0 (steady state)."""
        model = _make_model(T_initial=298.15)
        T_coolant = 298.15
        Q_gen = 500.0
        dt = 0.1

        for _ in range(100000):
            model.step(dt, Q_gen, T_coolant)

        T_core_before = model.T_core
        T_skin_before = model.T_skin
        model.step(dt, Q_gen, T_coolant)

        assert abs(model.T_core - T_core_before) < 1e-6
        assert abs(model.T_skin - T_skin_before) < 1e-6


class TestChillerCoupling:
    """Tests for Q_output → chiller interface."""

    def test_positive_heat_output(self):
        """Q_output must be positive when stack is heated above coolant."""
        model = _make_model(T_initial=350.0)
        T_coolant = 298.15
        Q_gen = 1000.0

        Q_output = model.step(0.1, Q_gen, T_coolant)
        assert Q_output > 0, f"Expected positive Q_output, got {Q_output}"

    def test_zero_heat_no_output(self):
        """With Q_gen=0 and T = T_coolant, Q_output ≈ 0."""
        model = _make_model(T_initial=298.15)
        T_coolant = 298.15

        Q_output = model.step(0.1, 0.0, T_coolant)
        assert abs(Q_output) < 1e-6


class TestDecayBehaviour:
    """Tests for thermal decay toward coolant temperature."""

    def test_decay_to_coolant(self):
        """With Q_gen = 0, temperatures decay toward T_coolant."""
        model = _make_model(T_initial=400.0)
        T_coolant = 298.15
        dt = 0.1

        for _ in range(200000):
            model.step(dt, 0.0, T_coolant)

        assert abs(model.T_core - T_coolant) < 0.1, (
            f"T_core={model.T_core:.2f} did not decay to T_coolant={T_coolant}"
        )
        assert abs(model.T_skin - T_coolant) < 0.1


class TestEnergyConservation:
    """Tests for energy balance at steady state."""

    def test_steady_state_energy_balance(self):
        """At steady state, Q_gen ≈ Q_output (energy in = energy out)."""
        model = _make_model(T_initial=298.15)
        T_coolant = 298.15
        Q_gen = 750.0
        dt = 0.1

        Q_output = 0.0
        for _ in range(100000):
            Q_output = model.step(dt, Q_gen, T_coolant)

        # At steady state, all generated heat must exit through the skin
        assert abs(Q_output - Q_gen) < 1.0, (
            f"Energy imbalance: Q_gen={Q_gen:.2f}, Q_output={Q_output:.2f}"
        )


class TestGetState:
    """Tests for state reporting."""

    def test_state_dict_keys(self):
        """get_state() must return all expected keys."""
        model = _make_model()
        model.step(0.1, 100.0, 298.15)

        state = model.get_state()
        expected_keys = {
            "T_core_K", "T_skin_K", "Q_output_W",
            "Yonkist_number", "Biot_number", "yonkist_valid",
        }
        assert expected_keys == set(state.keys())

    def test_reset(self):
        """reset() restores initial conditions."""
        model = _make_model(T_initial=300.0)
        model.step(0.1, 1000.0, 298.15)
        assert model.T_core != 300.0  # Sanity check: step changed it

        model.reset()
        assert model.T_core == 300.0
        assert model.T_skin == 300.0
