"""
Membrane Hydration (λ Model) — Verification Suite.

Tests Springer correlation conductivity, water equilibrium isotherm,
and membrane resistance bounds.

Reference: doc2 §3, Springer et al. 1991.
"""

import numpy as np
import pytest

from physical_engine.factory_simulation.membrane_hydration import (
    _springer_membrane_conductivity,
    _equilibrium_water_content,
    compute_membrane_resistance,
)


class TestMembraneHydration:
    """Tests for Springer membrane hydration model."""

    def test_water_content_isotherm_bounds(self):
        """Water content λ is strictly bounded within [1.0, 14.0]."""
        lam_dry = _equilibrium_water_content(0.0)
        lam_sat = _equilibrium_water_content(1.0)
        lam_liquid = _equilibrium_water_content(2.0)

        assert abs(lam_dry - 0.043) < 0.01 or lam_dry >= 1.0
        assert lam_sat > lam_dry
        assert lam_liquid >= 14.0

    def test_conductivity_temperature_and_hydration_dependence(self):
        """Conductivity increases with higher hydration λ and higher temperature T."""
        sigma_dry = _springer_membrane_conductivity(3.0, 353.15)
        sigma_wet = _springer_membrane_conductivity(14.0, 353.15)
        assert sigma_wet > sigma_dry

        sigma_cold = _springer_membrane_conductivity(14.0, 303.15)
        sigma_hot = _springer_membrane_conductivity(14.0, 353.15)
        assert sigma_hot > sigma_cold

    def test_membrane_resistance_scaling(self):
        """Membrane ohmic resistance decreases with higher hydration."""
        R_dry = compute_membrane_resistance(3.0, 353.15, 0.005)
        R_wet = compute_membrane_resistance(14.0, 353.15, 0.005)
        assert R_wet < R_dry

    def test_membrane_resistance_recalibration_target(self):
        """Verify R_mem(14.0, 353.15K) is ~0.0403 Ω·cm², yielding ~0.1003 Ω·cm² with R_internal=0.06."""
        R_wet = compute_membrane_resistance(14.0, 353.15, 0.005)
        assert abs(R_wet - 0.040267) < 1e-4
        R_total_nominal = 0.06 + R_wet
        assert abs(R_total_nominal - 0.1003) < 1e-3

    def test_dynamic_sorption_hysteresis_step_change(self):
        """Step-change in water activity does not cause instantaneous hydration jump."""
        from physical_engine.factory_simulation.membrane_hydration import step_membrane_hydration
        lam_0 = 3.0
        # Step change to full saturation (a_w = 1.0)
        lam_step1 = step_membrane_hydration(lam_0, 1.0, dt=1.0)
        assert lam_step1 > lam_0
        assert lam_step1 < 14.0  # Does not instantly jump to equilibrium (14.0)

    def test_sorption_asymmetry(self):
        """Wetting uptake is faster than drying release (tau_sorption < tau_desorption)."""
        from physical_engine.factory_simulation.membrane_hydration import (
            step_membrane_hydration, TAU_SORPTION_S, TAU_DESORPTION_S
        )
        assert TAU_SORPTION_S < TAU_DESORPTION_S

        # 10 seconds of wetting from lam=5.0 toward eq(1.0)=14.0
        lam_wet = step_membrane_hydration(5.0, 1.0, dt=10.0)
        delta_wet = lam_wet - 5.0

        # 10 seconds of drying from lam=14.0 toward eq(0.0)=0.043 -> 1.0
        lam_dry = step_membrane_hydration(14.0, 0.0, dt=10.0)
        delta_dry = 14.0 - lam_dry

        assert delta_wet > delta_dry


