"""Drive the REAL SimBridgeServicer.RunBatchTest with the exact request the Java TestBenchArtifact builds."""
import sys, time, logging
sys.path.insert(0, "/home/claude/Matrix_Factory-main")
logging.disable(logging.CRITICAL)
import numpy as np
import physical_engine.sim_bridge_server as s
from physical_engine.protos import sim_bridge_pb2 as pb
from physical_engine.factory_simulation.pemfc_model import (OHMIC_DEGRADATION, MASS_TRANSPORT_STARVATION,
        THERMAL_SHUTDOWN, LOW_ACTIVATION, SOLVER_DID_NOT_CONVERGE)

# Remove the 0.5 s wall-clock pacing so we can sweep quickly (we measure it separately)
real_sleep = time.sleep
s.time.sleep = lambda x: None

svc = s.SimBridgeServicer(num_cells=200, R_internal=0.06)   # serve() default R_internal

def flags_to_str(f):
    names = [(OHMIC_DEGRADATION,"OHMIC"),(MASS_TRANSPORT_STARVATION,"MASS_TRANSPORT"),(THERMAL_SHUTDOWN,"THERMAL"),
             (LOW_ACTIVATION,"LOW_ACT"),(SOLVER_DID_NOT_CONVERGE,"SOLVER")]
    return "|".join(n for b,n in names if f & b) or "none"

def java_request(defects, var_ratio=0.0, stations=4, ecsa=1.0, pclamp=4.25, por=0.78):
    # EXACT formulas from TestBenchArtifact.java lines 114,120,126
    r_pen = defects*0.08 + (var_ratio*0.02)/max(stations,1)
    derate = min(0.6, defects*0.15)
    return pb.BatchTestRequest(stack_id="S", num_cells=100, operating_temp_k=350.0,
            inlet_pressure_h2_bar=2.0, inlet_pressure_o2_bar=2.0,   # 1+min(1.5,100*0.01)=2.0
            r_internal_penalty_ohm_cm2=r_pen, activity_derate_fraction=derate,
            ecsa_ratio=ecsa, p_clamp_mpa=pclamp, gdl_porosity=por)

print("=== P7: End-of-line test outcome vs number of upstream defects (real RunBatchTest) ===")
print(f"{'defects':>7} {'passed':>7}  flags")
for d in range(0,5):
    r = svc.RunBatchTest(java_request(d), None)
    print(f"{d:>7} {str(r.passed):>7}  {flags_to_str(r.failure_flags)}  (V@j[0]={r.measured_voltages[0]:.2f}, V@j[-1]={r.measured_voltages[-1]:.2f})")

print("\n=== Does variance alone (0 defects) ever fail? var_ratio sweep ===")
for vr in (0.0, 1.0, 5.0, 20.0):
    r = svc.RunBatchTest(java_request(0, var_ratio=vr), None)
    print(f"  var_ratio={vr:5.1f} -> passed={r.passed} flags={flags_to_str(r.failure_flags)}")

print("\n=== Does a *continuous* upstream signal (ecsa/clamp/porosity) change the outcome with 0 defects? ===")
for lbl,kw in [("ecsa=0.9",dict(ecsa=0.9)),("ecsa=0.5",dict(ecsa=0.5)),("ecsa=0.25",dict(ecsa=0.25)),
               ("p_clamp=3.0",dict(pclamp=3.0)),("p_clamp=6.0",dict(pclamp=6.0)),("porosity=0.6",dict(por=0.6))]:
    r = svc.RunBatchTest(java_request(0, **kw), None)
    print(f"  {lbl:<14} passed={r.passed} flags={flags_to_str(r.failure_flags)}  V_last={r.measured_voltages[-1]:.2f}")

print("\n=== P-thermal: T_core change across sweep ===")
T0 = svc._thermal.T_core
req = java_request(0)
svc.RunBatchTest(req, None)
print(f"  T_core before={T0:.4f} K, after sweep={svc._thermal.T_core:.4f} K, delta={svc._thermal.T_core-T0:+.4f} K")
print(f"  threshold THERMAL_SHUTDOWN=358.15 K (setpoint 350.0 K from Java) -> reachable via heating? delta needed = +{358.15-350.0:.2f} K")
print("  THERMAL flag fires iff operating_temp_k alone > 358.15 ? ->", end=" ")
r = svc.RunBatchTest(pb.BatchTestRequest(stack_id="S",num_cells=100,operating_temp_k=360.0,inlet_pressure_h2_bar=2.0,inlet_pressure_o2_bar=2.0), None)
print(flags_to_str(r.failure_flags))
