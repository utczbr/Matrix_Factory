"""Independent verification of physics claims against the REAL repo code."""
import sys, math
sys.path.insert(0, "/home/claude/Matrix_Factory-main")
import numpy as np
from physical_engine.factory_simulation import pemfc_model as pm
from physical_engine.factory_simulation.membrane_hydration import compute_membrane_resistance

R, F = 8.314462618, 96485.33212
T = 353.15

print("=== P1: Tafel slope (alpha*z) ===")
# slope per decade = ln(10) * RT / (alpha*z*F)
for az, label in [(0.5*4, "repo: alpha=0.5, z=4"), (0.5*1, "textbook: alpha=0.5, n_rds=1"), (1.0, "alpha*n=1 (~60-70 mV/dec @ 80C is 2.303RT/F*(1/alpha)=)")]:
    slope = math.log(10) * R*T/(az*F) * 1000
    print(f"  alpha*z={az:<4}  {label:<60} -> {slope:6.1f} mV/dec")
# empirical from code: eta_act at j and 10j
j0 = pm._effective_j0(2.5e-8, 1.0, T, 68500.0, 353.15)
_, e1, *_ = pm.calculate_pemfc_voltage(0.01, T, 1.0, 1.0)
_, e2, *_ = pm.calculate_pemfc_voltage(0.10, T, 1.0, 1.0)
print(f"  EMPIRICAL from calculate_pemfc_voltage: d(eta_act)/decade = {(e2-e1)*1000:.2f} mV/dec")

print("\n=== P2: j0 vs roughness ===")
print(f"  j0 used geometrically (ecsa_ratio=1): {j0:.3e} A/cm2_geo")
print(f"  With roughness factor 100 (typical Pt/C cathode, ~0.4 mgPt/cm2): {j0*100:.3e}")
print(f"  eta_act @ 1 A/cm2 repo: {pm.calculate_pemfc_voltage(1.0,T,1.0,1.0)[1]*1000:.1f} mV")
print("  (code has no roughness factor: grep below)")

print("\n=== P3: Tafel out of domain (j < j0) ===")
for j in (1e-10, 1e-9, 1e-8, 1e-6, 1e-4):
    V, ea, eo, ec, E = pm.calculate_pemfc_voltage(j, T, 1.0, 1.0, N_cells=1)
    flag = "  <-- V > OCV (unphysical)" if V > E else ""
    print(f"  j={j:8.0e}  eta_act={ea*1000:8.1f} mV  V_cell={V:.4f}  OCV={E:.4f}{flag}")

print("\n=== P4: Heat balance (entropic term) ===")
j = 1.0
V, ea, eo, ec, E = pm.calculate_pemfc_voltage(j, T, 1.0, 1.0, N_cells=1)
Rtot = 0.06 + compute_membrane_resistance(14.0, T, 0.005)
q_model = j*(ea+eo)          # what Station-5 thermal uses (no conc, no entropy)
q_model_all = j*(ea+eo+ec)
for name, Etn in (("vapour 1.254V", 1.254), ("liquid 1.481V", 1.481)):
    q_true = j*(Etn - V)
    print(f"  V_cell={V:.4f}  R_total={Rtot:.4f}  Q_true({name})={q_true:.3f} W/cm2  model(act+ohm)={q_model:.3f}  coverage={q_model/q_true*100:.0f}%")
print(f"  model incl. conc.: {q_model_all:.3f} W/cm2")
print(f"  Nernst base used by code: E_rev_std=1.229 V  (=> implies LIQUID water, E_tn should be 1.481)")

print("\n=== P5: D_eff / j_lim ===")
print(f"  D_eff(eps=0.78, s=0)  = {pm.effective_diffusivity(0.78, 0.0):.3e}  vs D0={pm.D0_O2_GDL:.1e}  ratio={pm.effective_diffusivity(0.78,0.0)/pm.D0_O2_GDL:.2f}")
print(f"  Scaled j_lim = 2.5 * 0.78^? -> 2.5*0.78 = {2.5*0.78:.2f}")

print("\n=== P6: flooding ODE dimensional check ===")
w_prod = (1.0*1e4)/(2*F)
print(f"  water_production @1 A/cm2 = {w_prod:.4f} mol/(m2 s)  | GDL_SATURATION_CAPACITY={pm.GDL_SATURATION_CAPACITY} (dimensionless)")
print(f"  => ds/dt = {w_prod/pm.GDL_SATURATION_CAPACITY:.4f}  [mol/(m2 s)], NOT [1/s]. s saturates (0->0.99) in {0.99/(w_prod/pm.GDL_SATURATION_CAPACITY):.1f} s")
# proper scaling: ds/dt = (N_w * M_w/rho_l)/(eps*delta)  -> [1/s]
Mw, rho, eps, delta = 0.018, 998.0, 0.78, 200e-6
ds_dt_proper = (w_prod*Mw/rho)/(eps*delta)
print(f"  Dimensionally-consistent (M_w/rho_l/(eps*delta_GDL)) = {ds_dt_proper:.3e} 1/s -> {1/ds_dt_proper:.0f} s to fill if NO removal (order-of-magnitude, assumes all product stays liquid)")
