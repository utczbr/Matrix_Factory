# Monte Carlo Parallel Scaling (How-To Guide)

This how-to guide explains how to configure and run up to **30 parallel, isolated simulation runs within a single JVM** using source-level agent namespace rewriting and seed fan-out.

---

## The Single-JVM Scaling Problem

Running multi-seed Monte Carlo simulation ensembles typically incurs massive JVM startup and memory overhead if each run requires a separate JVM process. Matrix Factory Twin solves this by dynamically scoping agent namespaces and artifact workspace URIs within a single host JVM.

---

## Step-by-Step Execution Guide

### 1. Generating Multi-Seed Project Definitions

JaCaMo Phase 4 mode operates on `.jcm` project definitions (such as `factory.jcm` or Phase 4 template files) where agent names and artifact workspaces are dynamically scoped per run ID ($0 \dots N-1$).

> **Note:** If regenerating custom `.jcm` topology definitions, confirm the generator script path with the JaCaMo project maintainer.

### 2. Spawning Parallel Physical Daemons

Launch Python daemon instances pinned to CPU cores using `daemon_launcher.py`:

```bash
# Launch 30 physical daemon processes starting at port 50051
python3 physical_engine/daemon_launcher.py \
  --run-start-id 0 --run-count 30 --base-port 50051 --jvm-reserved-cores 2 &
```

### 3. Launching the Multi-Run Batch

Execute the parallel Phase 4 Monte Carlo runner via Gradle:

```bash
./gradlew run --args="--phase4 --run-count=30 --base-port=50051 --run-start-id=0 --max-ticks=5000 --phase4-jcm-dir=."
```

---

## Log & Result Aggregation

Simulation logs and quality metrics are logged asynchronously to `factory_history.db` SQLite WAL tables (`Orders`, `StationQuality`, `EnergyTelemetry`), indexed by `run_id`.

To execute comparative analysis (e.g., PROSA vs. ADACOR baseline under energy price spikes):

```bash
python3 experiments/run_prosa_vs_adacor.py
```

To run statistical significance tests (Shapiro-Wilk, Mann-Whitney U, 95% Confidence Intervals) across the generated batch:

```bash
python3 experiments/analyze_results.py analysis/prosa_vs_adacor_summary.csv
```
