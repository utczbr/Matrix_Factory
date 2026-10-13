# Capability Map: Matrix Factory Remediation (v2: approved with edits)

Evidence ledger: `VERIFICATION.md` (finding IDs P-/E-/M-/D- below). Module ids are stable from here on.

## Decisions recorded (from your answers)

| # | Decision |
|---|---|
| Q1 | Research question: **a reproducible testbed for evaluating control and price-spike policies in matrix manufacturing, using downstream PEMFC performance as the quality metric.** |
| Q2 | ADACOR: **implement real stationary→transient mode-switching** (autonomy factor, recovery timer) **alongside ablation arms.** Adds module `adacor-mode-switching`. |
| Q3 | Validation data: one published polarization dataset with full parameter tables: **proposed in `VALIDATION-DATASET-PICK.md` (you confirm).** |
| Q4 | Scope: all modules; deep station physics **deferred**, a clean parameterised surrogate first so the pipeline works end-to-end. |

## Modules

| Module id | Responsibility | Depends on | Findings | Spec depth |
|---|---|---|---|---|
| `baseline-freeze` | Pin the audited snapshot (hash manifest + tag); retract unsupported "p < 0.001"; remove hard-coded secret fallback; "under audit" banner | — | E-07, M-08 | Few lines |
| `measurement-integrity` | NaN-not-zero for missing data; horizon-based throughput; exact time-average WIP; censored cycle time; validity flags; Holm; paired test; legacy-CSV adapter | `baseline-freeze` | E-02, E-03, E-08 | Full |
| `pemfc-physics-core` | Station 5 formulas: Tafel (α·n), roughness factor, j<j₀ domain, entropic heat + single phase convention, unit/area consistency, flooding-ODE units, Biot criterion, air-fed domain, cell-reversal flag, parameter registry | `baseline-freeze` | P-01…P-06, P-14, P-15, P-16, P-18 | Full |
| `pemfc-validation` ★ | Dataset fixtures + staged calibration protocol + held-out gates + identifiability report + negative control + global sensitivity | `pemfc-physics-core` | P-02 (identifiability), validation gap | Full |
| `station-surrogates` ★ | Re-scoped from `station-process-models`: stations emit a continuous `QualityState` through a parameterised, documented surrogate (monotone, bounded, seeded); sourced Station 1 margin | `baseline-freeze` | P-11, P-13, P-17 (surrogate-level) | Full |
| `quality-coupling` | Replace "PASS ⇔ defects = 0" with continuous mapping `QualityState → PEMFC parameters`; make `operating_temp_k` drive physics; computed `THERMAL_SHUTDOWN`; wire or delete dead physics; remove 6 s `sleep` | `pemfc-validation`, `station-surrogates` | P-07, P-08, P-09, P-10 | Full |
| `sim-determinism` | Diagnose dead runs; remove or prove inert the 10 ms wall-clock quorum; persist `droppedNerCount`; real replay tests (state hash per tick, same seed twice, one under CPU load) | `measurement-integrity` | E-01, M-05, M-06 | Full |
| `control-policy-semantics` | Policy abstraction + ablation arms (baseline, pause-only, deadlock-resolution on in all arms); 2PC → "barrier with timeout" (or atomic); MoISE enforced or removed; energy metric across stations/AMRs | `sim-determinism` | M-01…M-04, E-05 | Full |
| `adacor-mode-switching` ★ | Real ADACOR: per-operational-holon autonomy factor α, stationary (hierarchical-like) ↔ transient (heterarchical-like), disturbance propagation with decay, recovery timer/hysteresis | `control-policy-semantics` | M-01, M-03, D-03 | Full |
| `experiment-redesign` | One pre-registered question; interleaved/randomised arm order; warm-up; ≥30 replicas with power analysis; price-profile sweep; physics-on vs physics-off ablation | `measurement-integrity`, `adacor-mode-switching`, `quality-coupling` | E-04, E-01 (root cause) | Full |
| `claims-and-docs` | Reconcile README/site/`report.tex`/claim-matrix with code+results; real Zenodo DOI; `file:///` + `edit_uri`; terminology; related-work table; reference audit | `experiment-redesign` | D-01…D-05, E-06, M-07 | Full |

★ = new or re-scoped in this version.

**Deferred (no spec yet):** `station-process-models`, deep first-principles Stations 1–4 (depends on `station-surrogates`, `pemfc-validation`). Revisit after `experiment-redesign` shows whether upstream fidelity changes any decision.

## Build order

```
baseline-freeze
  ├─→ measurement-integrity ─→ sim-determinism ─→ control-policy-semantics ─→ adacor-mode-switching ─┐
  ├─→ pemfc-physics-core ─→ pemfc-validation ─┐                                                      │
  └─→ station-surrogates ─────────────────────┴─→ quality-coupling ──────────────────────────────────┤
                                                                                                     ↓
                                                              experiment-redesign ─→ claims-and-docs
```

Two parallel tracks after `baseline-freeze`: **control track** (measurement → determinism → policy → ADACOR) and **physics track** (core → validation, surrogates → coupling). They meet at `experiment-redesign`.

## Changes vs v1 (for your veto)

1. **Added `adacor-mode-switching`** (your Q2 choice).
2. **Re-scoped `station-process-models` → `station-surrogates`**; the original id is kept for the deferred deep-physics work.
3. ★ **My structural change: split `pemfc-validation` out of `pemfc-physics-core`.** The formula fixes are verifiable with analytic oracles; the dataset/calibration/identifiability work is a separately shippable cluster with its own consumer (`quality-coupling` takes its calibrated defaults). Keeping them in one spec would have mixed ~23 criteria. *Default: accepted. Say "keep merged" to revert.*
4. `quality-coupling` now depends on `pemfc-validation` (calibrated defaults), not directly on the core.

## Boundary contracts (owned by the provider module's spec)

| Provider → Consumer | Contract |
|---|---|
| `measurement-integrity` → all experiments | `results.csv` schema v2: `started`, `stalled`, `horizon_s`, `horizon_source`, `incomplete_count`, `dropped_ner`; missing = `NaN`, never `0` |
| `pemfc-physics-core` → `pemfc-validation`, `quality-coupling` | Python API of `calculate_pemfc_voltage(...)`; a parameter registry (value, unit, source, status ∈ measured/cited/fitted/assumed) |
| `station-surrogates` → `quality-coupling` | `QualityState` (continuous fields + units + valid ranges) in one YAML-configurable surrogate |
| `control-policy-semantics` → `adacor-mode-switching` | Policy interface + arm selection by config flag (no source mutation) |
| any module touching `BatchTestRequest` | `sim_bridge.proto` exists in 3 copies (`src/main/proto`, `physical_engine/protos`, `visualization`); a drift check is part of whichever module changes it |

## Cross-cutting constraints

- **CI** runs Python 3.10 and JDK 17: no 3.11+ features; Java changes must compile on 17.
- **I cannot run Gradle/JVM here** (wrapper cannot download its distribution). Java/ASL tasks ship with tests; you run `./gradlew test` and send output. Python tasks I verify myself.
- Existing tests are never weakened. Tests that encode a *proven-wrong* behaviour (e.g. the `z_pemfc == 4` guard) are replaced only with your explicit approval at the test checkpoint.

## Specs

| Module | File | Status |
|---|---|---|
| `baseline-freeze` | `SPEC-baseline-freeze.md` | Completed (verified by `tests/test_repo_hygiene.py`) |
| `measurement-integrity` | `SPEC-measurement-integrity.md` | Draft: awaiting review |
| `pemfc-physics-core` | `SPEC-pemfc-physics-core.md` | Draft: awaiting review |
| `pemfc-validation` | (after `pemfc-physics-core` approval; protocol drafted in `VALIDATION-DATASET-PICK.md`) | Not started |
| all others | in build order | Not started |
