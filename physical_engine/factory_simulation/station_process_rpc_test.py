import pytest
from physical_engine.sim_bridge_server import SimBridgeServicer
from physical_engine.protos import sim_bridge_pb2
from physical_engine.factory_simulation import station1_mea_preparation as st1
from physical_engine.factory_simulation import station2_catalyst_deposition as st2
from physical_engine.factory_simulation import station3_bipolar_plate_stamping as st3
from physical_engine.factory_simulation import station4_stack_clamping as st4


@pytest.fixture(scope="module")
def servicer():
    return SimBridgeServicer(run_id=0)


def test_station1_rpc_nominal_and_off_nominal(servicer):
    # Nominal
    req = sim_bridge_pb2.StationProcessRequest(
        station_id="S1",
        order_id="ORD-001",
        k_time=1.0,
        station1=sim_bridge_pb2.Station1Params(
            t_press_k=433.15,
            dwell_time_s=180.0
        )
    )
    res = servicer.SimulateStationProcess(req)
    exp = st1.simulate_stage1_mea_prep_safe(433.15, 180.0, 1.0)
    assert pytest.approx(res.proc_time_s) == exp[0]
    assert res.is_defective == exp[1]
    assert pytest.approx(res.var_ratio) == exp[2]
    assert pytest.approx(res.alpha_final) == exp[3]
    assert pytest.approx(res.delamination_risk) == exp[4]
    assert pytest.approx(res.pinhole_risk) == exp[5]

    # Off-nominal
    req_off = sim_bridge_pb2.StationProcessRequest(
        station_id="S1",
        order_id="ORD-002",
        k_time=1.0,
        station1=sim_bridge_pb2.Station1Params(
            t_press_k=400.0,
            dwell_time_s=120.0
        )
    )
    res_off = servicer.SimulateStationProcess(req_off)
    exp_off = st1.simulate_stage1_mea_prep_safe(400.0, 120.0, 1.0)
    assert pytest.approx(res_off.alpha_final) == exp_off[3]


def test_station2_rpc(servicer):
    req = sim_bridge_pb2.StationProcessRequest(
        station_id="S2",
        order_id="ORD-003",
        k_time=1.0,
        station2=sim_bridge_pb2.Station2Params(
            v_coat_m_s=0.15,
            mu_slurry_pa_s=0.050
        )
    )
    res = servicer.SimulateStationProcess(req)
    exp = st2.simulate_stage2_catalyst_deposition_safe(0.15, 0.050, 1.0)
    assert pytest.approx(res.proc_time_s) == exp[0]
    assert res.is_defective == exp[1]
    assert pytest.approx(res.ecsa_ratio) == exp[3]


def test_station3_rpc(servicer):
    req = sim_bridge_pb2.StationProcessRequest(
        station_id="S3",
        order_id="ORD-004",
        k_time=1.0,
        station3=sim_bridge_pb2.Station3Params(
            press_force_kn=120.0,
            die_stroke_count=100,
            w0_initial_wear=0.01,
            use_duplex_coating=True
        )
    )
    res = servicer.SimulateStationProcess(req)
    exp = st3.simulate_stage1_stamping_safe(120.0, 100, 0.01, True, 1.0)
    assert pytest.approx(res.proc_time_s) == exp[0]
    assert res.is_defective == exp[1]
    assert pytest.approx(res.damage_index) == exp[3]


def test_station4_rpc(servicer):
    torques = [46.0, 46.0, 46.0, 46.0]
    frictions = [0.15] * 8
    req = sim_bridge_pb2.StationProcessRequest(
        station_id="S4",
        order_id="ORD-005",
        k_time=1.0,
        station4=sim_bridge_pb2.Station4Params(
            applied_torques_nm=torques,
            friction_coefficients=frictions
        )
    )
    res = servicer.SimulateStationProcess(req)
    exp = st4.simulate_stage2_clamping_safe(torques, frictions, True, 1.0)
    assert pytest.approx(res.proc_time_s) == exp[0]
    assert res.is_defective == exp[1]
    assert pytest.approx(res.gdl_porosity) == exp[3]
    assert pytest.approx(res.e_tangent_mpa) == exp[4]
    assert pytest.approx(res.p_clamp_mpa) == exp[5]
