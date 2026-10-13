# Matrix Factory Twin: Verification Ledger

Repo snapshot: `utczbr/Matrix_Factory` @ `main` (tarball downloaded 2026-10-08).
Method: read the source, then **executed the real functions** (numba 0.68 JIT path, real `SimBridgeServicer.RunBatchTest`, raw `results.csv`). Scripts are in `verify_scripts.tar.gz`.

Legend: ✅ confirmed by execution/code · ⚠️ confirmed but **corrected** vs the reviews · 🆕 new finding · ❓ not verifiable here

---

## 0. Headline

All the *scientific* problems raised by the two reviews are real. Three details in the reviews needed correction (§5), and I found four additional issues (🆕). The Python suite is **green (70 passed, 14 skipped)** while every physics defect below is present, so the current tests cannot detect any of them.

---

## 1. Physics: Station 5 PEMFC model

| ID | Finding | Evidence (reproduced) | Sev |
|---|---|---|---|
| P-01 ✅ | Tafel uses α·z = 0.5·4 = 2 → slope **35.0 mV/dec** (80 °C). Low-j ORR on Pt/C is ≈ 60–70 mV/dec (2.303RT/F = 70.1 mV at 353 K for α·n=1); high-j region ≈ 120–140. The `z_pemfc != 4 → raise` guard hard-codes the error. | `calculate_pemfc_voltage` at j=0.01 and 0.10 → Δη = 35.04 mV | High |
| P-02 ✅ | j₀ is per-cm²-Pt but multiplied only by `ecsa_ratio ≤ 1`; no roughness factor anywhere in the repo. Errors **partially cancel** (poor identifiability): η_act at 1 A/cm² is 266 mV (repo), 533 (slope fixed only), 196 (rf fixed only), **393** (both fixed, rf=100). Net bias −127 mV. | `verify_p2_and_deadcode.py`; grep for roughness = none | High |
| P-03 ✅ | Tafel unguarded for j < j₀: V_cell > OCV. At j=1e-10: η_act = −84 mV, V_cell = 1.266 V vs OCV 1.182 V. | `verify_physics.py` §P3 | Med |
| P-04 ✅ | Heat excludes entropic term. At 1 A/cm², V=0.790 V, R_tot=0.100 Ω·cm²: model Q = 0.367 W/cm²; true Q = 0.464 (vapour) / 0.691 (liquid) → **79% / 53%** coverage. Nernst base 1.229 V already implies liquid water, so 1.481 V is the consistent choice (53%). | `verify_physics.py` §P4 | High |
| P-05 ✅ | Flooding ODE: `(mol·m⁻²·s⁻¹)/0.35` returned as ds/dt. Gives 6.7 s to saturate vs ~167 s with a dimensionally-consistent (M_w/ρ_l/(ε·δ_GDL)) form (order of magnitude, assumptions stated in script). Also `j_lim_eff = 2.5·(1−derate)` ignores D_eff; ε=0.78 alone gives ratio 0.78, so nominal 2.5 is never "reached" by the doc's own formula. | `verify_physics.py` §P5–P6 | High |
| P-06 ✅ | Thermal units inconsistent. `AdvanceTime`: `Q = j·(η_act+η_ohm)` labelled "[Watts]" (no area, no N). Sweep: `Q = j·N·(η_act+η_ohm)` (no area). Sweep ΔT_core = **−0.085 K** over 12 points → electro-thermal coupling numerically nil. | `sim_bridge_server.py:252-254`, `pemfc_model.py:524`; executed RPC | High |
| P-14 ✅ | "Yonkist" Yo = qL²/(kΔT) matches the classical Pomerantsev-type group (naming unverified ❓). For uniform generation in a plate, ΔT_int/ΔT_surf = Bi/2 exactly (numeric identity checked), so "Yo < Bi removes the Bi bound" is unsound. ΔT input is the lumped model's own output (circular, floor 0.1 K), and failure only logs a warning. | numeric check; `sim_bridge_server.py:387-398` | Med |
| P-15 🆕 | `SimBridgeServicer.__init__` default `R_internal=0.1`; `serve()` default `0.06`. Silent divergence depending on entry point. | `sim_bridge_server.py:149, 501` | Low |
| P-16 🆕 | No cell-reversal guard. With 3 defects the stack voltage at the last sweep point is **−6.3 V** (100 cells) and the test still reports a plain `OHMIC` failure. | `verify_e2e_rpc.py` | Med |

---

## 2. Manufacturing → performance coupling & dead physics

| ID | Finding | Evidence | Sev |
|---|---|---|---|
| P-07 ✅ | **End-of-line PASS ⇔ defects = 0.** 0 defects → pass; 1–4 → `OHMIC`. Headroom before OHMIC trips is 0.043 Ω·cm² but one defect adds 0.080 (77% of baseline 0.1045). The Java source comment states the +0.08 was chosen *so that one defect fails the test*. Coefficients (+0.08 Ω·cm², derate 0.15/defect) have no source. Stations' continuous outputs are near-inert: R_contact(Station 4) = 4.0% of the ohmic budget and moves only 0.0042→0.0053 Ω·cm² across p_clamp 2–6 MPa / porosity 0.5–0.78. | `verify_e2e_rpc.py`, `verify_e2e_2.py` (real `RunBatchTest`, Java-equivalent requests); `TestBenchArtifact.java:108-126` | High |
| P-08 🆕 | `request.operating_temp_k` is **inert**: V[-1] = 52.0649 / 52.0653 / 52.0653 / 52.0655 V at 300 / 350 / 360 / 400 K (only via activity). `THERMAL_SHUTDOWN` is evaluated on the internal `T_core` state (init 353.15 K), not the request, so it never fires from the setpoint. (Stronger than Review 2's "threshold on the setpoint".) Also the thermal state **persists across stacks** (351.93 K after prior sweeps), so test outcomes depend on test order. | `verify_e2e_2.py` §b | High |
| P-09 ✅+🆕 | Dead in the pipeline: `step_liquid_saturation`, `effective_diffusivity`, `step_membrane_hydration`, `StackThermalModelND` have zero non-test callers. 🆕 Java sets only 5 request fields; `j_lim_derate_fraction` and `rh_anode` are **never set**, and `lambda_mem` isn't in the proto at all (server reads it with `getattr`, so λ=14 always). The proto comments promising "mass-transport derating" are unreachable. | grep; `proto` BatchTestRequest; Java setters list | High |
| P-10 ✅ | `time.sleep(0.5)` per sweep point = 6 s wall-clock per end-of-line test inside a lock-step "simulated time" system. | `sim_bridge_server.py:410` | Med |

---

## 3. Stations 1–4 and calibration

| ID | Finding | Evidence | Sev |
|---|---|---|---|
| P-11 ✅ | Calibration is circular: script header declares targets 0.20% (S3) / 0.80% (S4) and checks that author-chosen σ reproduces them. Sensitivity: S3 defect rate = **0.00% / 0.19% / 1.93%** at σ_F = 3% / 5% / 7%. Nominal S3 damage index = **0.864** (86% of failure). | `calibrate_stamping_clamping.py:1-12`; MC run | High |
| P-12 ✅ | `K_WEAR_PVD = 3.5e-6` vs `K_WEAR_DUPLEX = 1.47e-10` (ratio ≈ 23,800×); `(F/F_nom)^1.35` presented as an "Archard exponent" though Archard's law is linear in load. Unit/source audit needed. | `station3...py:30-32, 69` | Med |
| P-13 ⚠️ | Station 1 (Kamal–Sourour): α(160 °C,180 s)=0.894 ✅; α(155 °C)=0.849 → defect ✅; α(dwell 150 s)=0.857 ✅. **But the window is not that narrow**: at 180 s it spans 155.5–174.5 °C (19.5 K). The real issue is the nominal sits only 4.5 K / 30 s from the lower edge, so defect rate is set by the σ chosen. | `station1` sweep | Low |
| P-17 ✅ | `E2_CURE = 68.5e3 J/mol` is identical to ORR `E_act = 68500`. Possibly coincidence; confirm sources. | `station1:24`, `pemfc_model.py:200` | Low |

---

## 4. Experiment, statistics, MAS

| ID | Finding | Evidence | Sev |
|---|---|---|---|
| E-01 ✅ | **8/15 PROSA** runs completed ≤ 1 order (ids 0–4, 7, 12, 13); **2/15 ADACOR** (11, 14). PROSA runs 0–4: `submitted_count = 0` (= first batch of the first arm). Runs 7/12/13: 6 submitted, 1 completed. Dead ids are **disjoint across arms**, which argues against a seed-specific deadlock (hypothesis only). | `verify_stats.py` | High |
| E-02 ✅ | Metric code: empty runs → `throughput = tardiness = 0` (should be NaN). Throughput denominator = last event time, not horizon, so stuck runs 7/12/13 show 0.0128/0.0151/0.0150 (top of the arm). `wip_mean` = Σcycle/t over **completed** orders only (survivorship). "tardiness" = cycle time (no due date). | `run_prosa_vs_adacor.py:85-104` | High |
| E-03 ✅ | p = 0.0300 (zeros kept, 15 v 15) → **0.438** excluding ≤1-completion runs (7 v 13) → **0.056** with ≥20 completions (6 v 10). Holm/Bonferroni over 6 tests: **0.18**. Paired analysis (shared seeds) leaves only **5 of 15** pairs with data in both arms 🆕. | `verify_stats.py` | High |
| E-04 ✅ | Arms run strictly sequentially (PROSA first, batches of 5, DB deleted between). Cold-start/order is confounded with treatment. | `run_prosa_vs_adacor.py:134-160` | High |
| E-05 ✅ | `energy_cost_eur` ≈ 5.6e-6 vs 6.1e-6 € per run (p = 0.63): compressor-only, invisible. | CSV | Med |
| E-06 ✅ | `report.tex` totals "228 of 326" / "297 of 426" vs CSV sums 276/325 and 302/488. | CSV vs `report.tex:676-677` | Med |
| E-07 ✅ | Claim matrix line 15: "p < 0.001 (Mann-Whitney U)". Smallest p in all repo stats files = 0.030. | `claim-matrix.md:15` | High |
| M-01 ✅ | The "ADACOR" arm = drain (≤15 s) + suspend (≤10 s) + abort in-flight intentions on price spike, then same CNP. **No throttling/admission code exists** in any `.asl` or `.java`, yet `report.tex:769` narrates admission throttling as the mechanism. | grep over `src/` | High |
| M-02 ✅ | AMR deadlock resolution `+transport_blocked` requires `active_schema(prosa)` (`supervisor_agent.asl:196`), so it is **off** under ADACOR (confound). | `supervisor_agent.asl` | High |
| M-03 ✅ | `assign_tasks` appears 2× in `adacor_org.xml` but 0× in any plan; authority links not enforced at runtime; `active_schema` is read only in `supervisor_agent.asl`. | grep | Med |
| M-04 ✅ | Phase 0 TTL expiry → compensating abort (2PC-consistent); Phase 1 TTL expiry → `force_commit` decree (barrier with timeout, not atomic commit). | `supervisor_agent.asl:120-172` | Med |
| M-05 ✅ | Tick quorum = `CountDownLatch.await(10 ms wall-clock)` then "proceed anyway"; `droppedNerCount` increments but is **never written to DB or analysis**. | `MainSimulator.java:57, 298-301` | High |
| M-06 ✅ | "SeededReplay" tests assert `isShutdown()` + non-null AMR array + no JVM deadlock. Nothing compares two trajectories; "0 drift" untested. | `SeededReplaySeed1Test.java` | High |
| M-07 ❓ | "Digital twin" vs "digital model" under Kritzinger et al.: depends on source taxonomy; not checkable here. | n/a | Med |
| M-08 🆕 | Experiment runner hard-codes a fallback `TELEMETRY_HMAC_SECRET` literal. | `run_prosa_vs_adacor.py` (env setup) | Low |

---

## 5. Documentation

| ID | Finding | Evidence |
|---|---|---|
| D-01 ✅ | Zenodo DOI `10.5281/zenodo.1234567`, author "Matrix Factory Research Team", venue "IEEE TII, 2026" in `docs/index.md` and `docs/citation.md`. | grep |
| D-02 ✅ | 16 `file:///` links across 6 docs (`websocket-telemetry` 4, `station-5-pemfc` 4, `grpc-protobuf` 3, `amr-agents` 3, `security-mtls` 1, `supervisor-agent` 1). `mkdocs.yml` sets no `edit_uri`, so Material defaults to `/edit/master/`, but the branch is `main`. | grep |
| D-03 ✅ | PROSA/ADACOR labels contradict across files: `report.tex` & README: PROSA peer/heterarchical, ADACOR hierarchical. `architecture-overview.md`: hierarchical PROSA, heterarchical ADACOR. ADACOR's defining trait in the literature is *switching* between modes (❓ primary sources to confirm); the code implements neither a hierarchical dispatcher nor mode switching. | grep |
| D-04 ✅ | Spike threshold: code/report 150 €/MWh; docs 0.25 $/kWh (= 250 $/MWh). | `EnergyPriceArtifact.java`, `holonic-control.md` |
| D-05 ⚠️ | Test counts: README says 71 pytest / 18 Java classes. I count **87** `def test*` (Review 2 said 90) and **17** Java classes with `@Test`. | recount |

---

## 6. Corrections to the earlier reviews

1. **Review 2, "≥3 defects → OHMIC + LOW_ACT"**: only true at 1 bar inlet pressure. Under the Java default setpoints (2.0/2.0 bar) it is `OHMIC` only for 1–4 defects.
2. **Review 2, "THERMAL_SHUTDOWN is a threshold on the setpoint"**: the setpoint doesn't reach it at all (P-08).
3. **Review 1, "Station 1 window is narrow"**: 19.5 K wide; the nominal's *proximity to the lower edge* is the real issue (P-13).
4. **Review 2, "90 test functions"**: 87 by my count.
5. **Review 2 §3.6 / paired tests**: pairing helps in principle, but only 5/15 pairs are usable (E-03).

## 7. Not verified here (❓)

- Gradle/JVM test runs (JDK 21 present; Gradle wrapper cannot download its distribution: network allowlist). **Java-side tasks need to be run on your machine.**
- Literature items: Kleemann/Bitay/Fernandes DOIs, ADACOR/PROSA characterisation, Kritzinger taxonomy, SOHOMA'22, "Yonkist" naming.
- `report.tex` vs README parameter snapshot differences (j₀ = 1e-9 vs 2.5e-8, 2-node vs N-cell thermal, JUnit count): not re-checked.
- Root cause of the dead runs (cold start vs nondeterminism vs deadlock) is still a hypothesis.

## 8. Python baseline

`pytest physical_engine` (excluding `test_grpc_security.py`): **70 passed, 14 skipped** in 65 s. Green with all P-01…P-06 present.
