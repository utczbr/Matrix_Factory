import math
R,F,T=8.314462618,96485.33212,353.15
j=1.0
def eta(slope_mV, j0): return slope_mV*math.log10(j/j0)
rf=100.0
cases = {
 "REPO  (35 mV/dec, j0=2.5e-8, no rf)":            eta(35.0, 2.5e-8),
 "slope fixed only (70, j0=2.5e-8, no rf)":        eta(70.1, 2.5e-8),
 "rf fixed only   (35, j0=2.5e-8*100)":            eta(35.0, 2.5e-8*rf),
 "BOTH fixed      (70, j0=2.5e-8*100)":            eta(70.1, 2.5e-8*rf),
}
print("eta_act at 1 A/cm2 [mV]  (the two errors partially cancel => poor identifiability)")
for k,v in cases.items(): print(f"  {k:<48} {v:6.0f}")
