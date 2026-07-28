import pytest
import numpy as np
from physical_engine.factory_simulation.pemfc_model import (
    step_liquid_saturation,
    effective_diffusivity,
    D0_O2_GDL,
)


def test_effective_diffusivity_monotonicity():
    """Effective diffusivity strictly decreases as saturation s increases."""
    eps = 0.78
    d_0 = effective_diffusivity(eps, 0.0)
    d_half = effective_diffusivity(eps, 0.5)
    d_high = effective_diffusivity(eps, 0.9)

    assert d_0 == pytest.approx(D0_O2_GDL * eps)
    assert d_0 > d_half > d_high > 0.0


def test_step_liquid_saturation_accumulation():
    """High current density with low air removal causes liquid water accumulation."""
    s_0 = 0.1
    # 1.5 A/cm2, zero removal, 1 sec step
    s_1 = step_liquid_saturation(s_0, 1.5, 0.0, dt=1.0)
    assert s_1 > s_0
    assert s_1 <= 0.99
