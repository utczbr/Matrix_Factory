#!/usr/bin/env python3
"""
Statistical analysis for the PROSA-vs-ADACOR experiment.

Necessary Correction #1 (critical-analysis review): the original version of
this script computed a single Shapiro-Wilk + Welch's/Mann-Whitney test on
throughput only, printed to stdout, and never saved its output anywhere —
so the README's "clear, mechanistically grounded signal" claim was never
actually backed by a persisted, reviewable statistical artifact. This
version:

  1. Reports every metric extract_metrics() produces (throughput,
     tardiness_mean, tardiness_max, wip_mean, energy_cost_eur where present),
     not just throughput.
  2. Adds 95% confidence intervals (bootstrap, percentile method — chosen
     over a t-distribution CI because n is typically 5-30 and Shapiro-Wilk
     frequently rejects normality on this data, see below) and an effect
     size for every metric (Cohen's d for the parametric path, rank-biserial
     r for Mann-Whitney).
  3. Explicitly surfaces the near-zero-completion diagnostic from
     Limitations §3.1: how many runs per arm completed <=1 order, since
     these dominate variance and were previously undocumented anywhere
     except a manual read of the raw CSV.
  4. Persists everything to analysis/<prefix>_stats.json and
     analysis/<prefix>_stats.md — the actual "save and report" fix the
     action table asked for.

Usage:
    python3 experiments/analyze_results.py [path/to/results.csv]

Defaults to analysis/results.csv if no path is given.
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as stats

METRICS = ["throughput", "tardiness_mean", "tardiness_max", "wip_mean", "energy_cost_eur", "defect_rate"]
NEAR_ZERO_COMPLETION_THRESHOLD = 1  # completed_count <= this is "near-zero" per Limitations §3.1


def bootstrap_ci(sample: np.ndarray, n_resamples: int = 9999, confidence: float = 0.95):
    """95% percentile-bootstrap CI on the mean. Falls back to a t-based CI
    for n<3 where bootstrap resampling isn't meaningful."""
    sample = np.asarray(sample, dtype=float)
    if len(sample) < 3:
        if len(sample) < 2:
            return (float("nan"), float("nan"))
        m, se = sample.mean(), stats.sem(sample)
        t_crit = stats.t.ppf((1 + confidence) / 2, df=len(sample) - 1)
        return (m - t_crit * se, m + t_crit * se)
    res = stats.bootstrap((sample,), np.mean, n_resamples=n_resamples,
                           confidence_level=confidence, method="percentile",
                           random_state=42)
    return (float(res.confidence_interval.low), float(res.confidence_interval.high))


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d using pooled SD (appropriate alongside Welch's t-test for
    reporting effect size even when variances differ, per common practice)."""
    na, nb = len(a), len(b)
    pooled_sd = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    if pooled_sd == 0:
        return float("nan")
    return float((a.mean() - b.mean()) / pooled_sd)


def rank_biserial_r(u_stat: float, na: int, nb: int) -> float:
    """Rank-biserial correlation effect size for Mann-Whitney U."""
    return float(1 - (2 * u_stat) / (na * nb))


def analyze_metric(prosa: np.ndarray, adacor: np.ndarray, metric_name: str) -> dict:
    result = {
        "metric": metric_name,
        "prosa_n": int(len(prosa)), "adacor_n": int(len(adacor)),
        "prosa_mean": float(np.mean(prosa)), "adacor_mean": float(np.mean(adacor)),
        "prosa_std": float(np.std(prosa, ddof=1)) if len(prosa) > 1 else 0.0,
        "adacor_std": float(np.std(adacor, ddof=1)) if len(adacor) > 1 else 0.0,
    }
    result["prosa_ci95"] = bootstrap_ci(prosa)
    result["adacor_ci95"] = bootstrap_ci(adacor)

    # Normality (Shapiro-Wilk requires n>=3)
    if len(prosa) >= 3 and len(adacor) >= 3:
        _, p_prosa_norm = stats.shapiro(prosa)
        _, p_adacor_norm = stats.shapiro(adacor)
        both_normal = p_prosa_norm > 0.05 and p_adacor_norm > 0.05
    else:
        p_prosa_norm = p_adacor_norm = float("nan")
        both_normal = False

    result["shapiro_p_prosa"] = float(p_prosa_norm)
    result["shapiro_p_adacor"] = float(p_adacor_norm)

    if both_normal:
        stat, p = stats.ttest_ind(prosa, adacor, equal_var=False)
        result["test"] = "Welch's t-test"
        result["test_statistic"] = float(stat)
        result["p_value"] = float(p)
        result["effect_size_name"] = "Cohen's d"
        result["effect_size"] = cohens_d(prosa, adacor)
    else:
        stat, p = stats.mannwhitneyu(prosa, adacor, alternative="two-sided")
        result["test"] = "Mann-Whitney U"
        result["test_statistic"] = float(stat)
        result["p_value"] = float(p)
        result["effect_size_name"] = "rank-biserial r"
        result["effect_size"] = rank_biserial_r(stat, len(prosa), len(adacor))

    return result


def near_zero_completion_diagnostic(df: pd.DataFrame) -> dict:
    """Limitations §3.1: near-zero-completion runs dominate aggregate
    statistics. Report them explicitly instead of leaving this as something
    a reviewer has to discover by reading the raw CSV by hand."""
    out = {}
    for schema in df["schema"].unique():
        sub = df[df["schema"] == schema]
        near_zero = sub[sub["completed_count"] <= NEAR_ZERO_COMPLETION_THRESHOLD]
        out[schema] = {
            "total_runs": int(len(sub)),
            "near_zero_completion_runs": int(len(near_zero)),
            "near_zero_fraction": float(len(near_zero) / len(sub)) if len(sub) > 0 else 0.0,
            "near_zero_run_ids": near_zero["run_id"].tolist(),
        }
    return out


def format_ci(ci):
    if any(np.isnan(x) for x in ci):
        return "n/a"
    return f"[{ci[0]:.4g}, {ci[1]:.4g}]"


def main():
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("analysis/results.csv")
    if not csv_path.exists():
        print(f"Error: {csv_path} not found.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    prosa_df = df[df["schema"] == "PROSA"]
    adacor_df = df[df["schema"] == "ADACOR"]

    prefix = csv_path.stem  # e.g. "results", "results_1440_5"
    out_dir = csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    diagnostic = near_zero_completion_diagnostic(df)

    metric_results = []
    for metric in METRICS:
        if metric not in df.columns:
            continue  # e.g. energy_cost_eur absent from CSVs predating Fix #5
        prosa_vals = prosa_df[metric].dropna().values
        adacor_vals = adacor_df[metric].dropna().values
        if len(prosa_vals) == 0 or len(adacor_vals) == 0:
            continue
        metric_results.append(analyze_metric(prosa_vals, adacor_vals, metric))

    report = {
        "source_csv": str(csv_path),
        "near_zero_completion_diagnostic": diagnostic,
        "metrics": metric_results,
    }

    json_path = out_dir / f"{prefix}_stats.json"
    json_path.write_text(json.dumps(report, indent=2))

    # --- stdout summary + Markdown artifact ---
    lines = [f"# Statistical Analysis — {csv_path}", ""]
    lines.append("## Near-zero-completion diagnostic (Limitations §3.1)")
    for schema, d in diagnostic.items():
        lines.append(
            f"- **{schema}**: {d['near_zero_completion_runs']}/{d['total_runs']} runs "
            f"completed <= {NEAR_ZERO_COMPLETION_THRESHOLD} order(s) "
            f"({d['near_zero_fraction']*100:.1f}%) — run_ids {d['near_zero_run_ids']}"
        )
    if any(d["near_zero_fraction"] > 0.15 for d in diagnostic.values()):
        lines.append(
            "\n> **Caution:** >15% of runs in at least one arm completed almost "
            "nothing. These runs dominate variance in every metric below; "
            "treat aggregate significance tests as exploratory until this is "
            "root-caused (see Necessary Correction #2 in the review)."
        )
    lines.append("")
    lines.append("## Per-metric comparison")
    lines.append("")
    lines.append("| Metric | PROSA mean (95% CI) | ADACOR mean (95% CI) | Test | p-value | Effect size |")
    lines.append("|---|---|---|---|---|---|")

    print(f"=== {csv_path} ===")
    print(f"n(PROSA)={len(prosa_df)}, n(ADACOR)={len(adacor_df)}\n")
    for schema, d in diagnostic.items():
        print(f"[near-zero-completion] {schema}: {d['near_zero_completion_runs']}/{d['total_runs']} "
              f"runs completed <= {NEAR_ZERO_COMPLETION_THRESHOLD} order(s) -> {d['near_zero_run_ids']}")
    print()

    for m in metric_results:
        print(f"--- {m['metric']} ---")
        print(f"  PROSA:  mean={m['prosa_mean']:.4g}  std={m['prosa_std']:.4g}  "
              f"95% CI={format_ci(m['prosa_ci95'])}  (n={m['prosa_n']}, Shapiro p={m['shapiro_p_prosa']:.4g})")
        print(f"  ADACOR: mean={m['adacor_mean']:.4g}  std={m['adacor_std']:.4g}  "
              f"95% CI={format_ci(m['adacor_ci95'])}  (n={m['adacor_n']}, Shapiro p={m['shapiro_p_adacor']:.4g})")
        print(f"  {m['test']}: statistic={m['test_statistic']:.4g}, p={m['p_value']:.4g}, "
              f"{m['effect_size_name']}={m['effect_size']:.4g}")
        print()

        lines.append(
            f"| {m['metric']} | {m['prosa_mean']:.4g} {format_ci(m['prosa_ci95'])} "
            f"| {m['adacor_mean']:.4g} {format_ci(m['adacor_ci95'])} "
            f"| {m['test']} | {m['p_value']:.4g} | {m['effect_size_name']}={m['effect_size']:.4g} |"
        )

    md_path = out_dir / f"{prefix}_stats.md"
    md_path.write_text("\n".join(lines) + "\n")

    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")


if __name__ == "__main__":
    main()
