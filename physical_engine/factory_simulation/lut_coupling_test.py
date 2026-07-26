"""
Regression and unit tests for R5 CoolProp/LUT thermodynamic partial-pressure coupling.
"""

import pytest
import numpy as np

from physical_engine.optimization.lut_manager import water_vapor_partial_pressure, real_gas_activity
from physical_engine.sim_bridge_server import SimBridgeServicer
from physical_engine.protos import sim_bridge_pb2
from physical_engine.factory_simulation.pemfc_model import calculate_nernst_potential


@pytest.fixture(scope="module")
def servicer():
    return SimBridgeServicer(num_cells=100, R_internal=0.1, run_id=999, stack_id="TEST_R5")


def test_water_vapor_partial_pressure_zero_rh():
    assert water_vapor_partial_pressure(353.15, rh=0.0) == 0.0


def test_water_vapor_partial_pressure_80c():
    # At 80 °C (353.15 K), P_sat for water is ~47.3 kPa (47300 Pa)
    p_vap = water_vapor_partial_pressure(353.15, rh=0.8)
    assert 30000.0 < p_vap < 50000.0


def test_real_gas_activity_h2():
    a, phi = real_gas_activity(2e5, 353.15, fluid="H2", rh=0.0)
    # At 2 bar dry H2, activity should be ~2.0 and fugacity coefficient near 1.0
    assert 1.9 < a < 2.1
    assert 0.95 < phi < 1.05


def test_rh_anode_decreases_h2_activity_and_ocv():
    T = 353.15
    P_total = 2e5  # 2 bar

    a_dry, _ = real_gas_activity(P_total, T, fluid="H2", rh=0.0)
    a_humid, _ = real_gas_activity(P_total, T, fluid="H2", rh=0.8)

    assert a_humid < a_dry

    E_ocv_dry = calculate_nernst_potential(T, a_dry, 1.0)
    E_ocv_humid = calculate_nernst_potential(T, a_humid, 1.0)

    assert E_ocv_humid < E_ocv_dry


def test_run_batch_test_rh_anode_backward_compat(servicer):
    # Dry request (rh_anode = 0.0 default)
    req_dry = sim_bridge_pb2.BatchTestRequest(
        stack_id="TEST-DRY",
        num_cells=100,
        operating_temp_k=353.15,
        inlet_pressure_h2_bar=2.0,
        inlet_pressure_o2_bar=2.0,
        rh_anode=0.0
    )
    resp_dry = servicer.RunBatchTest(req_dry, None)
    assert resp_dry.passed is True

    # Humidified request (rh_anode = 0.8)
    req_humid = sim_bridge_pb2.BatchTestRequest(
        stack_id="TEST-HUMID",
        num_cells=100,
        operating_temp_k=353.15,
        inlet_pressure_h2_bar=2.0,
        inlet_pressure_o2_bar=2.0,
        rh_anode=0.8
    )
    resp_humid = servicer.RunBatchTest(req_humid, None)
    assert resp_humid.passed is True

    # Voltages for humidified anode should be slightly lower due to lower H2 partial pressure
    v_dry = list(resp_dry.measured_voltages)
    v_humid = list(resp_humid.measured_voltages)
    for vd, vh in zip(v_dry, v_humid):
        assert vh <= vd + 1e-9
