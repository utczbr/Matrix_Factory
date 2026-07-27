"""
station_mechanistic_test.py — Property-Based Tests for Stations 1–4 First-Principles Kernels.

Validates invariants across valid physical input domains using Hypothesis:
  - Non-negative, finite outputs
  - Expected physical range bounds (porosity in [0.01, 0.95], degree of cure in [0.0, 1.0], ECSA ratio in [0.1, 1.0])
  - Monotonic variance ratio response (var_ratio >= 1.0)
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings, strategies as st

from physical_engine.factory_simulation.station1_mea_preparation import (
    simulate_stage1_mea_prep_safe,
    T_PRESS_NOMINAL_K,
    DWELL_TIME_NOMINAL_S,
)
from physical_engine.factory_simulation.station2_catalyst_deposition import (
    simulate_stage2_catalyst_deposition_safe,
    V_COAT_NOMINAL_M_S,
    MU_SLURRY_NOMINAL_PA_S,
)
from physical_engine.factory_simulation.station3_bipolar_plate_stamping import (
    simulate_stage1_stamping_safe,
    F_NOM_S3,
)
from physical_engine.factory_simulation.station4_stack_clamping import (
    simulate_stage2_clamping_safe,
    TORQUE_NOMINAL_NM,
)


@given(
    t_press_k=st.floats(min_value=350.0, max_value=473.15),
    dwell_time_s=st.floats(min_value=30.0, max_value=600.0),
    k_time=st.sampled_from([1.0, 10.0]),
)
@settings(max_examples=50)
def test_station1_mea_prep_invariants(t_press_k: float, dwell_time_s: float, k_time: float):
    proc_time_s, is_defective, var_ratio, alpha_final, delamination_risk, pinhole_risk = (
        simulate_stage1_mea_prep_safe(t_press_k, dwell_time_s, k_time)
    )

    assert proc_time_s > 0.0
    assert 0.0 <= alpha_final <= 1.0
    assert 0.0 <= delamination_risk <= 1.0
    assert 0.0 <= pinhole_risk <= 1.0
    assert var_ratio >= 1.0
    assert isinstance(is_defective, bool)


@given(
    v_coat_m_s=st.floats(min_value=0.05, max_value=0.50),
    mu_slurry_pa_s=st.floats(min_value=0.01, max_value=0.20),
    k_time=st.sampled_from([1.0, 10.0]),
)
@settings(max_examples=50)
def test_station2_catalyst_deposition_invariants(
    v_coat_m_s: float, mu_slurry_pa_s: float, k_time: float
):
    proc_time_s, is_defective, var_ratio, ecsa_ratio = (
        simulate_stage2_catalyst_deposition_safe(v_coat_m_s, mu_slurry_pa_s, k_time)
    )

    assert proc_time_s > 0.0
    assert 0.10 <= ecsa_ratio <= 1.00
    assert var_ratio >= 1.0
    assert isinstance(is_defective, bool)


@given(
    press_force_kn=st.floats(min_value=50.0, max_value=250.0),
    die_stroke_count=st.integers(min_value=0, max_value=1_000_000),
    w0_initial_wear=st.floats(min_value=0.0, max_value=0.5),
    use_duplex=st.booleans(),
    k_time=st.sampled_from([1.0, 10.0]),
)
@settings(max_examples=50)
def test_station3_bipolar_plate_stamping_invariants(
    press_force_kn: float,
    die_stroke_count: int,
    w0_initial_wear: float,
    use_duplex: bool,
    k_time: float,
):
    proc_time_s, is_defective, var_ratio, damage_index = simulate_stage1_stamping_safe(
        press_force_kn, die_stroke_count, w0_initial_wear, use_duplex, k_time
    )

    assert proc_time_s > 0.0
    assert 0.0 <= damage_index <= 2.0
    assert var_ratio >= 1.0
    assert isinstance(is_defective, bool)


@given(
    torques=st.lists(st.floats(min_value=20.0, max_value=60.0), min_size=4, max_size=4),
    friction=st.lists(st.floats(min_value=0.05, max_value=0.30), min_size=8, max_size=8),
    k_time=st.sampled_from([1.0, 10.0]),
)
@settings(max_examples=50)
def test_station4_stack_clamping_invariants(
    torques: list[float], friction: list[float], k_time: float
):
    proc_time_s, is_defective, var_ratio, gdl_porosity, e_tangent_mpa, p_clamp_mpa = (
        simulate_stage2_clamping_safe(torques, friction, True, k_time)
    )

    assert proc_time_s > 0.0
    assert 0.01 <= gdl_porosity <= 0.95
    assert p_clamp_mpa >= 0.0
    assert e_tangent_mpa > 0.0
    assert var_ratio >= 1.0
    assert isinstance(is_defective, bool)
