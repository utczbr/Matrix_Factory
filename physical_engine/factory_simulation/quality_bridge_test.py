"""
Regression tests for the Station 1-4 -> Station 5 manufacturing-quality
bridge (r_internal_penalty_ohm_cm2 / activity_derate_fraction on
BatchTestRequest).

Exercises SimBridgeServicer.RunBatchTest directly (in-process, no gRPC
transport) to confirm:
  1. A zero-penalty request reproduces the old "always green" behaviour
     exactly (backward compatible default).
  2. A logged manufacturing defect, translated into a non-zero
     r_internal_penalty_ohm_cm2, actually trips OHMIC_DEGRADATION and
     flips `passed` to False — i.e. Station 5 can now show red.
"""

from __future__ import annotations

import sys

import pytest

from physical_engine.protos import sim_bridge_pb2
from physical_engine.sim_bridge_server import SimBridgeServicer
from physical_engine.factory_simulation.pemfc_model import OHMIC_DEGRADATION


@pytest.fixture(scope="module")
def servicer() -> SimBridgeServicer:
    return SimBridgeServicer(num_cells=100, R_internal=0.1, run_id=999, stack_id="TEST")


def _request(stack_id: str, r_penalty: float = 0.0, derate: float = 0.0):
    return sim_bridge_pb2.BatchTestRequest(
        stack_id=stack_id,
        num_cells=100,
        operating_temp_k=350.0,
        inlet_pressure_h2_bar=2.0,
        inlet_pressure_o2_bar=2.0,
        r_internal_penalty_ohm_cm2=r_penalty,
        activity_derate_fraction=derate,
    )


def test_perfect_stack_passes(servicer):
    resp = servicer.RunBatchTest(_request("STACK-PERFECT"), None)
    assert resp.passed is True
    assert resp.failure_flags == 0


def test_defective_stack_trips_ohmic_degradation(servicer):
    # Mirrors TestBenchArtifact's translation: one logged defect -> +0.08
    # Ω·cm² penalty, which at R_internal=0.1 baseline is enough to cross
    # OHMIC_DEGRADATION_ETA_V=0.35V at the top of the default sweep.
    resp = servicer.RunBatchTest(_request("STACK-DEFECT-1", r_penalty=0.08), None)
    assert resp.passed is False
    assert resp.failure_flags & OHMIC_DEGRADATION


def test_heavily_defective_stack_fails_harder(servicer):
    resp = servicer.RunBatchTest(
        _request("STACK-DEFECT-3", r_penalty=0.24, derate=0.45), None
    )
    assert resp.passed is False
    assert resp.failure_flags & OHMIC_DEGRADATION


def test_missing_penalty_fields_default_to_zero(servicer):
    # A caller that never sets the new fields (proto3 default) must behave
    # exactly like the pre-bridge implementation.
    req = sim_bridge_pb2.BatchTestRequest(
        stack_id="STACK-LEGACY",
        num_cells=100,
        operating_temp_k=350.0,
        inlet_pressure_h2_bar=2.0,
        inlet_pressure_o2_bar=2.0,
    )
    resp = servicer.RunBatchTest(req, None)
    assert resp.passed is True
    assert resp.failure_flags == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
