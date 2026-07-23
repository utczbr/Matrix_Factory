# Statistical Analysis — analysis/results.csv

## Near-zero-completion diagnostic (Limitations §3.1)
- **PROSA**: 8/15 runs completed <= 1 order(s) (53.3%) — run_ids [0, 1, 2, 3, 4, 7, 12, 13]
- **ADACOR**: 2/15 runs completed <= 1 order(s) (13.3%) — run_ids [11, 14]

> **Caution:** >15% of runs in at least one arm completed almost nothing. These runs dominate variance in every metric below; treat aggregate significance tests as exploratory until this is root-caused (see Necessary Correction #2 in the review).

## Per-metric comparison

| Metric | PROSA mean (95% CI) | ADACOR mean (95% CI) | Test | p-value | Effect size |
|---|---|---|---|---|---|
| throughput | 0.008335 [0.005159, 0.01136] | 0.006996 [0.004634, 0.00921] | Mann-Whitney U | 0.2105 | rank-biserial r=-0.2711 |
| tardiness_mean | 200.8 [104.9, 304.4] | 358.8 [250.9, 466.4] | Mann-Whitney U | 0.02997 | rank-biserial r=0.4667 |
| tardiness_max | 698.3 [320.3, 1109] | 1071 [709.4, 1428] | Mann-Whitney U | 0.1684 | rank-biserial r=0.2978 |
| wip_mean | 2.313 [1.266, 3.411] | 2.958 [1.988, 3.824] | Mann-Whitney U | 0.9004 | rank-biserial r=0.03111 |
| energy_cost_eur | 5.551e-06 [2.565e-06, 8.734e-06] | 6.13e-06 [4.015e-06, 8.257e-06] | Mann-Whitney U | 0.632 | rank-biserial r=0.1067 |
| defect_rate | 0.002272 [0, 0.004824] | 0.004031 [0, 0.009192] | Mann-Whitney U | 0.8123 | rank-biserial r=0.04 |
