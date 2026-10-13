"""
Unit tests for Protobuf TelemetryFrame and OrderState schema round-trip serialization.

Validates that order states, energy pricing, and station 5 test bench metrics
serialize and deserialize cleanly across the Python/Java bridge.
"""

import pytest
from physical_engine.protos import sim_bridge_pb2, sim_bridge_pb2_grpc


def test_order_state_roundtrip():
    """Verify OrderState message serialization and fields."""
    order = sim_bridge_pb2.OrderState(
        order_id="ORD-001",
        current_location="S1",
        status="PROCESSING",
        progress=0.75,
    )
    data = order.SerializeToString()

    deserialized = sim_bridge_pb2.OrderState()
    deserialized.ParseFromString(data)

    assert deserialized.order_id == "ORD-001"
    assert deserialized.current_location == "S1"
    assert deserialized.status == "PROCESSING"
    assert pytest.approx(deserialized.progress) == 0.75


def test_telemetry_frame_full_roundtrip():
    """Verify TelemetryFrame with order states, energy pricing, and Station 5 current densities."""
    frame = sim_bridge_pb2.TelemetryFrame(
        sequence_number=42,
        sim_time_s=123.45,
        schema_epoch=2,
        active_org_schema="ADACOR",
        energy_price=150.75,
        station5_has_run_test=True,
        station5_last_test_passed=True,
        station5_last_tested_stack_id="STACK-99",
        station5_last_measured_voltages=[0.95, 0.85, 0.75, 0.65],
        station5_last_current_densities=[0.05, 0.2, 0.5, 1.0],
        order_states=[
            sim_bridge_pb2.OrderState(
                order_id="ORD-01",
                current_location="S2",
                status="BUSY",
                progress=0.4,
            ),
            sim_bridge_pb2.OrderState(
                order_id="ORD-02",
                current_location="AMR-1",
                status="TRANSIT",
                progress=0.9,
            ),
        ],
    )

    data = frame.SerializeToString()
    deserialized = sim_bridge_pb2.TelemetryFrame()
    deserialized.ParseFromString(data)

    assert deserialized.sequence_number == 42
    assert pytest.approx(deserialized.sim_time_s) == 123.45
    assert deserialized.schema_epoch == 2
    assert deserialized.active_org_schema == "ADACOR"
    assert pytest.approx(deserialized.energy_price) == 150.75
    assert deserialized.station5_has_run_test is True
    assert deserialized.station5_last_test_passed is True
    assert deserialized.station5_last_tested_stack_id == "STACK-99"
    assert list(deserialized.station5_last_measured_voltages) == [0.95, 0.85, 0.75, 0.65]
    assert list(deserialized.station5_last_current_densities) == [0.05, 0.2, 0.5, 1.0]

    assert len(deserialized.order_states) == 2
    assert deserialized.order_states[0].order_id == "ORD-01"
    assert deserialized.order_states[0].current_location == "S2"
    assert deserialized.order_states[1].order_id == "ORD-02"
    assert deserialized.order_states[1].current_location == "AMR-1"


def test_telemetry_frame_empty_order_states():
    """Verify TelemetryFrame with empty order states list."""
    frame = sim_bridge_pb2.TelemetryFrame(
        sequence_number=1,
        sim_time_s=0.0,
        energy_price=50.0,
    )
    data = frame.SerializeToString()
    deserialized = sim_bridge_pb2.TelemetryFrame()
    deserialized.ParseFromString(data)

    assert len(deserialized.order_states) == 0
    assert pytest.approx(deserialized.energy_price) == 50.0
