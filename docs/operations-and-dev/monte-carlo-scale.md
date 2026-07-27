# Monte Carlo Parallel Scaling (How-To Guide)

This how-to guide explains how to configure and run up to **30 parallel, isolated simulation runs within a single JVM** using source-level agent namespace rewriting and seed fan-out.

---

## The Single-JVM Scaling Problem

Running multi-seed Monte Carlo simulation ensembles typically incurs massive JVM startup and memory overhead if each run requires a separate JVM process. Matrix Factory Twin solves this by dynamically scoping agent namespaces and artifact workspace URIs within a single host JVM.

---

## Step-by-Step Execution Guide

### 1. Generating Multi-Seed Project Definitions

Use the template generation script to spawn isolated `.jcm` configuration files:

```bash
python3 experiments/generate_monte_carlo_jcm.py --runs=30 --base-port=50051
```

This generates `factory_1.jcm` through `factory_30.jcm`, assigning unique port offsets ($50051 + i$) for each gRPC physical daemon bridge.

### 2. Spawning Parallel Physical Daemons

Launch Python daemon instances pinned to CPU cores using `daemon_launcher.py`:

```bash
# Launch daemon array across 30 ports
python3 physical_engine/daemon_launcher.py --multi-run=30 --start-port=50051 &
```

### 3. Launching the Multi-Run Batch

Execute the parallel Monte Carlo runner via Gradle:

```bash
./gradlew runMonteCarloBatch --args="--num-seeds=30 --max-ticks=5000 --parallel-threads=8"
```

---

## Log & Result Aggregation

Simulation logs and SQLite database outputs are partitioned by run ID:

```text
analysis/results/
├── run_seed_001.csv
├── run_seed_002.csv
├── ...
├── run_seed_030.csv
└── aggregated_monte_carlo_stats.json
```

To run statistical significance tests (Shapiro-Wilk, Mann-Whitney U, 95% Confidence Intervals) across the generated batch:

```bash
python3 experiments/analyze_results.py analysis/results/aggregated_monte_carlo_stats.json
```
