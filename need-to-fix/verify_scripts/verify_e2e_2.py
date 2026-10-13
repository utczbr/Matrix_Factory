import sys, time, logging
sys.path.insert(0, "/home/claude/Matrix_Factory-main")
logging.disable(logging.CRITICAL)
import numpy as np
import physical_engine.sim_bridge_server as s
from physical_engine.protos import sim_bridge_pb2 as pb
from physical_engine.factory_simulation import microstructure
from physical_engine.factory_simulation.membrane_hydration import compute_membrane_resistance
s.time.sleep = lambda x: None

def fresh(): return s.SimBridgeServicer(num_cells=200, R_internal=0.06)
def req(defects, pH2=2.0, pO2=2.0, T=350.0):
    return pb.BatchTestRequest(stack_id="S", num_cells=100, operating_temp_k=T,
        inlet_pressure_h2_bar=pH2, inlet_pressure_o2_bar=pO2,
        r_internal_penalty_ohm_cm2=defects*0.08, activity_derate_fraction=min(0.6,defects*0.15))
def names(f):
    n=[(1,"OHMIC"),(2,"MASS"),(4,"THERMAL"),(8,"LOW_ACT"),(16,"SOLVER")]
    return "|".join(x for b,x in n if f&b) or "none"

print("=== (a) LOW_ACT vs inlet pressure & defects  [Java default is 2.0/2.0 bar] ===")
for p in (1.0, 2.0):
    row=[]
    for d in range(0,5):
        r = fresh().RunBatchTest(req(d,p,p), None); row.append(f"d{d}:{names(r.failure_flags)}")
    print(f"  p={p} bar  ", "  ".join(row))

print("\n=== (b) Does request.operating_temp_k drive the electrochemistry or THERMAL flag? ===")
for T in (300.0, 350.0, 360.0, 400.0):
    r = fresh().RunBatchTest(req(0,T=T), None)
    print(f"  operating_temp_k={T:5.0f}  V[0]={r.measured_voltages[0]:.4f}  V[-1]={r.measured_voltages[-1]:.4f}  flags={names(r.failure_flags)}")

print("\n=== (c) Ohmic budget: where does Station-4 contact resistance sit? ===")
rc = microstructure.compute_contact_resistance(4.25, 0.78)
rmem = compute_membrane_resistance(14.0, 353.15, 0.005)
print(f"  R_internal,0={0.06:.4f}  R_mem(lambda=14)={rmem:.4f}  R_contact(nominal Station4)={rc:.4f}  total={0.06+rmem+rc:.4f} Ohm cm2")
print(f"  contact share = {rc/(0.06+rmem+rc)*100:.1f}% | one defect adds 0.08 = {0.08/(0.06+rmem+rc)*100:.0f}% of baseline")
for pc,por in ((3.0,0.78),(6.0,0.78),(4.25,0.6),(2.0,0.5)):
    print(f"  p_clamp={pc} por={por}: R_contact={microstructure.compute_contact_resistance(pc,por):.4f}")
# threshold: OHMIC if eta_ohm=j*R > 0.35 V at j_max=2.375
jmax=0.95*2.5
print(f"  OHMIC threshold 0.35 V at j_max={jmax:.3f} -> R_crit = {0.35/jmax:.4f} Ohm cm2 ; baseline R = {0.06+rmem+rc:.4f}")
print(f"  => headroom before OHMIC trips = {0.35/jmax-(0.06+rmem+rc):.4f}  (one defect adds 0.0800 > headroom)")
