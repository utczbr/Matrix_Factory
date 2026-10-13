# Spec: `measurement-integrity`

Module id: `measurement-integrity` · Depends on: `baseline-freeze` · Findings: E-02, E-03, E-08 (+ E-01 *reporting*; root cause is `sim-determinism`) · Depth: **full**

## Objective

**Experiment outputs must never silently turn missing or invalid data into numbers, and every reported statistic must carry the population and multiplicity context it needs.**

Today, `extract_metrics()` (`experiments/run_prosa_vs_adacor.py:85-104`) zero-fills empty runs, divides by the last event time instead of the horizon, and computes "WIP" from completed orders only. The repo's single nominally significant result (p = 0.030) exists only because of those zeros (→ 0.438 or 0.056 depending on handling; Holm-adjusted 0.18 across the repo's 6 tests).

**User:** the thesis author and any reviewer re-running `analysis/`.
**Done looks like:** (1) no code path emits `0` for "no data"; (2) the three corrected metrics match hand-computed oracles; (3) `analyze_results.py` reports Holm-adjusted p-values, paired results when valid, per-arm failure counts, and never prints a prose significance claim; (4) the *old* CSVs can still be analysed through a legacy adapter and reproduce the audit's numbers.

**Out of scope:** *why* runs die (`sim-determinism`), the experiment design (`experiment-redesign`), docs wording (`claims-and-docs`). The existing bootstrap CIs, Cohen's d / rank-biserial effect sizes and the near-zero-completion diagnostic in `analyze_results.py` already exist and are **kept**.

## Definitions (used by every criterion)

| Term | Definition |
|---|---|
| `horizon_s` | Simulated seconds the run was configured to last. Passed explicitly; fallback = max `sim_time` over all telemetry for the run, recorded in `horizon_source`. |
| `started` | `submitted_count ≥ 1`. A run with `started = False` is an **infrastructure failure**: reported, never tested. |
| `stalled` | `started` and `completed_count ≤ 1` (keeps the existing `NEAR_ZERO_COMPLETION_THRESHOLD = 1`). A stall may be a *treatment effect*, so it stays in the primary analysis. |
| `throughput` | `completed_count / horizon_s` (0.0 is a legitimate value for a started run). |
| `wip_time_avg` | `(1/horizon_s) · ∫ N(t) dt`, N(t) = orders submitted and not yet completed, **in-flight orders counted until the horizon**. |
| `cycle_time_mean` | Mean of `completed − submitted` over completed orders; `NaN` if none. (Replaces the misnamed `tardiness_mean`: there is no due date.) |
| `cycle_time_age_incl_mean` | Mean over **all** submitted orders of `min(completion, horizon) − submit`. A **lower bound** on the true mean cycle time of all submitted orders. |
| Population **P1** (primary) | all `started` runs. **P2** (sensitivity) | `started` and not `stalled`. |

## Tech Stack

Python 3.10 (CI), pandas, numpy, scipy ≥ 1.10 (already in use), pytest, hypothesis (already in `requirements.txt`). **No new dependencies.**

## Commands

```
Unit tests (new)        : pytest experiments/tests -q -p no:cacheprovider
Existing suite (guard)  : pytest physical_engine/ -q -p no:cacheprovider      # must stay 70 passed, 14 skipped
Analyse new CSV         : python3 experiments/analyze_results.py analysis/results_v2.csv
Analyse legacy CSV      : python3 experiments/analyze_results.py analysis/results.csv --legacy --horizon-s 3600
Re-run experiment (JVM) : python3 experiments/run_prosa_vs_adacor.py            # user-run (needs Gradle)
Zero-fill scan          : git grep -nE "'(throughput|tardiness_mean|wip_mean)': *0\b" experiments/   # must print nothing
```

## Project Structure

```
experiments/metrics.py            NEW  pure functions: compute_run_metrics(), time_average_wip(), energy_cost_eur()
experiments/stats_utils.py        NEW  holm_adjust(), paired_test(), mann_whitney(), populations()
experiments/legacy_adapter.py     NEW  v1 CSV → v2 columns (masking, no fabrication)
experiments/run_prosa_vs_adacor.py     thin I/O wrapper: SQL → DataFrames → metrics.compute_run_metrics
experiments/analyze_results.py         uses stats_utils; keeps CIs/effect sizes; new report sections
experiments/tests/                NEW  test_metrics.py, test_stats_utils.py, test_legacy_regression.py, test_report.py
experiments/tests/fixtures/       NEW  tiny synthetic order/quality/energy frames
analysis/                              legacy CSVs stay untouched as evidence; new outputs written as *_v2.*
```

## Code Style

```python
def throughput(completed_count: int, horizon_s: float) -> float:
    """Completed orders per simulated second over the configured horizon."""
    if not horizon_s > 0:            # also rejects NaN
        raise ValueError(f"horizon_s must be > 0, got {horizon_s!r}")
    return completed_count / horizon_s
```
Pure functions on DataFrames, no SQL inside `metrics.py`; `NaN` (not `None`, not `0`) for undefined; type hints (`float | None` is fine on 3.10); tests grouped in `TestX` classes with one-line docstrings naming the criterion ID.

## Result schema v2 (`results_v2.csv`)

`schema_version, schema, run_id, batch_index, seed, horizon_s, horizon_source, submitted_count, completed_count, incomplete_count, started, stalled, throughput, cycle_time_mean, cycle_time_max, cycle_time_std, cycle_time_age_incl_mean, wip_time_avg, max_incomplete_age_s, defect_rate, energy_cost_eur, dropped_ner, invalid_reason`
Deprecated aliases kept for one release for the notebook `analysis/prosa_vs_adacor.ipynb`: `tardiness_mean = cycle_time_mean`, `tardiness_max`, `tardiness_std`, `wip_mean = wip_time_avg`. `dropped_ner` and `seed` are `NaN` until `sim-determinism` supplies them.

## Testing Strategy

- **Unit** (`test_metrics.py`, `test_stats_utils.py`): synthetic frames with hand-computed answers.
- **Property** (hypothesis): invariants that don't depend on example values (Holm, age-inclusive lower bound, pair counting).
- **Regression on real data** (`test_legacy_regression.py`): re-analysing the committed legacy CSV must reproduce numbers computed **independently** during the audit with plain `scipy` (see SC-MI-9).
- **Report golden test** (`test_report.py`): structure of `*_stats.md`, and absence of prose significance claims.
- CI: adding `pytest experiments/tests` to `.github/workflows/ci.yml` is **ask-first**.

**Test integrity**
- *Red for the right reason:* each test is run against the **current** `extract_metrics` logic first (copied into the red-phase harness) and must fail on the intended assertion (e.g. "expected nan, got 0"), not on import errors. The task order puts `metrics.py` stubs (raising `NotImplementedError` with correct signatures) first so reds are assertion failures.
- *Traceability:* a table in `tasks/plan.md` maps every SC to ≥ 1 test and every test to an SC.
- *Independent oracles:* WIP and throughput toys are hand-computed in this spec; Holm vector is a hand-worked example; legacy p-values come from the audit script `verify_stats.py` (plain `scipy`), not from the new code.
- *Sabotage check on critical paths (manual, then reverted):* (1) revert denominator to last-event time → SC-MI-3 must fail; (2) return `0.0` for not-started → SC-MI-1 must fail; (3) drop the monotone-max step in Holm → SC-MI-7 must fail; (4) count pairs without requiring both arms started → SC-MI-8 must fail; (5) make WIP ignore in-flight orders → SC-MI-4 must fail.
- *Adversarial review prompt (fresh context):* "Describe an implementation that is wrong but passes all tests." Known candidate to close: treating `stalled` runs as not-started passes SC-MI-1; SC-MI-2 (stalled ⇒ `started = True`, throughput exactly 0.0) is there to catch it.
- *Lock:* approved test files under `experiments/tests/` are protected by a CI step that fails if they change without a `tests-approved` label (**ask-first** with the CI change).

## Boundaries

- **Always:** keep `NaN` semantics end-to-end (never `fillna(0)` on metrics); print both populations (P1, P2) with n per arm; keep deprecated alias columns until `claims-and-docs`; run the existing suite after each task.
- **Ask first:** CI changes; dropping the deprecated alias columns; changing `NEAR_ZERO_COMPLETION_THRESHOLD`; adding any dependency; changing the confirmatory metric family.
- **Never:** edit or overwrite `analysis/results*.csv` or `*_stats.*` in place; invent a horizon silently; emit a p-value when pairing is impossible; write "significant" / "clear signal" prose in generated reports; weaken or delete an existing test.

## Success Criteria

| ID | Criterion (specific, testable) | How verified |
|---|---|---|
| SC-MI-1 | Run with 0 submitted orders ⇒ `started = False`, `invalid_reason = "no_submissions"`, and `throughput, cycle_time_*, wip_time_avg, defect_rate, energy_cost_eur` are all `NaN` (none is `0`). | `test_metrics.py::test_not_started_is_nan` (synthetic frames) |
| SC-MI-2 | Run with ≥ 1 submitted and 0 completed ⇒ `started = True`, `stalled = True`, `throughput == 0.0` exactly, `cycle_time_mean` is `NaN`, `incomplete_count == submitted_count`. | `test_stalled_run` |
| SC-MI-3 | `throughput = completed / horizon_s`. Oracle: 3 completed, last event at t = 78 s, horizon 3600 s ⇒ `3/3600 = 8.333e-4` (old logic gave 3/78 = 0.0385). `horizon_s ≤ 0` or `NaN` ⇒ `ValueError`. | `test_throughput_denominator` |
| SC-MI-4 | `wip_time_avg` equals the hand integral. Oracle: A [0,100], B [50,150], C submitted 150 never completes, horizon 200 ⇒ ∫N dt = 250 ⇒ **1.25**. With C removed ⇒ **1.0**. | `test_wip_time_average_oracle` |
| SC-MI-5 | `cycle_time_age_incl_mean` is a lower bound on the true mean: for any generated truth `{submit_i, true_cycle_i}` truncated at a horizon, the metric ≤ mean(true_cycle). It equals `cycle_time_mean` when no order is incomplete. (Toy: A=100, B=100, C age 50 ⇒ 83.33; **it may be below** the completed-only 100: that is correct.) | hypothesis property test + toy |
| SC-MI-6 | `defect_rate` is `NaN` when no quality rows exist; `energy_cost_eur` is `NaN` when no telemetry exists (the current code returns `0`). | `test_missing_is_nan` |
| SC-MI-7 | `holm_adjust` is correct and monotone. Oracle (hand-worked): p = [0.01, 0.04, 0.03, 0.005] ⇒ adjusted [0.03, 0.06, 0.06, 0.02]. Properties: adjusted ≥ raw; ≤ 1; order-preserving in rank; `NaN` inputs are excluded from the family size and returned as `NaN`. | vector test + hypothesis |
| SC-MI-8 | `paired_test` pairs by `run_id` **only where both arms are `started`** (and the metric is finite in both). `n_pairs < 6` ⇒ status `"insufficient_pairs"` and **no p-value** (the smallest attainable two-sided exact Wilcoxon p is 2/2⁵ = 0.0625 at n = 5, 2/2⁶ = 0.031 at n = 6). When valid, reports n_pairs, median paired difference and a bootstrap CI. | `test_paired_*`; hypothesis on pair counting |
| SC-MI-9 | **Legacy regression** on `analysis/results.csv` (`--legacy`): the helper reproduces the audit's independent Mann–Whitney p on `tardiness_mean`: **0.0300** (all 15 v 15, zeros kept), **0.4378** (exclude `completed_count ≤ 1`: 7 v 13), **0.0559** (`completed_count ≥ 20`: 6 v 10); PROSA runs 0-4 are `started = False`; PROSA runs 7, 12, 13 are `stalled`; Holm over the repo's six-test family multiplies the smallest p (0.02997) by 6 ⇒ **≈ 0.18**. | `test_legacy_regression.py` (tolerance 5e-4) |
| SC-MI-10 | Generated `*_stats.md/json` contain, per metric: population, n per arm, raw p, **Holm-adjusted p**, test used (paired or unpaired, and why), effect size + CI; a per-arm **failure table** (ids of `started = False` and `stalled` runs); and a computed line `Confirmatory family: k tests, min adjusted p = …`. They contain none of the words *significant / clear signal / proves / demonstrates*. | `test_report.py` golden structure + forbidden-word scan |
| SC-MI-11 | `--legacy` never fabricates data: `started/stalled` are derived from counts; metrics of not-started runs are masked to `NaN`; throughput is recomputed as `completed_count / --horizon-s` or `NaN` when `--horizon-s` is absent; unrecoverable columns (`wip_mean`) are marked `legacy_unreliable` and excluded from the confirmatory family with a printed warning. | `test_legacy_adapter.py` |
| SC-MI-12 | `run_prosa_vs_adacor.py` contains no metric arithmetic and no zero-fill; it calls `metrics.compute_run_metrics` and writes schema v2 with `schema_version = 2`. | zero-fill scan (Commands) + code review; JVM run is user-verified |
| SC-MI-13 | `pytest physical_engine/` still reports **70 passed, 14 skipped**; `pytest experiments/tests` is green; CI step added (if approved). | commands above |

## Open Questions

1. **Horizon plumbing.** The runner does not currently know the horizon (it is set by `scripts/launch_phase4.sh` via `--max-ticks` / `maxSimTime`, and I did not find the tick→second conversion). *Default: `HORIZON_S` is an explicit config in the runner; fallback inference is flagged in `horizon_source` and triggers a warning.* Please tell me the intended tick length (is 1 tick = 1 simulated second?).
2. **Stalled runs in the primary population.** *Default: yes (P1 includes them; P2 is the sensitivity analysis), because a stall can be caused by the treatment.* The alternative (exclude them) is exactly the post-treatment conditioning I warned about.
3. **Confirmatory family** (Holm applies within it): *default* `throughput, cycle_time_mean, wip_time_avg, energy_cost_eur, defect_rate`; `cycle_time_max/std` descriptive only.
4. **Shared seeds.** Pairing assumes both arms use the same seed per `run_id` (Review 2 reported `stationId.hashCode() ^ runId`; **I have not verified this myself**). The `seed` column will make it checkable; until then the report prints "pairing assumes shared seeds (unverified)".
5. **Restricted-mean survival time** (Kaplan-Meier RMST) would be a more standard censoring treatment than the age-inclusive lower bound. *Default: not in this module; revisit in `experiment-redesign`.*
6. **Notebook:** `analysis/prosa_vs_adacor.ipynb` reads the CSV. *Default: aliases keep it working; I won't edit the notebook in this module.*
