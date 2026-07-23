# Statistical Analysis — analysis/results_360_10.csv

## Near-zero-completion diagnostic (Limitations §3.1)
- **PROSA**: 1/10 runs completed <= 1 order(s) (10.0%) — run_ids [6]
- **ADACOR**: 2/10 runs completed <= 1 order(s) (20.0%) — run_ids [8, 9]

> **Caution:** >15% of runs in at least one arm completed almost nothing. These runs dominate variance in every metric below; treat aggregate significance tests as exploratory until this is root-caused (see Necessary Correction #2 in the review).

## Per-metric comparison

| Metric | PROSA mean (95% CI) | ADACOR mean (95% CI) | Test | p-value | Effect size |
|---|---|---|---|---|---|
| throughput | 0.01392 [0.01225, 0.01564] | 0.01156 [0.009508, 0.01361] | Welch's t-test | 0.1205 | Cohen's d=0.7303 |
| tardiness_mean | 145 [124.5, 168.1] | 169 [132.8, 200.4] | Mann-Whitney U | 0.2123 | rank-biserial r=0.34 |
| tardiness_max | 228.4 [173.4, 285.1] | 255.7 [189.1, 311.1] | Mann-Whitney U | 0.6776 | rank-biserial r=0.12 |
| wip_mean | 1.978 [1.709, 2.187] | 1.833 [1.465, 2.161] | Mann-Whitney U | 0.8501 | rank-biserial r=-0.06 |
| defect_rate | 0 [0, 0] | 0 [0, 0] | Welch's t-test | nan | Cohen's d=nan |
