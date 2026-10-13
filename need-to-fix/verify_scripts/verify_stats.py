import pandas as pd, numpy as np
from scipy import stats
df = pd.read_csv("/home/claude/Matrix_Factory-main/analysis/results.csv")
P = df[df.schema=="PROSA"].set_index("run_id"); A = df[df.schema=="ADACOR"].set_index("run_id")
print("n per arm:", len(P), len(A))
print("\n=== S1: dead / near-dead runs ===")
for n,d in (("PROSA",P),("ADACOR",A)):
    dead = d[d.completed_count<=1]
    print(f"  {n}: {len(dead)}/{len(d)} runs with <=1 completion -> run_ids {sorted(dead.index.tolist())}")
print("  PROSA runs 0-4 submitted_count:", P.loc[0:4,'submitted_count'].tolist(), " (first 5 runs of first arm)")
print("  PROSA 7,12,13: submitted/completed:", [(int(P.loc[i,'submitted_count']),int(P.loc[i,'completed_count'])) for i in (7,12,13)],
      " throughput:", [round(P.loc[i,'throughput'],4) for i in (7,12,13)])
print("  PROSA throughput quantiles:", np.round(P.throughput.quantile([.5,.75,.9]).values,4), "| runs 7,12,13 inflated while stuck")

print("\n=== S2: p-value for tardiness_mean under different handling of dead runs (Mann-Whitney, two-sided) ===")
def mw(a,b): return stats.mannwhitneyu(a,b,alternative="two-sided").pvalue
print(f"  as in repo (zeros kept, 15 v 15):                 p={mw(P.tardiness_mean,A.tardiness_mean):.4f}")
Pn,An = P[P.completed_count>1], A[A.completed_count>1]
print(f"  exclude runs with <=1 completion ({len(Pn)} v {len(An)}):       p={mw(Pn.tardiness_mean,An.tardiness_mean):.4f}")
Ph,Ah = P[P.completed_count>=20], A[A.completed_count>=20]
print(f"  only runs with >=20 completions ({len(Ph)} v {len(Ah)}):        p={mw(Ph.tardiness_mean,Ah.tardiness_mean):.4f}")

print("\n=== S3: multiplicity ===")
m6 = [0.2105,0.02997,0.1684,0.9004,0.632,0.8123]
print("  min p in repo stats file = 0.02997; Bonferroni x6 =", round(0.02997*6,3), "; x9 =", round(0.02997*9,3))
# Holm for 6 
order = np.argsort(m6); holm = {}
run=0
for rank,i in enumerate(order):
    run = max(run, min(1,(len(m6)-rank)*m6[i])); holm[i]=run
print("  Holm adjusted (6 tests):", [round(holm[i],3) for i in range(6)])

print("\n=== S4: paired structure (shared seeds => common random numbers) ===")
j = P.join(A, lsuffix="_P", rsuffix="_A")
both = j[(j.completed_count_P>1)&(j.completed_count_A>1)]
print(f"  runs where BOTH arms produced data: {len(both)} of 15")
if len(both)>=6:
    print("  paired Wilcoxon on tardiness_mean:", f"p={stats.wilcoxon(both.tardiness_mean_P, both.tardiness_mean_A).pvalue:.4f}", f"(n={len(both)})")
print("  PROSA-dead run ids vs ADACOR-dead run ids are disjoint? ", set(P[P.completed_count<=1].index).isdisjoint(set(A[A.completed_count<=1].index)))

print("\n=== S5: totals vs report.tex ===")
print("  PROSA submitted/completed sums:", int(P.submitted_count.sum()), int(P.completed_count.sum()))
print("  ADACOR submitted/completed sums:", int(A.submitted_count.sum()), int(A.completed_count.sum()))
print("  (report.tex claims 228/326 PROSA, 297/426 ADACOR -- see grep below)")

print("\n=== S6: energy metric magnitude ===")
print("  energy_cost_eur mean PROSA/ADACOR:", P.energy_cost_eur.mean(), A.energy_cost_eur.mean(), "-> ~1e-5 EUR per run; any price-shaving effect is invisible")
print("\n=== S7: throughput survivorship: CV and healthy-only ===")
print("  PROSA throughput CV=%.2f ; ADACOR CV=%.2f" % (P.throughput.std()/P.throughput.mean(), A.throughput.std()/A.throughput.mean()))
