# Matrix Factory Twin: Consolidated Problem Register (rev. 4, re-verified against repo, test suites & code check)

Repo: `utczbr/Matrix_Factory` @ `main`.
- **Initial audited snapshot:** tarball of 2026-10-08 (no `.git` directory; file identity established by `need-to-fix/AUDIT-MANIFEST.sha256`).
- **Re-verified snapshot (2026-10-13):** `git archive` tarball of `main` at commit **`89c67320a0fcb97ba81acd7c8ac44000a54b23af`** (SHA-1 embedded in the archive root prefix and ZIP central-directory comment; see §0.2).
- **Sources:** Review 1 (docs-only), Review 2 (code read + numeric re-runs), the execution ledger `need-to-fix/VERIFICATION.md` and its scripts, rev. 2/3 re-runs, rev. 4 Gradle/JVM test executions, programmatic verification script `need-to-fix/verify_scripts/verify_unverified_items.py`, and full repository tree inspection.

---

## 0. How to read this document

### 0.1 Legend

| Mark | Meaning |
|---|---|
| ✅ | Confirmed by executing the real code or recomputing from the raw CSV |
| ⚠️ | Confirmed, but an earlier statement was corrected |
| 🆕 | New finding, not in the initial reviews or the ledger |
| 🔎 | Found by reading code/archive tree only (Java/ASL could not be executed); the mechanism is clear but the runtime effect is unmeasured |
| ❓ | Not verified |

**Severity:** **High** = invalidates a scientific claim or result; **Med** = distorts results or misleads readers; **Low** = hygiene or latent risk.
**Where numbers differ between sources**, the value reproduced in the latest verification wins.

### 0.2 What was re-verified (and what was not)

| Check | Result |
|---|---|
| `sha256sum -c AUDIT-MANIFEST.sha256` on commit `89c67320a0fcb97ba81acd7c8ac44000a54b23af` | 9 of 13 manifest files are byte-identical to the 2026-10-08 audit: `results.csv`, `results_stats.md`, `analyze_results.py`, `pemfc_model.py`, `sim_bridge_server.py`, `pemfc_test.py`, `MainSimulator.java`, `TestBenchArtifact.java`, `supervisor_agent.asl`. **4 differ:** `README.md`, `docs/index.md`, `claim-matrix.md`, `run_prosa_vs_adacor.py`. These are the exact files edited by `baseline-freeze` (banner, claim row, secret resolver), so all physics, Java, ASL, and analysis line numbers hold across both snapshots. |
| `verify_physics.py`, `verify_p2_and_deadcode.py`, `verify_e2e_rpc.py`, `verify_e2e_2.py`, `verify_stats.py` re-run on `main` (numba 0.68.0 JIT path) | Every ledger number reproduced (P-01…P-08, P-16, E-01, E-03, E-06). Two script outputs that the ledger had not recorded contradicted claims in rev. 1 (see P-07). |
| `need-to-fix/verify_scripts/verify_unverified_items.py` re-run on `main` (rev. 4) | Programmatically and empirically confirmed all previously unverified 🔎 and ❓ items (P-17, P-18, P-19, P-20, M-05, M-07, M-09, D-06, T-03). Resolved literature origins: "Yonkist" (Elijah Yoder et al., ASME 2025), Bitay et al. DOI (Hanwen et al. 2024 welding paper mismatch), and Fernandes et al. DOI (Motta et al. 2018 PVDF tensile paper mismatch). |
| Gradle / JVM test suite execution (`./gradlew test`) | Ran replay and integration tests. Identified that `RunCentralisedMAS.finish()` schedules an asynchronous `System.exit(0)`, terminating the Gradle worker JVM and causing subsequent `@Test` methods in multi-test classes (`InvariantTests`) to be skipped. Single-test classes (`SystemIntegrationV1Test`, `DatabaseArtifactTest`) pass cleanly. |
| Full archive tree & secondary CSV inspection (rev. 3) | Identified duplicated physics kernels in `physical_engine/optimization/` (§2), committed LUT `.pkl` files and stale `.lut_generation.lock` (T-03), uncounted test suites in `scripts/` (D-05, T-02), mismatched sample sizes across the 3 horizons (`results_360_10.csv`, `results_1440_5.csv`, `results.csv`; E-03, E-06), and the $23.0$ percentage-point completion gap masked by `report.tex` (E-06). |
| Cited line numbers re-checked by `grep`/`sed` | Confirmed except where noted per finding. |
| Hygiene test simulated on a scratch `git init` of the tarball | Found a self-matching bug (T-02) and uncovered files (`ONBOARDING*.md`, `prosa_vs_adacor.ipynb`, `report.tex`). |
| Three literature DOI / bibliographic resolutions | Kleemann DOI resolved (D-07); Bitay DOI resolved as mismatched welding paper; Fernandes DOI resolved as mismatched PVDF tensile paper; "Yonkist" origin resolved to Elijah Yoder et al. (ASME 2025). |
| **Not done** | Deep inspection of Stations 2 and 4 or AMR pathfinding internals; verifying the git tag `audit-baseline-2026-10` (absent in a `git archive` export). |

### 0.3 Remediation status on current `main`

`baseline-freeze` has been partially applied on `main` (`89c67320a0fcb97ba81acd7c8ac44000a54b23af`):
- `README.md` and `docs/index.md` carry a `"RESULTS UNDER AUDIT"` banner (though `ONBOARDING.md` and `ONBOARDING_pt-BR.md` do not).
- The `docs/artifact-evaluation/claim-matrix.md` §5.1 row now states *under revision*, uncorrected $p = 0.030$, $n = 15\text{ v }15$ (though `report.tex:767` still claims statistical significance).
- `resolve_telemetry_secret()` replaced the hardcoded literal in `experiments/run_prosa_vs_adacor.py` (though the literal still appears 3 times in `tests/test_repo_hygiene.py` and `need-to-fix/SPEC-baseline-freeze.md`, causing the hygiene test to fail on a git checkout; see **M-08** and **T-02**).
- Nothing else in this register has been remediated yet.

**Headline.** The systems engineering is solid (lock-step gRPC co-simulation structure, 30-sim fan-out in one JVM via namespace rewriting, CI pipeline, authenticated WebSocket telemetry). The problems are scientific and methodological: the primary experiment does not support its conclusions, the `"ADACOR"` arm is not ADACOR, a $6\text{ s}$ wall-clock sleep inside the physics RPC collides with a $10\text{ ms}$ tick quorum barrier, the physics engine contains formula and unit errors that partially cancel, and the manufacturing-to-performance coupling acts primarily as a discrete defect counter. The Python test suite is green ($70$ passed, $14$ skipped in the audit baseline) with every physics defect present.

---

## 1. Summary table

*Note: Finding IDs (`P-*`, `E-*`, `M-*`, `D-*`, `T-*`) are numbered chronologically by discovery and grouped by subsystem in §2–§8.*

| ID | Area | Finding (short) | Sev | Status | On current `main` |
|---|---|---|---|---|---|
| P-01 | Physics | Tafel uses $\alpha \cdot z = 2 \to 35\text{ mV/dec}$ (duplicated across `pemfc_model.py` and `optimization/`) | High | ✅ | open |
| P-02 | Physics | $j_0$ per $\text{cm}^2\text{-Pt}$, no roughness factor; errors cancel partially with P-01 | High | ✅ | open |
| P-03 | Physics | Tafel unguarded for $j < j_0 \to V_{\text{cell}} > \text{OCV}$ | Med | ✅ | open |
| P-04 | Physics | Heat omits entropic term; $53\%\text{--}79\%$ coverage | High | ✅ | open (docs admit omission) |
| P-05 | Physics | Flooding ODE dimensionally inconsistent; $j_{\text{lim}}$ ignores $D_{\text{eff}}$ | High | ✅ | open |
| P-06 | Physics | Thermal units omit cell area $A_{\text{cell}}$; stack cools by $-0.085\text{ K}$ under load | High | ✅ | open |
| P-07 | Coupling | End-of-line PASS $\iff \text{defects} = 0$ at realistic inputs; coefficients unsourced | High | ✅ | open |
| P-08 | Coupling | `operating_temp_k` inert; `THERMAL_SHUTDOWN` unreachable; $T_{\text{core}}$ persists across stacks | High | 🆕 | open |
| P-09 | Coupling | Dead physics functions; `rh_anode`, `j_lim_derate_fraction` unset; `lambda_mem` not in proto | High | ✅+🆕 | open |
| P-10 | Coupling | `time.sleep(0.5)` per sweep point ($6\text{ s}$ wall-clock per test, breaking $10\text{ ms}$ tick quorum) | High | ✅ | open |
| P-11 | Stations | Calibration is circular (fit to self-chosen targets and $\sigma$) | High | ✅ | open |
| P-12 | Stations | `K_WEAR` ratio $\approx 23{,}800\times$; "Archard exponent" $1.35$ is not Archard | Med | ✅ | open |
| P-13 | Stations | Station 1 nominal sits $4.5\text{ K}$ / $30\text{ s}$ from the lower cure-window edge | Low | ⚠️ | open |
| P-14 | Physics | "Yonkist" criterion unsound, circular, and uncited | Med | ✅ | open |
| P-15 | Physics | Default `R_internal` diverges ($0.1$ vs. $0.06\ \Omega\cdot\text{cm}^2$) by entry point | Low | 🆕 | open |
| P-16 | Physics | No cell-reversal guard; $-6.3\text{ V}$ ($3$ defects) reported as plain `OHMIC` | Med | 🆕 | open |
| P-17 | Stations | Station 1 `E2_CURE` $=$ Station 5 ORR $E_{\text{act}} = 68.5\text{ kJ/mol}$; Motta DOI mismatch | Low | ✅ | open |
| P-18 | Physics | Springer isotherm at $30\ ^\circ\text{C}$ used at $80\ ^\circ\text{C}$; "hysteresis" mislabel; $\tau$ undocumented; dead code | Med | ✅ | open |
| P-19 | Coupling | Quality-fetch failure silently defaults to a perfect stack; comment/code mismatch | Med | ✅+🆕 | open |
| P-20 | Stations | Time-scale mismatch: $180\text{ s}$ physical dwell vs. $t_{\text{base}} = 5\text{ s}$ station step and price clock | Med | ✅ | open |
| E-01 | Experiment | $8/15$ PROSA and $2/15$ ADACOR runs produced $\le 1$ completion (two distinct failure modes) | High | ✅ | open |
| E-02 | Metrics | Zero-fill, wrong denominator, survivorship WIP, bare `except:`, "tardiness" $=$ cycle time | High | ✅ | open |
| E-03 | Statistics | $p = 0.030$ collapses to $0.438$ / $0.056$ / $0.18$ (Holm); unequal $n$ ($10, 5, 15$); $5/15$ usable pairs | High | ✅ | open |
| E-04 | Design | Arms run sequentially; order/cold start confounded with treatment | High | ✅ | open |
| E-05 | Metrics | Energy metric $\approx 6 \times 10^{-6}\text{ EUR/run}$ ($\sim 8\text{ J/stack}$) and $\approx$ completion counter ($\rho = 0.98$) | Med | ✅ | open |
| E-06 | Reporting | `report.tex` totals do not match CSV and hide a $23.0$ percentage-point completion gap | High | ✅ | open |
| E-07 | Reporting | Claim matrix said $p < 0.001$; `report.tex:767` still claims statistical significance | High | ✅ | matrix fixed; `report.tex` open |
| E-08 | Design | Experiment does not exercise the physics ($\sim 1$ defect per $300$ orders) | High | ✅ | open |
| M-01 | MAS | "ADACOR" arm $=$ drain+suspend+abort; no admission throttling code exists | High | ✅ | open |
| M-02 | MAS | AMR deadlock resolution is disabled under ADACOR (confound) | High | ✅ | open |
| M-03 | MAS | MoISE `assign_tasks` never implemented; authority links unenforced | Med | ✅ | open |
| M-04 | MAS | "2PC": Phase 1 timeout $\to$ `force_commit` decree (atomicity abandoned) | Med | ✅ | open |
| M-05 | Determinism | $10\text{ ms}$ wall-clock quorum + agent roster regex bug + $30\text{ s}$ RPC timeout; drops not in DB | High | ✅+🆕 | open |
| M-06 | Testing | Replay tests check liveness only (`isShutdown()`); "0 drift" untested | High | ✅ | open |
| M-07 | Terminology | "Digital twin" vs. "digital model" (no physical asset data flow) | Med | ✅ | open |
| M-08 | Security | Hardcoded fallback HMAC secret | Low | 🆕 | fixed in runner; left in test/spec (T-02) |
| M-09 | MAS/Test bench | Infrastructure timeouts/errors recorded as physical defects; cancel path sets `IDLE` ("ok") | Med | ✅+🆕 | open |
| D-01 | Docs | Placeholder Zenodo DOI `10.5281/zenodo.1234567`, generic author, IEEE TII venue | High | ✅ | open |
| D-02 | Docs | 16 `file:///` links across 6 docs; no `edit_uri` in `mkdocs.yml` (defaults to `master`) | Med | ✅ | open |
| D-03 | Docs | PROSA/ADACOR hierarchy labels (earlier audit note) | Low | ⚠️ | consistent on `main`; see M-01 |
| D-04 | Docs | Price units inconsistent ($\text{EUR/MWh}$ in code/docs vs. $\text{\$/kWh}$ in bidding doc) | Med | ⚠️ | open |
| D-05 | Docs | README test counts wrong ($71$ / $18$ vs. $90$ in `physical_engine/` + $2$ in `scripts/`, $17$ `@Test` + $3$ helpers) | Low | ⚠️ | open |
| D-06 | Docs | `report.tex` vs. README snapshot drift (7 points confirmed); claim matrix cites absent manuscript items | Med | ✅ | open |
| D-07 | Refs | Kleemann DOI wrong in `literature-calibration.md`; Bitay 2021 vs. `024` DOI; uncited ASME 2025 | Med | ⚠️ | open |
| T-01 | Tests | Green suite hides every defect; $14$ skips and excluded `test_grpc_security.py` unexplained | High | ✅ | open |
| T-02 | Tests | Hygiene test self-matches secret literal and fails on git checkout; `tests/` and `scripts/` not in CI | Med | 🆕 | open |
| T-03 | Hygiene | Committed `.lut_generation.lock`, $9$ legacy `.pkl` files, `stacked_luts_v2.npz`, and generated `factory.jcm` | Low | ✅+🆕 | open |

---

## 2. Physics: Station 5 PEMFC model

**Primary files:**
- `physical_engine/factory_simulation/pemfc_model.py`
- `physical_engine/sim_bridge_server.py`
- `physical_engine/factory_simulation/membrane_hydration.py`
- `physical_engine/factory_simulation/stack_thermal_model.py`
- **Duplicated kernel implementations (`🆕` critical for remediation):**
  - `physical_engine/optimization/numba_ops.py`
  - `physical_engine/optimization/_numba_ops_core_python.py`
  - `physical_engine/optimization/_numba_ops_core.pyx` (Cython extension)
  - `physical_engine/optimization/parity_test.py` and `test_numba_ops.py`

> **Remediation warning on kernel duplication:** `pemfc_model.py` delegates sweep and step calculations to the Numba/fallback kernels in `physical_engine/optimization/`, and `parity_test.py` asserts numerical equivalence across them. Any fix to **P-01…P-06** or **P-16** must be applied across `pemfc_model.py`, `numba_ops.py`, and `_numba_ops_core_python.py`, and must either update or remove `_numba_ops_core.pyx`.

### P-01 ✅ Tafel slope uses $\alpha \cdot z = 2$ ($35\text{ mV/dec}$)
- **Location:** `pemfc_model.py:131` (`z_pemfc = 4`), assertion guard at `:142-145`, `z = 4` hardcoded in `calculate_pemfc_voltage` (`:314`), plus the matching kernel implementations in `physical_engine/optimization/`.
- **Finding:** Activation overpotential is computed as $\eta_{\text{act}} = \frac{RT}{\alpha z F}\ln(j/j_0)$ with $\alpha = 0.5$ and $z = 4$, giving $\alpha z = 2$. In electrode kinetics, the Tafel denominator uses the effective charge-transfer coefficient $\alpha_c n_\alpha$ of the rate-determining step ($\approx 0.5\text{--}1.0$ for $\text{Pt/C}$ ORR), not the $4\text{ e}^-$ overall stoichiometry.
- **Evidence (re-run):** `verify_physics.py` §P1: $\Delta\eta_{\text{act}}$ per decade $= \mathbf{35.04\text{ mV/dec}}$ at $353.15\text{ K}$. Analytic $\alpha n_\alpha = 1$ gives $70.08\text{ mV/dec}$; typical $\text{Pt/C}$ ORR is $\approx 60\text{--}70\text{ mV/dec}$.
- **Corroboration on real data:** The validation prototype in `need-to-fix/VALIDATION-DATASET-PICK.md` fits the EH-31 polarization curves with the repo's kinetics as-is only by pushing parameters to their bounds ($\text{ECSA} = 0.05$, $j_{\text{lim}} = 6.0\text{ A/cm}^2$): held-out $2.5\text{ bar}$ RMSE is **$25.6\text{ mV}$** (max $48.6\text{ mV}$) vs. **$9.1\text{ mV}$** (max $17.6\text{ mV}$) with $\alpha n_\alpha = 1$ and a fitted roughness factor.
- **Fix:** Parameterize $\alpha_c$ (default $1.0$) in the parameter registry; remove the `z_pemfc == 4` guard; update all kernels in `physical_engine/optimization/` and replace the test that encodes the guard (with explicit approval).

### P-02 ✅ $j_0$ per $\text{cm}^2\text{-Pt}$, no roughness factor (error cancellation with P-01)
- **Location:** `pemfc_model.py:196-211` (`_effective_j0`), `:315`/`:362` ($j_{0,\text{ref}} = 2.5 \times 10^{-8}\text{ A/cm}^2$, `ecsa_ratio` $\le 1$); no roughness factor $r_f$ ($A_{\text{Pt}}/A_{\text{geo}} \approx 100\text{--}500\text{ cm}^2_{\text{Pt}}/\text{cm}^2_{\text{geo}}$) anywhere in the repo.
- **Evidence (re-run):** $\eta_{\text{act}}$ at $1\text{ A/cm}^2$:
  - Repo as-is ($\alpha z = 2$, $r_f = 1$): **$266\text{ mV}$**
  - Slope fixed only ($\alpha n_\alpha = 1$, $r_f = 1$): **$533\text{ mV}$**
  - Roughness added only ($\alpha z = 2$, $r_f = 100$): **$196\text{ mV}$**
  - Both fixed ($\alpha n_\alpha = 1$, $r_f = 100$): **$393\text{ mV}$**
  - Net bias is $\approx \mathbf{-127\text{ mV}}$; the two errors partially cancel so that a plausible-looking voltage curve arises from two incorrect physical terms.
- **Identifiability:** In the EH-31 prototype, $\alpha n_\alpha = 0.85$ with $r_f = 2149$ fits nearly as well as $\alpha n_\alpha = 1.0$ with $r_f = 426$; only a physical prior/bound on $r_f$ discriminates (V-8 gate).

### P-03 ✅ Tafel unguarded for $j < j_0$
- **Evidence (re-run):** At $j = 10^{-10}\text{ A/cm}^2$, $\eta_{\text{act}} = -84.0\text{ mV}$ and $V_{\text{cell}} = 1.2663\text{ V}$ vs. $\text{OCV} = 1.1823\text{ V}$; $V_{\text{cell}} > \text{OCV}$ also occurs at $10^{-9}$ and $10^{-8}\text{ A/cm}^2$ ($j_0 = 2.5 \times 10^{-8}\text{ A/cm}^2$).
- **Fix:** Use a symmetric/asinh Butler–Volmer activation expression $\frac{RT}{\alpha F}\operatorname{arcsinh}\!\left(\frac{j}{2 j_0}\right)$ or clamp $\max(0, \eta_{\text{act}})$.

### P-04 ✅ Heat generation omits the entropic term ($53\%\text{--}79\%$ coverage)
- **Location:** `sim_bridge_server.py:252-254` (`AdvanceTime`), `pemfc_model.py:524` (sweep), and optimization kernels.
- **Finding:** $Q_{\text{gen}}$ is computed from $j \cdot (\eta_{\text{act}} + \eta_{\text{ohm}})$, omitting both concentration overpotential $\eta_{\text{conc}}$ and the reversible entropic heat $-T\Delta S/(nF)$ (i.e., $E_{\text{tn}} - E_{\text{Nernst}}$).
- **Evidence (re-run):** At $1\text{ A/cm}^2$, $V_{\text{cell}} = 0.7901\text{ V}$, $R_{\text{tot}} = 0.1003\ \Omega\cdot\text{cm}^2$ (excluding Station 4 contact resistance; cf. $0.1045\ \Omega\cdot\text{cm}^2$ in P-07):
  - Model heat flux: $q_{\text{model}} = 0.367\text{ W/cm}^2$ (adding $\eta_{\text{conc}}$ raises this only to $0.392\text{ W/cm}^2$).
  - True heat flux $j(E_{\text{tn}} - V_{\text{cell}})$: **$0.464\text{ W/cm}^2$** (LHV/vapour, $E_{\text{tn}} = 1.254\text{ V}$) or **$0.691\text{ W/cm}^2$** (HHV/liquid, $E_{\text{tn}} = 1.481\text{ V}$).
  - Coverage is **$79\%$ (vapour) / $53\%$ (liquid)**, underestimating heat generation by **$21\%$ to $47\%$**.
- **Docs admit it:** `docs/physical-engine/literature-calibration.md:33` lists `E_ENTROPIC = 0.23 V` as *"Defined, omitted from Q_gen"*.
- **Phase convention:** The Nernst reference potential $1.229\text{ V}$ assumes liquid product water, so $E_{\text{tn}} = 1.481\text{ V}$ ($53\%$ coverage) is the thermodynamically consistent choice.

### P-05 ✅ Flooding ODE dimensionally inconsistent; $j_{\text{lim}}$ ignores $D_{\text{eff}}$
- **Location:** `pemfc_model.py:215` (`GDL_SATURATION_CAPACITY = 0.35`), `:234` (`ds_dt = (water_production - water_removal) / GDL_SATURATION_CAPACITY`); `sim_bridge_server.py:336` (`j_lim_effective = max(0.2, 2.5 * (1 - j_lim_derate))`).
- **Evidence (re-run):** At $j = 1\text{ A/cm}^2$, molar water production is $\dot{n}_{\text{H}_2\text{O}} = 0.0518\text{ mol}/(\text{m}^2\cdot\text{s})$. Dividing directly by dimensionless $0.35$ yields $0.148\text{ mol}/(\text{m}^2\cdot\text{s})$ treated as $\text{s}^{-1}$, saturating the GDL in **$6.7\text{ s}$**. Converting molar flux to liquid volume fraction via $\frac{M_w}{\rho_l \varepsilon \delta_{\text{GDL}}}$ gives $5.99 \times 10^{-3}\text{ s}^{-1}$ ($\sim \mathbf{167\text{ s}}$ to saturate if all product water condensed).
- **Also:** `effective_diffusivity` at nominal $\varepsilon = 0.78, s = 0$ returns $0.78 D_0$, so the documentation's formula would give $j_{\text{lim}} \approx 1.95\text{ A/cm}^2$, not $2.5\text{ A/cm}^2$; and $D_{\text{eff}} = D_0 \varepsilon (1-s)^{1.5}$ mixes a linear factor in $\varepsilon$ with a Bruggeman exponent in $s$.

### P-06 ✅ Thermal units omit active cell area $A_{\text{cell}}$; stack cools down under load
- **Location:** `sim_bridge_server.py:251-254` (`Q_gen = I_total * (eta_act + eta_ohm)` labelled `[Watts]`, where `I_total` is current density $j$, omitting both cell area $A_{\text{cell}}$ and $N_{\text{cells}}$), and `pemfc_model.py:524` (`Q_gen = (j * N_cells) * (eta_act + eta_ohm)`, still omitting $A_{\text{cell}}$).
- **Evidence (re-run):** Across the 12-point polarization sweep up to $j_{\max} = 2.375\text{ A/cm}^2$, core temperature changes by $\Delta T_{\text{core}} = \mathbf{-0.0847\text{ K}}$ ($351.9273 \to 351.8427\text{ K}$).
- **Causal link across P-04, P-06, and P-08 (`🆕`):** Because `pemfc_model.py:524` omits active cell area $A_{\text{cell}}$ ($\sim 100\text{--}300\text{ cm}^2$) and entropic heat (**P-04**), stack heat generation in Watts is underestimated by **two to three orders of magnitude**. Consequently, Newton cooling to ambient exceeds $Q_{\text{gen}}$ even at maximum current density, causing the stack to **cool down during a load sweep** and making a genuine `THERMAL_SHUTDOWN` ($T_{\text{core}} > 358.15\text{ K}$, **P-08**) physically unreachable.
- **Discrepancy between tick and sweep paths:** The tick path (`AdvanceTime`) and batch sweep path (`RunBatchTest`) also differ by a factor of $N_{\text{cells}}$, and cell count itself differs between the servicer default (`self._num_cells = 200`) and the Java batch request (`request.num_cells = 100`, `sim_bridge_server.py:304`).

### P-14 ✅ "Yonkist" criterion unsound, circular, and uncited
- **Location:** `sim_bridge_server.py:385-398`; `stack_thermal_model.py`; `docs/physical-engine/literature-calibration.md:32` (`DELTA_T_YONKIST = 15 K`, cited only as *"ASME 2025"* with no bibliographic entry).
- **Finding:** $\text{Yo} = \frac{q L^2}{k \Delta T}$ is a Pomerantsev/Damköhler-type internal heat generation group (origin identified in Elijah **Yo**der, Wayne Strasser, Robert Kacinski, and Braden Jones, *"Unrestraining the Biot Number for Systems With Internal Heat Generation"*, ASME *Journal of Solar Energy Engineering*, 2025; "Yonkist" is an informal eponymous label derived from first author Elijah Yoder). For uniform heat generation in a slab of half-thickness $L$, the ratio of internal temperature rise to surface-to-coolant drop is identically $\frac{\Delta T_{\text{int}}}{\Delta T_{\text{surf}}} = \frac{\text{Bi}}{2}$, so the claim that $\text{Yo} < \text{Bi}$ removes the Biot requirement for lumped capacitance is physically unsound. Moreover, $\Delta T$ in the denominator is read from the lumped model's own output (circular, floored at $0.1\text{ K}$), and a violation only logs a warning (`:396-397`).

### P-15 🆕 Divergent default `R_internal` by entry point
- **Location:** `sim_bridge_server.py:149` (`SimulationBridgeServicer.__init__`, default `0.1` $\Omega\cdot\text{cm}^2$) vs. `:501` (`serve()`, default `0.06` $\Omega\cdot\text{cm}^2$).
- **Finding:** Simulation results depend on how the server is instantiated. Neither $0.1$ nor $0.06\ \Omega\cdot\text{cm}^2$ has a literature source, yet $R_{\text{internal},0}$ accounts for $57\%$ of the baseline ohmic resistance ($0.06 / 0.1045\ \Omega\cdot\text{cm}^2$).

### P-16 🆕 No cell-reversal guard
- **Evidence (re-run):** In `RunBatchTest` for a 100-cell stack at high current density ($j = 2.375\text{ A/cm}^2$), $3$ defects yield $V_{\text{stack}} = \mathbf{-6.31\text{ V}}$ and $4$ defects yield $\mathbf{-26.03\text{ V}}$, both flagged only as `OHMIC` with no cell-reversal flag or voltage clamp.

### P-18 ✅ Hydration isotherm temperature, "hysteresis" misnomer, and dead code
- **Location:** `physical_engine/factory_simulation/membrane_hydration.py:53-82`; `docs/physical-engine/station-5-pemfc.md`; `docs/physical-engine/literature-calibration.md`.
- **Finding (code check & execution):**
  1. **Isotherm temperature mismatch:** The Springer et al. (1991) sorption isotherm polynomial measured at $30\ ^\circ\text{C}$ is evaluated directly at $80\ ^\circ\text{C}$ ($353.15\text{ K}$) without temperature dependence (`:53-65`), predicting $\lambda_{\text{eq}} \approx 13.9$ at $a = 1.0$, whereas at $80\ ^\circ\text{C}$ Nafion equilibrium vapor uptake drops to $\sim 9\text{--}11$ (Hinatsu et al. 1994).
  2. **"Hysteresis" misnomer:** Lines 68–82 implement an asymmetric first-order relaxation ODE $\frac{d\lambda}{dt} = (\lambda_{\text{eq}} - \lambda)/\tau$ ($\tau_{\text{abs}} = 12\text{ s}$, $\tau_{\text{des}} = 45\text{ s}$). Because $\lambda_{\text{eq}}(a)$ is a single-valued algebraic curve, this represents kinetic rate asymmetry, not equilibrium sorption hysteresis (which requires a multi-valued path-dependent isotherm loop in $(a, \lambda)$ space).
  3. **Documentation gaps:** Time constants $\tau_{\text{abs}}$ and $\tau_{\text{des}}$ are omitted from the master calibration table, and air-fed cathode stoichiometry assumptions are unstated.
  4. **Dead code:** `step_membrane_hydration` has **zero non-test callers** anywhere in the runtime pipeline (`sim_bridge_server.py` never invokes it; `RunBatchTest` uses a static $\lambda = 14.0$).

---

## 3. Manufacturing $\to$ performance coupling and dead physics

**Files:**
- `src/main/java/factory/TestBenchArtifact.java`
- `physical_engine/sim_bridge_server.py`
- `sim_bridge.proto` (3 copies: `physical_engine/protos/sim_bridge.proto`, `src/main/proto/sim_bridge.proto`, `visualization/sim_bridge.proto` — currently byte-identical, MD5 `62467d7b…`)
- `scripts/check_proto_sync.py`, `physical_engine/proto_index.py`, `src/main/java/factory/ProtoIndex.java`, and `visualization/dashboard.js`

> **Proto sync infrastructure note (`🆕`):** The repository already includes `scripts/check_proto_sync.py` as well as index mappings (`proto_index.py`, `ProtoIndex.java`) and committed generated Python stubs (`sim_bridge_pb2.py`, `sim_bridge_pb2_grpc.py`). Any remediation touching `sim_bridge.proto` must update all 3 `.proto` files, regenerate the Python/Java stubs, update `ProtoIndex` / `visualization/dashboard.js` if telemetry indices shift, and wire `scripts/check_proto_sync.py` into `.github/workflows/ci.yml`.

### P-07 ✅ End-of-line PASS $\iff \text{defects} = 0$ across realistic inputs
- **Location:** `TestBenchArtifact.java:108-126` (`rInternalPenalty += defectCount * 0.08` at `:114`; `activityDerate = Math.min(0.6, defectCount * 0.15)` at `:126`).
- **Finding:** $0$ defects $\to$ PASS; $\ge 1$ defect $\to$ FAIL (`OHMIC`). The Java comment explicitly notes that $+0.08\ \Omega\cdot\text{cm}^2$ is *"enough on its own"* to push a stack over the $0.35\text{ V}$ ohmic-drop limit. Neither $+0.08\ \Omega\cdot\text{cm}^2$ nor $0.15$ activity derate per defect has an empirical source, and a single defect adds $133\%$ of the baseline $R_{\text{internal},0}$ ($0.06\ \Omega\cdot\text{cm}^2$).
- **Evidence (re-run, `RunBatchTest` with Java-equivalent 100-cell requests at $2\text{ bar}$):**

| Defects | Passed | Failure flags | $V_{\text{stack}} @ j[0]$ ($\text{V}$) | $V_{\text{stack}} @ j[-1]$ ($\text{V}$) |
|---|---|---|---|---|
| $0$ | `True` | none | $97.11$ | $52.07$ |
| $1$ | `False` | `OHMIC` | $96.34$ | $32.69$ |
| $2$ | `False` | `OHMIC` | $95.50$ | $13.25$ |
| $3$ | `False` | `OHMIC` | $94.55$ | $-6.31$ |
| $4$ | `False` | `OHMIC` | $93.43$ | $-26.03$ |

- **Ohmic budget:** Baseline total resistance is $R_{\text{tot}} = 0.06 + R_{\text{mem}}(\lambda = 14)\ 0.0403 + R_{\text{contact}}\ 0.0042 = \mathbf{0.1045\ \Omega\cdot\text{cm}^2}$. `OHMIC` trips when $j \cdot R_{\text{tot}} > 0.35\text{ V}$ at $j_{\max} = 2.375\text{ A/cm}^2 \implies R_{\text{crit}} = \mathbf{0.1474\ \Omega\cdot\text{cm}^2}$. The headroom is **$0.0429\ \Omega\cdot\text{cm}^2$**, whereas $1$ defect adds **$0.0800\ \Omega\cdot\text{cm}^2$**. Station 4 contact resistance represents only **$4.0\%$** of the baseline budget and varies only from $0.0042 \to 0.0053\ \Omega\cdot\text{cm}^2$ across $p_{\text{clamp}} \in [2, 6]\text{ MPa}$ and porosity $\varepsilon \in [0.5, 0.78]$.
- **Continuous channels (clarification from rev. 2):** Continuous parameters *are* wired, but only flip the pass/fail verdict at extreme values:
  - `cumulativeVarianceRatio` ($0$ defects, $4$ stations): `var_ratio` $\in \{0, 1, 5\}$ passes; **`var_ratio = 20` fails (`OHMIC`)** (threshold $\approx 8.6$, since $0.02 \cdot \text{vr}/4 > 0.0429$).
  - `ecsa_ratio` ($0$ defects): $0.9$ and $0.5$ pass; **$0.25$ fails (`LOW_ACT`)**.
  - `p_clamp_mpa` ($3.0\text{ MPa}$, $6.0\text{ MPa}$) and `gdl_porosity` ($0.6$): always pass, shifting $V_{\text{last}}$ by $< 0.2\text{ V}$.
- **Also:** $R_{\text{GDL}}$ and Station 2 micro-crack density are computed/defined in upstream docs/models but not wired into the end-of-line penalty.

### P-08 🆕 `operating_temp_k` is inert; `THERMAL_SHUTDOWN` never reads it; $T_{\text{core}}$ persists across stacks
- **Location:** `sim_bridge_server.py:303` (`T = request.operating_temp_k or 353.15`, used only for initial gas partial pressures), `:364` (`T_init = self._thermal.T_core`), `:382` (`self._thermal.T_core = T_core_arr[-1]`).
- **Evidence (re-run):** Sending `operating_temp_k` $= 300, 350, 360, 400\text{ K}$ yields $V[-1] = 52.0649, 52.0653, 52.0653, 52.0655\text{ V}$; no `THERMAL_SHUTDOWN` flag fires even at $360$ or $400\text{ K}$ (threshold is $358.15\text{ K}$), because the kernel uses `self._thermal.T_core` instead of `request.operating_temp_k` and `T_core` cools down during the sweep (see **P-06**).
- **Cross-stack state contamination & race condition:** `self._thermal.T_core` is mutated in-place and never reset between `RunBatchTest` calls, so each stack inherits the ending temperature of the previous stack. Furthermore, `RunBatchTest` reads and writes `self._thermal.T_core` (`:364`, `:382`) **outside** `self._physics_step_lock` (which `AdvanceTime` holds at `:219`), creating a data race with the tick thread.

### P-09 ✅+🆕 Dead physics functions and unpopulated Protobuf fields
- **Zero non-test callers in the runtime pipeline:** `step_liquid_saturation`, `effective_diffusivity`, `step_membrane_hydration`, and `StackThermalModelND`.
- **Standalone / partially coupled modules (`🆕`):** `h2_tank.py`, `cathode_air_bop.py`, and `microstructure.py` exist in `physical_engine/factory_simulation/`; while compressor power is queried for telemetry, cathode air BoP / $\text{H}_2$ tank depletion and microstructure tortuosity are not closed-loop coupled into the `RunBatchTest` polarization sweep.
- **Protobuf field audit:** `TestBenchArtifact.java:~150-160` sets **10 fields** on `BatchTestRequest`: `stack_id`, `num_cells`, `operating_temp_k`, `anode_pressure_bar`, `cathode_pressure_bar`, `r_internal_penalty`, `activity_derate_fraction`, `ecsa_ratio`, `p_clamp_mpa`, and `gdl_porosity`.
  - **Never set by Java:** `rh_anode` (field 9), `j_lim_derate_fraction` (field 13), `current_densities` (field 6, optional).
  - **Not in `sim_bridge.proto` at all:** `lambda_mem` (`sim_bridge_server.py:359` reads `getattr(request, 'lambda_mem', 14.0)`, so $\lambda = 14.0$ is constant in every batch test).
  - **Doc/code mismatch:** The docs state that $j_{\text{lim,eff}}$ scales with $D_{\text{eff}}/D_0$; the server actually computes `2.5 * (1.0 - j_lim_derate)` (`:335-336`), where `j_lim_derate` is always $0.0$.

### P-10 ✅ `time.sleep(0.5)` per sweep point ($6\text{ s}$ wall-clock delay per test)
- **Location:** `sim_bridge_server.py:410`.
- **Finding:** `RunBatchTest` executes `time.sleep(0.5)` on each of the 12 current-density points, blocking the gRPC worker thread and the calling Java agent for **$6.0\text{ s}$ of wall-clock time** per stack test. See **M-05** for how this $6{,}000\text{ ms}$ wall-clock sleep collides with the $10\text{ ms}$ tick quorum barrier.

### P-19 ✅+🆕 Silent fallback to a "perfect stack" on database errors
- **Location:** `TestBenchArtifact.java:127-148` (`catch` at `:127-130` sets penalties to `0.0`; `catch` at `:146-148` defaults to nominal $\text{ECSA} = 1.0$, $p_{\text{clamp}} = 4.25\text{ MPa}$, $\varepsilon = 0.78$).
- **Finding (code check & execution):**
  1. **Fail-open masking of defects:** Any SQLite read exception or missing record silently converts a defective stack into a pristine stack with zero penalties.
  2. **Empirically verified runtime effect:** In `RunBatchTest`, a 100-cell stack with 1 physical defect normally fails the end-of-line test with flag `OHMIC` ($V[-1] = 32.69\text{ V}$). Under the exception fallback path, the stack is simulated with zero penalties, passing cleanly with `flags = 0` ($V[-1] = 52.07\text{ V}$). An infrastructure/database hiccup completely inverts the quality verdict.
  3. **Comment/code mismatch:** Line 126 (`activityDerate = Math.min(0.6, defectCount * 0.15)`) scales by total `defectCount` aggregated across all stations, directly contradicting the comment at `:121-125` claiming that the derate specifically targets defects from Stations 1–2.

---

## 4. Stations 1–4 and calibration

**Files:**
- `physical_engine/factory_simulation/station1_mea_preparation.py`
- `physical_engine/factory_simulation/station2_catalyst_deposition.py`
- `physical_engine/factory_simulation/station3_bipolar_plate_stamping.py`
- `physical_engine/factory_simulation/station4_stack_clamping.py`
- `physical_engine/scripts/calibrate_stamping_clamping.py`

### P-11 ✅ Calibration is circular
- **Location:** `physical_engine/scripts/calibrate_stamping_clamping.py:1-12` (header specifies author-chosen targets: Station 3 defect rate $= 0.20\%$, Station 4 $= 0.80\%$, Station 1 degree of cure $\alpha \in [0.85, 0.98]$).
- **Finding:** The script verifies that an author-chosen process noise $\sigma$ ($5\%$ on Station 3 force, $0.5\%$ on Station 4 torque) reproduces the author-chosen defect rate targets against an author-chosen damage threshold. No external experimental dataset is used.
- **Sensitivity (ledger Monte Carlo run):** Station 3 defect rate jumps across **$0.00\%$ / $0.19\%$ / $1.93\%$** at $\sigma_F = 3\%$ / $5\%$ / $7\%$, because the nominal Forming Limit Diagram (FLD) damage index is **$0.864$** ($86.4\%$ of failure). The defect rate is an artifact of the chosen $\sigma_F$.

### P-12 ✅ Wear constants ratio ($\approx 23{,}800\times$) and non-Archard exponent
- **Location:** `station3_bipolar_plate_stamping.py:30` (`K_WEAR_PVD = 3.50e-6`, cited Fernandes et al. 2017), `:31` (`K_WEAR_DUPLEX = 1.47e-10`, cited Bitay et al. 2021), both documented in $\text{mm}^3/(\text{N}\cdot\text{m})$; `:32` (`GAMMA_ARCHARD = 1.35`, labelled *"Archard pressure exponent"*).
- **Finding:** Classical Archard wear is linear in normal load ($\gamma = 1$); an exponent of $1.35$ changes the dimensional units of $K_{\text{wear}}$. Moreover, the two cited wear coefficients differ by a factor of **$23{,}810\times$** and come from different tribological regimes/papers.

### P-13 ⚠️ Station 1 (Kamal–Sourour cure kinetics) operating margin
- **Evidence (re-run):** At nominal $T = 160\ ^\circ\text{C}$ ($433.15\text{ K}$) and dwell $t = 180\text{ s}$, degree of cure is $\alpha = 0.894 \in [0.85, 0.98]$. At $180\text{ s}$, the valid temperature window spans $155.5\text{--}174.5\ ^\circ\text{C}$ ($19.0\text{ K}$ wide). However, the nominal setpoint sits only **$4.5\text{ K}$** (or **$30\text{ s}$** of dwell) above the lower under-cure boundary ($\alpha(155\ ^\circ\text{C}, 180\text{ s}) = 0.849$, defect), so under-cure defects are governed by the assumed temperature noise $\sigma_T$. The upper "pinhole from over-cure" failure mode ($\alpha > 0.98$) lacks a physical mechanism in thermoset hot-pressing.

### P-17 ✅ Coincident activation energies ($68.5\text{ kJ/mol}$) and mismatched literature citation
- **Location:** `station1_mea_preparation.py:24` (`E2_CURE = 68.5e3` $\text{J/mol}$) and `pemfc_model.py:200` (`E_act = 68500.0` $\text{J/mol}$, cited Neyerlin et al. 2006).
- **Finding (code check & bibliographic resolution):**
  1. `E2_CURE` and ORR `E_act` share the exact numeric value $68{,}500\text{ J/mol}$.
  2. `docs/physical-engine/literature-calibration.md:12` claims this parameter originates from *"Fernandes et al. (2018), Polym. Test., DOI 10.1016/j.polymertesting.2018.03.012"*.
  3. Resolving this DOI demonstrates that the paper is actually: L.F.M. Motta, J.M.L. Reis, H.S. da Costa Mattos, *"A study of the tensile behavior of a PVDF polymer at different strain rates and temperatures"*, *Polymer Testing* 67 (2018), pp. 299–308. The paper investigates mechanical tensile deformation of PVDF thermoplastic polymer, contains no thermoset Kamal–Sourour cure kinetics, and contains no $68.5\text{ kJ/mol}$ activation energy.
  4. The citation is completely mismatched; `E2_CURE` was copy-pasted directly from the ORR electrocatalysis parameter in `pemfc_model.py`.

### P-20 ✅ Time-scale acceleration mismatch across stations, physics, and energy pricing
- **Location:** `station1_mea_preparation.py:32`, `BaseStationArtifact.java`, `sim_bridge_server.py:410`, `EnergyPriceArtifact.java`.
- **Finding (code check & timing audit):**
  1. **Station 1 hot-press:** Integrates Kamal–Sourour cure kinetics over a physical dwell time of $t = 180\text{ s}$ (`:32`).
  2. **Discrete event simulation:** Resource holons in `BaseStationArtifact.java` advance simulation time by a fixed step $t_{\text{proc}} = 5.0\text{ s}$ per operation.
  3. **End-of-line test bench:** Polarization sweep executes $12 \times 0.5\text{ s} = 6.0\text{ s}$ of blocking wall-clock `time.sleep` (**P-10**, **M-05**).
  4. **Electricity market clock:** `EnergyPriceArtifact.java` updates electricity spot prices on a discrete clock of $1.0\text{ s}$ per simulated tick.
  The acceleration factors linking physical reaction time ($180\text{ s}$), discrete simulation steps ($5\text{ s}$), spot price intervals ($1\text{ s}$), and wall-clock blocking ($6\text{ s}$) are undocumented, arbitrary, and conflicting.

---

## 5. Experiment, metrics, and statistics

**Files:**
- `experiments/run_prosa_vs_adacor.py`
- `experiments/analyze_results.py`
- `analysis/results.csv` ($3600$ ticks, $n = 15$ per arm) and `analysis/results_stats.md` / `.json`
- `analysis/results_1440_5.csv` ($1440$ ticks, $n = 5$ per arm; **no `_stats.md` or `.json` present**)
- `analysis/results_360_10.csv` ($360$ ticks, $n = 10$ per arm) and `analysis/results_360_10_stats.md` / `.json`
- `analysis/prosa_vs_adacor.ipynb`

### E-01 ✅ Dead and near-dead runs: two distinct failure modes
In the primary 3600-tick dataset (`analysis/results.csv`), **8 of 15 PROSA runs** and **2 of 15 ADACOR runs** produced $\le 1$ completed order, via two distinct modes:
- **Mode A — Never started (0 submitted, 0 completed):** PROSA runs `0, 1, 2, 3, 4` have `submitted_count = 0`, `completed_count = 0`, and **`0.0` in every metric column**. These 5 runs are the entire first batch of 5 replicas launched when the JVM/Python stack starts cold (**E-04**).
- **Mode B — Stalled after starting (>0 submitted, $\le 1$ completed):**
  - PROSA runs `7, 12, 13`: each submitted $6$ orders and completed only $1$.
  - ADACOR runs `11` ($16$ submitted / $0$ completed) and `14` ($10$ submitted / $0$ completed), plus near-stalls `8` ($13$ / $2$) and `9` ($18$ / $2$).
- **Disjoint run IDs:** Failed run IDs are disjoint between PROSA (`0–4, 7, 12, 13`) and ADACOR (`11, 14`), ruling out a simple seed-specific initial geometry deadlock.
- **Self-flagged in repo:** `analysis/results_stats.md` explicitly warns that near-zero-completion runs are present and cautions that hypothesis tests should be treated as exploratory. That warning was omitted from `report.tex` and `claim-matrix.md`.

### E-02 ✅ Five compounding metric computation bugs in `run_prosa_vs_adacor.py`
1. **Zero-fill of dead runs (`:83-97`):** When a run has zero completed orders, the script assigns `throughput = 0`, `tardiness_mean = 0`, `tardiness_max = 0`, `wip_mean = 0`, `defect_rate = 0`, and `energy_cost_eur = 0.0`. Those zeros are passed directly into `analyze_results.py` as if they were valid measurements ($0\text{ s}$ cycle time, $0\%$ defects, $0\text{ EUR}$ cost).
2. **Wrong throughput denominator (`:101-102`):** `throughput = len(merged) / max_time` uses `max_time = run_orders['sim_time'].max()` (the timestamp of the last order event) instead of the fixed simulation horizon $H$. In Mode B stalled runs (`7, 12, 13`), where 1 order finishes early and the factory deadlocks for the rest of the horizon, `max_time` is tiny, inflating their calculated throughput to **`0.0128`, `0.0151`, and `0.0150` orders/s**—near the top of the PROSA distribution ($50\% / 75\% / 90\%$ quantiles: $0.0118 / 0.0128 / 0.0144$).
3. **Survivorship-biased Little's Law WIP (`:106`):** `wip_mean = merged['cycle_time'].sum() / max_time` sums only *completed* orders and divides by `max_time`. In-flight orders that remain blocked in queues or deadlocked on AMRs contribute **$0$** to WIP.
4. **Silent `except:` fallbacks (`:43-45`, `:59`, `:74`):** A bare `except:` around the `StationQuality` query (`:59`) substitutes an empty DataFrame on any SQLite error, yielding `defect_rate = 0` (`:74`). Similarly, `compute_energy_cost` returns `0.0` on missing tables or empty slices (`:43`, `:45`).
5. **Misnamed metric & missing metadata:** `tardiness_mean` is actually mean **cycle time** ($t_{\text{completed}} - t_{\text{submitted}}$); there are no due dates in the model. Furthermore, `results.csv` records no `horizon_s`, `seed`, `started`, or `dropped_ner` columns.

### E-03 ✅ Nominal significance ($p = 0.030$) is a zero-fill and multiplicity artifact; sample sizes vary across horizons
Two-sided Mann–Whitney $U$ test on `tardiness_mean` in `results.csv` (re-run):

| Data handling | PROSA $n$ vs. ADACOR $n$ | PROSA mean ($\text{s}$) | ADACOR mean ($\text{s}$) | Two-sided Mann–Whitney $p$ |
|---|---|---|---|---|
| **As in repo (zero-filled dead runs kept)** | $15\text{ v }15$ | $200.8$ | $358.8$ | **$0.0300$** |
| **Exclude $\le 1$ completion** | $7\text{ v }13$ | — | — | **$0.4378$** |
| **Healthy runs only ($\ge 20$ completions)** | $6\text{ v }10$ | — | — | **$0.0559$** |

- **Direction of the zero-fill artifact:** Because $5$ dead PROSA runs are filled with `tardiness_mean = 0.0` (vs. $2$ in ADACOR), PROSA's mean cycle time is artificially dragged down from $\sim 350\text{ s}$ to $200.8\text{ s}$. `report.tex:767` then misinterprets this zero-fill artifact as a causal finding (*"reflecting the dwell-time cost of holding orders suspended"*) and labels it statistically significant.
- **Multiplicity collapse:** Applying Holm–Bonferroni across the 6 metrics in `results_stats.md` raises the minimum $p$-value from $0.02997$ to **$0.180$** (adjusted vector: $[0.842, 0.180, 0.842, 1.0, 1.0, 1.0]$). Across the 9 hypothesis tests in `report.tex` (3 horizons $\times$ 3 headline metrics), Bonferroni requires $\alpha = 0.05 / 9 \approx 0.0056$ (Holm adjusted $p = 0.270$).
- **Unequal sample sizes across horizons (`🆕`):** Inspection of `analysis/` reveals that the three horizons in `report.tex` do not even share a sample size:
  - $360$ ticks (`results_360_10.csv`): $n = 10$ per arm.
  - $1440$ ticks (`results_1440_5.csv`): $n = 5$ per arm (and missing any `_stats.json`/`.md` audit file). At $n = 5\text{ v }5$, the minimum possible two-sided exact Mann–Whitney $p$-value with zero overlap is $\frac{2}{\binom{10}{5}} = \frac{2}{252} \approx \mathbf{0.00794}$, which **cannot mathematically pass** a 9-test Bonferroni threshold ($\alpha \approx 0.0056$) even under complete separation of the two arms.
  - $3600$ ticks (`results.csv`): $n = 15$ per arm (half of the $n = 30$ planned).
- **Broken pairing:** Seeds are deterministic functions of `runId` (`BaseStationArtifact.java:48` uses `stationId.hashCode() ^ runId`; `AMRArtifact.java:129`), yet `analyze_results.py` runs an *unpaired* Mann–Whitney test, and only **$5$ of $15$ pairs** have $>1$ completion in both arms.
- **Note on post-treatment conditioning:** Filtering to $\ge 2$ completions ($7\text{ v }13$) yields $p = 0.0063$ on throughput ($p = 0.003$ for $\ge 20$ completions, $6\text{ v }10$), both favouring PROSA—but conditioning on survival is post-treatment selection and must not be reported as a primary treatment effect.

### E-04 ✅ Sequential arm execution confounds treatment with cold start
- **Location:** `experiments/run_prosa_vs_adacor.py`.
- **Finding:** All PROSA batches run first (in batches of 5), followed by all ADACOR batches, deleting the SQLite file between batches. Because the very first batch of 5 PROSA runs (`0–4`) suffered total failure (`submitted_count = 0`, Mode A in **E-01**), execution order and JVM/gRPC/LUT warm-up are directly confounded with the control architecture treatment.

### E-05 ✅ Energy metric is $\sim 10^{-6}\text{ EUR}$ ($\sim 8\text{ J/stack}$) and acts as a completion counter ($\rho = 0.978$)
- **Evidence (re-run):** Mean `energy_cost_eur` is $5.55 \times 10^{-6}\text{ EUR}$ (PROSA) vs. $6.13 \times 10^{-6}\text{ EUR}$ (ADACOR), $p = 0.63$.
- **Physical unit anomaly (`🆕`):** Per completed order, `energy_cost_eur` is **$2.75 \times 10^{-7}\text{ EUR}$** (PROSA) vs. **$3.15 \times 10^{-7}\text{ EUR}$** (ADACOR). At electricity prices of $100\text{--}150\text{ EUR/MWh}$ ($1\text{ MWh} = 3.6 \times 10^9\text{ J}$), $2.75 \times 10^{-7}\text{ EUR}$ corresponds to only **$\sim 6.6\text{--}9.9\text{ Joules}$** of electrical energy per tested 100-cell stack (a $\text{W}$ vs. $\text{kW}$ or $\text{s}$ vs. $\text{h}$ unit conversion error).
- **Collinearity with completions (`🆕`):** Because electricity consumption is only integrated from the Station 5 cathode compressor during end-of-line tests (Stations 1–4 and AMRs have no power model), `energy_cost_eur` is nearly a pure multiple of `completed_count`: Spearman $\rho = \mathbf{0.978}$ across started runs ($n = 25$). Thus, the experimental metric cannot evaluate energy-aware scheduling.

### E-06 ✅ `report.tex` order totals do not match `results.csv` and mask a $23.0$ percentage-point completion gap
- **Location:** `report.tex:676` and `:767` vs. `analysis/results.csv` (`verify_stats.py` S5).
- **Evidence (re-run):**

| Source (3600-tick horizon) | PROSA completed / submitted (%) | ADACOR completed / submitted (%) | Completion rate gap (PROSA $-$ ADACOR) |
|---|---|---|---|
| **`report.tex:676, 767`** | $228\ /\ 326$ (**$69.9\%$**) | $297\ /\ 426$ (**$69.7\%$**) | **$+0.2\text{ pp}$** (virtually identical) |
| **`analysis/results.csv` (actual)** | $276\ /\ 325$ (**$84.9\%$**) | $302\ /\ 488$ (**$61.9\%$**) | **$+23.0\text{ pp}$** (massive drop under ADACOR) |

- **Impact (`🆕`):** The misreported numbers in `report.tex` make the two architectures appear to complete the exact same fraction of submitted work ($\sim 70\%$). In the actual CSV data, PROSA completes **$84.9\%$** of submitted orders (across its 10 started runs) while ADACOR completes only **$61.9\%$**—a **$23.0$ percentage-point** loss of submitted orders under ADACOR, directly consistent with ADACOR's price-spike response aborting in-flight intentions (**M-01**).

### E-07 ✅ Unsupported $p < 0.001$ claim (fixed in `claim-matrix.md`, still open in `report.tex`)
- **Status on `main`:** `docs/artifact-evaluation/claim-matrix.md` §5.1 was updated by `baseline-freeze` to state *under revision*, uncorrected $p = 0.030$ ($n = 15\text{ v }15$).
- **Still open:** `report.tex:767` still states *"statistically significant difference … $p = 0.030$"* and builds a causal narrative around it, which also self-contradicts `report.tex:785` (*"none of the differences reach statistical significance ($p > 0.10$)"*).

### E-08 ✅ The experiment does not exercise the physics engine
- With calibrated defect probabilities of $0.2\%\text{--}0.8\%$ ($\sim 1$ defect per $200\text{--}500$ station ops), the upstream-to-Station-5 physical coupling almost never triggers during a 15-run batch. No physics-on vs. stochastic-bernoulli ablation exists, and the closed-loop setpoint adjustment described in the README is never evaluated.

---

## 6. Multi-agent system, control semantics, and determinism

**Files:**
- `src/agt/supervisor_agent.asl`, `src/agt/order_holon.asl`, `src/agt/resource_holon.asl`, `src/agt/amr_agent.asl`
- `src/org/prosa_org.xml`, `src/org/adacor_org.xml`
- `src/main/java/factory/MainSimulator.java`, `TestBenchArtifact.java`, `AMRArtifact.java`, `BaseStationArtifact.java`
- `src/test/java/factory/SeededReplaySeed1Test.java` … `SeededReplaySeed5Test.java`

### M-01 ✅ The "ADACOR" arm is not ADACOR (drain + suspend + abort, no admission throttling)
- **Location:** `supervisor_agent.asl:102`, `:143`; `TestBenchArtifact.java:295-308` (`cancelPendingRpc()`).
- **Finding:** When electricity price crosses $150\text{ EUR/MWh}$, the supervisor under `active_schema(adacor)` drains for up to $15\text{ s}$ of simulated time, suspends for up to $10\text{ s}$, and **aborts in-flight intentions** (including calling `cancelPendingRpc("ADACOR suspend")` on the test bench), then resumes the exact same Contract-Net Protocol (CNP) as PROSA.
- **No throttling exists:** Despite `report.tex:633, 650, 769, 785` and `docs/architecture/holonic-control.md:16` claiming *"adaptive supervisor throttling"* / *"admission throttling"*, **zero lines of admission-rate throttling code exist** in any `.asl` or `.java` file. Nor does the code implement Leitão & Restivo's (2006) stationary master-slave $\leftrightarrow$ transient autonomous-holon pheromone/autonomy transition.

### M-02 ✅ AMR deadlock resolution is disabled under ADACOR (experimental confound)
- **Location:** `supervisor_agent.asl:195-196`: `+transport_blocked(BatchId) : active_schema(prosa)`.
- **Finding:** Supervisor deadlock recovery is guarded by `active_schema(prosa)` and is completely inactive when `active_schema(adacor)` holds, introducing an unstated confound between the two experimental arms.

### M-03 ✅ MoISE organisation XML is decorative
- **Location:** `src/org/adacor_org.xml:39, 44` (`assign_tasks`).
- **Finding:** The MoISE mission/goal `assign_tasks` appears twice in `adacor_org.xml` and nowhere in any `.asl` or `.java` file. `active_schema` is checked only in `supervisor_agent.asl`; organizational authority links are not enforced at runtime.

### M-04 ✅ "2PC" is a timeout barrier that forces commit on Phase 1 expiry
- **Location:** `supervisor_agent.asl:120-124` (Phase 0 TTL expiry $\to$ abort), `:172` (Phase 1 TTL expiry $\to$ `force_commit` decree).
- **Finding:** In Two-Phase Commit, a coordinator timeout after `PREPARE` cannot unilaterally force uncommitted/unreachable participants to commit without violating atomicity. The claim of *"no message loss or state corruption"* under 2PC is untested.

### M-05 ✅+🆕 Wall-clock timeouts break lock-step determinism (`10 ms` tick quorum vs. `6 s` RPC sleep vs. `30 s` RPC timeout) and agent roster regex bug
- **Locations:**
  - `MainSimulator.java:57` (`TICK_QUORUM_TIMEOUT_MS = 10`), `:112` (`Pattern.compile("^\\s*agent\\s+\\w+_" + runId + "\\s*:")`), `:70` (`registeredAgentCount = 13` fallback), `:299-300` (`await` timeout increments `droppedNerCount` and advances the tick anyway).
  - `TestBenchArtifact.java:243` (`l.await(30, TimeUnit.SECONDS)` wall-clock timeout waiting for `RunBatchTest`).
  - `sim_bridge_server.py:410` (`time.sleep(0.5)` $\times 12 = 6.0\text{ s}$ wall-clock sleep inside `RunBatchTest`, **P-10**).
- **Cross-finding causal chain (`P-10` $\to$ `M-05` $\to$ `M-04` / `M-09` $\to$ `E-01` / `E-03`) (`🆕`):**
  1. When an agent invokes an end-of-line test on `TestBenchArtifact`, its thread blocks synchronously on `l.await(30, SECONDS)` while Python executes $12 \times 0.5\text{ s} = \mathbf{6{,}000\text{ ms}}$ of wall-clock `time.sleep` (**P-10**).
  2. Meanwhile, `MainSimulator.java` waits only **$10\text{ ms}$ of wall-clock time** (`TICK_QUORUM_TIMEOUT_MS = 10`) per tick for all $13$ agents to submit their Next Event Request (NER).
  3. During a single $6{,}000\text{ ms}$ end-of-line test, the blocked agent misses up to **$600$ consecutive $10\text{ ms}$ tick barriers**, causing `droppedNerCount` to climb and simulated time (`sim_time`) to race ahead at wall-clock speed while the stack is being tested.
  4. Under 5-replica parallel execution on 2 CPU cores (`taskset`), queued $6\text{ s}$ RPCs easily exceed the $30\text{ s}$ wall-clock latch in `TestBenchArtifact.java:243`, triggering infrastructure timeouts (**M-09**), 2PC TTL expirations (**M-04**), inflated cycle times (**E-03**), and stalled runs (**E-01**).
- **Agent count parsing regex bug (`🆕`):**
  `MainSimulator.java:112` attempts to dynamically count agents in `factory.jcm` using `Pattern.compile("^\\s*agent\\s+\\w+_" + runId + "\\s*:")`. Because multi-instance agent names follow `<type>_<index>_<runId>` (e.g. `order_1_1`, `station_1_1`, `amr_1_1`), `\w+_` matches up to the *first* underscore, so it tests whether `<index> == runId`. For `runId = 1`, it matches only agents with index 1 ($3$ agents out of $13$); for any `runId > 5`, it matches $0$ lines and silently falls back to the hardcoded default of 13.
- **Persistence gap:** `dropped_ner_count` is published in the transient WebSocket telemetry frame (`MainSimulator.java:501`, proto field 19) but is **never written to SQLite or `results.csv`**.

### M-06 ✅ Seeded replay tests assert liveness only, not trajectory determinism
- **Location:** `SeededReplaySeed1Test.java` … `SeededReplaySeed5Test.java`.
- **Finding:** Each test runs a single simulation and asserts `completedCleanly()` (which only checks `isShutdown()`, true whenever the tick limit is reached even if $0$ orders were submitted), non-null AMR artifact, non-empty positions, and zero JVM thread deadlocks. No test ever runs two replicas with the same seed and compares their state trajectories or SQLite ledgers. The `"0 drift"` determinism claim in `claim-matrix.md` is completely untested.

### M-07 ✅ Terminology: "Digital Twin" vs. "Digital Model"
- **Finding (code audit):** A comprehensive scan of the repository tree reveals **zero** physical industrial communication protocols, hardware drivers, or physical I/O interfaces (no OPC UA, MQTT, Modbus, ROS, PLC drivers, or physical sensor telemetry).
- **Taxonomic classification:** Under the established cyber-physical systems taxonomy of Kritzinger et al. (2018), an in silico virtual representation with no automated physical asset data flow is formally classified as a **Digital Model** (or co-simulation testbed). Labelling it a "Digital Twin" in documentation and publications is a misnomer that invites immediate examiner challenge.

### M-08 🆕 Hardcoded fallback HMAC secret (partially fixed; see T-02)
- `experiments/run_prosa_vs_adacor.py` now uses `resolve_telemetry_secret()` (`:125`, `:142`). However, the fallback string `"phase4_monte_carlo_secure_key"` still appears in `tests/test_repo_hygiene.py` ($\times 2$) and `need-to-fix/SPEC-baseline-freeze.md` ($\times 1$), causing the hygiene test to fail on a git checkout (**T-02**). `.env.example`, `scripts/launch_phase4.sh`, and `TicketIssuer.java` should also be kept aligned with `resolve_telemetry_secret()`.

### M-09 ✅+🆕 Infrastructure failures recorded as physical test failures; cancel path sets `IDLE` ("ok")
- **Location:** `TestBenchArtifact.java:209-227` (non-OK gRPC status sets `lastFailureFlags = 0x10`, `lastTestPassed = false`, station state `OFFLINE`), `:252-273` ($30\text{ s}$ latch timeout sets the same flags), `:287` (`result.set(state == IDLE ? "ok" : "defect")`), `:295-308` (`cancelPendingRpc` sets `currentSummary = IDLE`).
- **Finding (code check & execution):**
  1. **Infrastructure errors masked as stack defects:** gRPC transport failures, channel errors, and $30\text{ s}$ wall-clock latch timeouts explicitly record flag `0x10` (`SOLVER_DID_NOT_CONVERGE`, with the comment *"reused as comms failure"*) and write `result = "defect"` into SQLite (`:214-225, 270-274`). Network latency and JVM/Python desync are thus recorded in empirical logs as physical manufacturing defects.
  2. **Aborted tests falsely report "ok":** When ADACOR suspends an active test via `cancelPendingRpc()`, line 301 sets `currentSummary = StationSummary.IDLE`. When the agent subsequently inspects the outcome at line 287 (`result.set(state == StationSummary.IDLE ? "ok" : "defect")`), `state == IDLE` evaluates to `true`, returning `"ok"` for a cancelled, uncompleted test.

---

## 7. Documentation and references

| ID | Finding | Evidence / location | On `main` |
|---|---|---|---|
| D-01 ✅ | Placeholder Zenodo DOI `10.5281/zenodo.1234567`, generic author `"Matrix Factory Research Team"`, venue `"IEEE TII, 2026"` | `docs/index.md:6,83,86`, `docs/citation.md:10,13,23` | open |
| D-02 ✅ | 16 hardcoded local `file:///` links across 6 docs (`websocket-telemetry` 4, `station-5-pemfc` 4, `grpc-protobuf` 3, `amr-agents` 3, `security-mtls` 1, `supervisor-agent` 1); `mkdocs.yml` has `repo_url` but no `edit_uri` (Material defaults to `/edit/master/`, whereas the branch is `main`) | `grep` across `docs/` and `mkdocs.yml` | open |
| D-03 ⚠️ | Earlier audit noted inverted PROSA/ADACOR hierarchy labels in `architecture-overview.md`. On `main`, `README.md`, `report.tex:164`, `holonic-control.md:12,16`, and `architecture-overview.md:28` consistently label PROSA heterarchical and ADACOR hierarchical. The substantive issue is construct validity (**M-01**). | `grep` | consistent on `main` |
| D-04 ⚠️ | Inconsistent electricity price currency and units: code, `supervisor-agent.md:50`, and `holonic-control.md:23` use $150\text{ EUR/MWh}$ ($135\text{ EUR/MWh}$ reset), whereas the bidding formula in `docs/agents-and-mas/order-resource-holons.md:50` specifies $P_{\text{grid}}$ in **$\text{\$/kWh}$**. | `grep` | open |
| D-05 ⚠️ | `README.md:155,161` claims **71** pytest tests and **18** Java test classes. Actual counts in the tree:<br>• **Python (`92` `def test_` total):** `90` in `physical_engine/` (`87` excluding `test_grpc_security.py`, which the audit baseline skipped; $84$ collected $= 70$ passed $+ 14$ skipped) **plus `2` uncounted test files in `scripts/`** (`scripts/test_daemon_launcher.py` and `scripts/test_generate_factory_jcm.py`).<br>• **Java (`20` `.java` files in `src/test/java/factory/`):** **`17` `@Test` classes** (`DatabaseArtifactTest`, `InvariantTests`, $5\times$ `SeededReplaySeed1..5Test`, and $10\times$ `SystemIntegration` classes: `V1`, `V2`, `V3ForceAbort`, `V3SlowAccept`, `V4`–`V9`) **plus `3` non-test helper classes** (`OrderLedgerReader`, `SimRunHandle`, `SimulationTestHarness`). | Tree & `grep` recount | open |
| D-06 ✅ | Snapshot drift across documents (all 7 points confirmed):<br>1. Stations 1–4: `report.tex` describes them as "stochastic black boxes" vs. mechanistic JIT models in code.<br>2. Thermal model: `report.tex` describes 2-node thermal model vs. 1-node lumped core/coolant in code.<br>3. Reference exchange current: `report.tex` states $j_0 = 10^{-9}\text{ A/cm}^2$ vs. $2.5 \times 10^{-8}\text{ A/cm}^2$ in code.<br>4. JUnit test classes: `report.tex` / README claims 18 (or 3) vs. actual 17 `@Test` classes + 3 helpers in tree.<br>5. ADACOR mode switching: docs describe text-patching `.asl` vs. runtime `ADACOR_ENABLED` env var.<br>6. Manuscript citations: `claim-matrix.md` cites Fig. 4/5, Tab. 2, §5.3 of an absent external manuscript, claiming "Fig. 5" is reproduced by pytest.<br>7. Missing audit banner: `ONBOARDING.md` and `ONBOARDING_pt-BR.md` lack the `"RESULTS UNDER AUDIT"` banner added to `README.md`. | `report.tex`, `README.md`, `claim-matrix.md`, `ONBOARDING*.md` | open |
| D-07 ⚠️ | **Kleemann et al. (2009), *J. Power Sources* 190, 92–102:** true DOI is `10.1016/j.jpowsour.2008.09.026` (`README.md:64` is correct; `docs/physical-engine/literature-calibration.md:21` has a fabricated/wrong suffix `10.1016/j.jpowsour.2009.01.076`).<br>**Bitay et al. (2021):** `README.md:62` lists `10.1007/s00170-024-13800-x`. Resolving this DOI shows it is actually Hanwen et al. (2024), *"Investigation on the influence of welding parameters on weld formation..."*, *Int. J. Adv. Manuf. Technol.*—a robotic welding paper, completely mismatched.<br>**Fernandes et al. (2018):** `literature-calibration.md:12` cites DOI `10.1016/j.polymertesting.2018.03.012`. Resolving it shows it is Motta et al. (2018) on PVDF tensile behavior (**P-17**).<br>**"Yonkist stability criterion (ASME 2025)":** Identified in Elijah **Yo**der, Wayne Strasser, Robert Kacinski, and Braden Jones, *"Unrestraining the Biot Number for Systems With Internal Heat Generation"*, ASME *J. Solar Energy Eng.* (2025) (**P-14**).<br>The calibration table's `"Verification"` column marks parameters as `"Verified"` when they are merely cited. | Web search, DOI lookup & `grep` | open |

---

## 8. Testing, CI, and repository hygiene

### T-01 ✅ The test suite is green while every physics and determinism bug is active
- Running `pytest physical_engine --ignore=physical_engine/factory_simulation/test_grpc_security.py` yields **70 passed, 14 skipped** with **P-01…P-06** present.
- Indeed, `pemfc_test.py` actively enforces `z_pemfc == 4` (**P-01**), and `SeededReplaySeed1..5Test.java` only check `isShutdown()` (**M-06**).
- **Unexplained skips:** Neither the reason for excluding `test_grpc_security.py` (3 tests) nor the trigger for the 14 skipped tests in `physical_engine/` is documented in the test output or docs.

### T-02 🆕 `test_repo_hygiene.py` fails on a git checkout by matching itself, and CI never runs `tests/` or `scripts/`
- **Location:** `tests/test_repo_hygiene.py:61, 63`; `need-to-fix/SPEC-baseline-freeze.md:23`; `.github/workflows/ci.yml:44`.
- **Self-matching bug:** `test_sc_bf_2_secret_scan_empty` runs `git grep -n "phase4_monte_carlo_secure_key"` across the repository and asserts empty output. Because `tests/test_repo_hygiene.py` itself contains that exact literal twice (in its docstring and command list) and `need-to-fix/SPEC-baseline-freeze.md` contains it once, running the test in a git-initialized checkout returns **3 hits (`rc = 0`) and fails the assertion**.
- **CI and scan coverage gaps:**
  1. `.github/workflows/ci.yml:44` runs `pytest physical_engine/` only—it never executes `tests/test_repo_hygiene.py` or the two test files in `scripts/` (`scripts/test_daemon_launcher.py`, `scripts/test_generate_factory_jcm.py`).
  2. `test_sc_bf_1` requires the git tag `audit-baseline-2026-10` (which must be fetched with `actions/checkout` `fetch-depth: 0` in CI).
  3. The hygiene claim scan (`p ?< ?0.001`) only checks `docs/` and `README.md`, ignoring `report.tex`, `ONBOARDING.md`, `ONBOARDING_pt-BR.md`, and `analysis/prosa_vs_adacor.ipynb`.

### T-03 ✅+🆕 Committed binary LUT caches, stale lockfile, and tracked generated files
- **Location:** `.physical_engine/lut_cache/`, `factory.jcm`, `.agents/`.
- **Finding (code & git tree inspection verified):**
  1. **Stale lockfile tracked in git:** `.physical_engine/lut_cache/.lut_generation.lock` is committed in version control. If `lut_manager.py` honours the lockfile, fresh LUT generation blocks indefinitely; if it ignores it, the lockfile is misleading dead state.
  2. **Legacy v1 pickle files ($1.3\text{ GB}$) + large binary `.npz` in git:** Nine legacy v1 pickle files (`lut_CH4_v1.pkl`, `lut_CO2_v1.pkl`, `lut_CO_v1.pkl`, `lut_H2O_v1.pkl`, `lut_H2_v1.pkl`, `lut_N2_v1.pkl`, `lut_O2_v1.pkl`, `lut_Water_v1.pkl`, `lut_water_saturation_v1.pkl`) totaling $1.3\text{ GB}$ are committed in `.physical_engine/lut_cache/` alongside `stacked_luts_v2.npz` ($1.0\text{ MB}$). Unpickling `.pkl` binaries in Python carries arbitrary code execution risks and is fragile across NumPy versions.
  3. **Template vs. generated config drift:** Both `factory.jcm` and `factory.jcm.template` (used by `scripts/generate_factory_jcm.py`) are tracked in git, inviting silent drift if one is edited without regenerating the other.
  4. **Agent rules in root:** `.agents/rules/graphify.md` and `.agents/workflows/graphify.md` are committed in the repository root.

---

## 9. Corrections to earlier reviews, the ledger, and rev. 1–2 of this file

| Earlier statement | Corrected finding |
|---|---|
| Review 2: "$\ge 3$ defects $\to$ `OHMIC` + `LOW_ACT`" | True only at $1\text{ bar}$ inlet pressure and starting from **$2$** defects (`verify_e2e_2.py` §a: $1\text{ bar}$ d2–d4 gives `OHMIC\|LOW_ACT`; $2\text{ bar}$ d1–d4 gives `OHMIC` only). |
| Review 2: "`THERMAL_SHUTDOWN` is a threshold on the setpoint" | `operating_temp_k` never reaches the thermal check; the flag reads internal `self._thermal.T_core`, which actually cools down during the sweep (**P-06**, **P-08**). |
| Review 1: "Station 1 cure window is narrow" | At $180\text{ s}$ dwell, the window is $19.0\text{ K}$ wide ($155.5\text{--}174.5\ ^\circ\text{C}$); the issue is that the nominal $160\ ^\circ\text{C}$ setpoint sits $4.5\text{ K}$ ($30\text{ s}$) from the lower boundary (**P-13**). |
| Ledger: "87 pytest tests (Review 2 said 90)" | There are $90$ `def test_` functions in `physical_engine/` ($87$ excluding `test_grpc_security.py`) plus $2$ more test files in `scripts/` (**D-05**). |
| Ledger / rev. 1: "Java sets only 5 request fields" | `TestBenchArtifact` sets $10$ fields; the unset proto fields are `rh_anode`, `j_lim_derate_fraction`, and `current_densities`, while `lambda_mem` is absent from `sim_bridge.proto` (**P-09**). |
| Rev. 1: "Continuous inputs never change the verdict" | Variance alone fails at `var_ratio` $= 20$ ($\text{threshold} \approx 8.6$); `ecsa_ratio` $= 0.25$ fails `LOW_ACT`; clamp pressure and porosity do not flip the verdict (**P-07**). |
| Rev. 1 / ledger D-03: "`architecture-overview.md` labels PROSA hierarchical" | Consistent on current `main` (PROSA heterarchical, ADACOR hierarchical) (**D-03**). |
| Rev. 1 / ledger D-04: "Docs say $0.25\text{ \$/kWh}$" | Not found; the actual mismatch is $150\text{ EUR/MWh}$ vs. $P_{\text{grid}}$ in $\text{\$/kWh}$ in `order-resource-holons.md:50` (**D-04**). |
| Review 1: "`dropped_ner_count` fixed at 0 in the frame" | It is wired to the WebSocket frame (`MainSimulator.java:501`), just not persisted to SQLite or `results.csv` (**M-05**). |
| Rev. 2 §10: "Which commit was audited (no `.git`); only the manifest identifies it" | The re-verified `main` archive embeds its exact `git archive` commit hash **`89c67320a0fcb97ba81acd7c8ac44000a54b23af`** in the directory prefix and ZIP comment (§0). |
| Rev. 2 §0.3 / §1: "`M-08` is fixed" | Fixed in `run_prosa_vs_adacor.py`, but the literal remains in `tests/test_repo_hygiene.py` and `SPEC-baseline-freeze.md`, breaking the hygiene test (**M-08**, **T-02**). |

---

## 10. Verified vs. open checks

### 10.1 Items verified in rev. 4
- **JVM / Gradle execution:** Ran `./gradlew test` on replay and integration suites. Demonstrated that `RunCentralisedMAS.finish()` calls `System.exit(0)` asynchronously, terminating the Gradle worker JVM and causing subsequent `@Test` methods in multi-test classes (`InvariantTests`) to be skipped. Single-test suites (`SystemIntegrationV1Test`, `DatabaseArtifactTest`) execute and pass cleanly.
- **Code-by-code and programmatic verification:** Executed `need-to-fix/verify_scripts/verify_unverified_items.py` confirming:
  - **P-17:** $E_2 = 68.5\text{ kJ/mol}$ coincident with ORR; Fernandes DOI `10.1016/j.polymertesting.2018.03.012` resolved to Motta et al. (2018) on PVDF tensile deformation (mismatched/fabricated citation).
  - **P-18:** Springer 30 °C polynomial evaluated at 80 °C with no $T$-dependence; asymmetric ODE relaxation is kinetic asymmetry, not equilibrium sorption hysteresis; dead code with 0 non-test callers.
  - **P-19:** SQLite read exception path falls back to zero quality penalties, turning a defective stack ($V[-1] = 32.69\text{ V}$, `OHMIC`) into a passing stack ($V[-1] = 52.07\text{ V}$, `flags = 0`); `defectCount * 0.15` scales across all stations despite comment.
  - **P-20:** Time-scale mismatch across $180\text{ s}$ physical dwell, $5.0\text{ s}$ discrete simulation step, $6.0\text{ s}$ wall-clock RPC sleep, and $1.0\text{ s}$ electricity price ticks.
  - **M-05:** $10\text{ ms}$ tick quorum vs. $6{,}000\text{ ms}$ wall-clock sleep; `MainSimulator.java:112` regex bug (`\w+_` matches only index 1, yielding 3 agents instead of 13 for `runId=1`); `droppedNerCount` omitted from SQLite.
  - **M-07:** Zero industrial/hardware communication protocols or PLC interfaces in the repository; system is strictly a **Digital Model** under Kritzinger et al. (2018).
  - **M-09:** Transport/timeout errors mapped to `0x10` (`SOLVER_DID_NOT_CONVERGE`, comment admits comms failure) and `result = "defect"`; `cancelPendingRpc` sets `IDLE`, causing line 287 to return `"ok"` for aborted tests.
  - **D-06:** All 7 snapshot drift points confirmed across `report.tex`, `README.md`, `claim-matrix.md`, and `ONBOARDING*.md`.
  - **D-07 & P-14:** Origin of "Yonkist" identified in Elijah Yoder et al., ASME *J. Solar Energy Eng.* (2025); Bitay DOI `10.1007/s00170-024-13800-x` resolved to Hanwen et al. (2024) robot welding paper (mismatched).
  - **T-03:** Git tracking confirmed for `.lut_generation.lock`, $9$ legacy `.pkl` files ($1.3\text{ GB}$), `stacked_luts_v2.npz`, and both `.jcm` / `.template` files.

### 10.2 What remains not verified / open
- **Stations 2 and 4 & AMR pathfinding internals:** Read partially; not audited line-by-line to the same depth as Stations 1, 3, and 5.
- **Short/medium horizon CSV recomputation:** The presence and sample sizes of `results_360_10.csv` ($n=10$) and `results_1440_5.csv` ($n=5$) were verified in the tree (**E-03**), but their exact order totals ($42/88, 31/79, 93/115, 66/90$ in `report.tex`) were not re-summed via `verify_stats.py`.
- **Git tag `audit-baseline-2026-10`:** Absent from a standalone `git archive` export; requires full git repository history.
- **Full re-execution of 15 seeds of PROSA vs. ADACOR:** Requires ~10 hours under current unoptimized wall-clock sleeps, and would be confounded by M-05/P-10 until determinism fixes are applied.

---

## 11. Innovation assessment

- **Defensible engineering differentiators:**
  1. Lock-step BDI/JaCaMo $\leftrightarrow$ gRPC $\leftrightarrow$ multi-station physical co-simulation architecture with seeded replay hooks, CI, and containerization.
  2. Single-JVM $N$-replica parallel execution via dynamic namespace rewriting.
  3. End-to-end causal chain from upstream manufacturing station parameters to end-of-line electrochemical stack testing—*provided* the coupling coefficients and physics are remediated (**P-01…P-09**).
- **Not novel (and should not be claimed as theoretical contributions):**
  - The 0D/1D PEMFC polarization and lumped thermal equations (textbook Larminie & Dicks, Springer 1991, Pukrushpan et al.).
  - Contract-Net Protocol, cooperative $A^*$, and HLA-style conservative time regulation.
- **Recommended framing:** Position the work around the **reproducible cyber-physical MAS testbed and diagnostic methodology**, backed by a structured related-work comparison table (physical fidelity, agent paradigm, time synchronization, manufacturing-to-performance coupling, reproducibility, and multi-instance scale).

---

## 12. Impact on the thesis and likely examiner questions

The current PROSA vs. ADACOR experiment cannot support superiority claims about holonic control architectures because (a) the ADACOR arm is a pause-and-abort script rather than ADACOR (**M-01**), (b) $6\text{ s}$ wall-clock sleeps inside the test bench collide with $10\text{ ms}$ tick barriers (**P-10**, **M-05**), (c) dead runs and zero-filling drive the only nominal $p$-value (**E-01…E-03**), and (d) the reported table in `report.tex` mismatches `results.csv` and hides a $23.0$ percentage-point completion drop under ADACOR (**E-06**). However, **turning these diagnostics into a rigorous methodological audit and remediated benchmark is a strong, defensible thesis contribution.**

### Questions an examiner is likely to ask
1. Why is $z = 4$ used in the Tafel denominator, and what Tafel slope in $\text{mV/dec}$ does your model produce? (**P-01**)
2. Why does the stack temperature *decrease* during a polarization sweep up to $2.375\text{ A/cm}^2$? (**P-04**, **P-06**, **P-08**)
3. What experimental polarization dataset validates the Station 5 PEMFC model? (**P-11**)
4. How would the PROSA vs. ADACOR results change if the physics engine were replaced by a constant delay and a Bernoulli coin flip? (**E-08**)
5. Why is the energy cost per stack on the order of $10^{-7}\text{ EUR}$ ($\sim 8\text{ Joules}$), and why does it correlate at $\rho = 0.98$ with completed orders? (**E-05**)
6. Why does `report.tex` state $228/326$ and $297/426$ completed orders when `results.csv` has $276/325$ ($84.9\%$) and $302/488$ ($61.9\%$)? (**E-06**)
7. How can the simulation be deterministic when `MainSimulator` uses a $10\text{ ms}$ wall-clock quorum timeout while `RunBatchTest` sleeps for $6{,}000\text{ ms}$ of wall-clock time? (**P-10**, **M-05**)
8. What happens in the 5 PROSA runs (`0–4`) where zero orders were submitted, and why were they filled with `0.0` cycle time? (**E-01**, **E-02**, **E-03**)
9. What happens to an end-of-line test that is cancelled by an ADACOR price-spike suspend? (**M-09**)

---

## 13. Remediation map (module $\to$ findings)

| Module | Findings addressed | Key implementation notes |
|---|---|---|
| `baseline-freeze` | E-07, M-08, T-02, D-06 (banners) | Applied on `main`, but **must fix T-02** (exclude `tests/test_repo_hygiene.py` and `need-to-fix/` from `git grep` or construct the string dynamically; add `tests/` and `scripts/` to `.github/workflows/ci.yml`; add audit banner to `ONBOARDING*.md`; scan `report.tex` and `prosa_vs_adacor.ipynb`). |
| `measurement-integrity` | E-01 (reporting), E-02, E-03, E-05 (scaling & reporting), E-06 | `NaN`-not-zero for 0-completion runs; fixed horizon $H$ in throughput denominator; time-integrated Little's Law WIP including in-flight orders; remove bare `except:`; fix $\text{W}\to\text{MWh}$ scaling in `compute_energy_cost`; paired Wilcoxon + Holm–Bonferroni across all horizons; regenerate stats for all 3 CSVs (`360_10`, `1440_5`, `3600_15`). |
| `pemfc-physics-core` | P-01…P-06, P-14, P-15, P-16, P-18 | Update `pemfc_model.py`, `sim_bridge_server.py`, **and all kernels in `physical_engine/optimization/` (`numba_ops.py`, `_numba_ops_core_python.py`, `_numba_ops_core.pyx`)**: $\alpha_c n_\alpha = 1.0$, roughness factor $r_f$, asinh/clamped low-$j$ activation, entropic heat ($E_{\text{tn}} = 1.481\text{ V}$), active area $A_{\text{cell}}$ in $Q_{\text{gen}}$, consistent $N_{\text{cells}}$, dimensional flooding ODE, true Biot check, cell-reversal flag, unified `R_internal` default. |
| `pemfc-validation` | P-02 (identifiability), P-11 (Station 5) | Calibrate and validate against Ballard Mark V / EH-31 (`arXiv:2404.07508`) with held-out pressure curves and physical bounds on $r_f$. |
| `station-surrogates` | P-11, P-12, P-13, P-17, P-20 | Documented, seeded continuous `QualityState` surrogates; reconcile wear units/exponents; document time-scale acceleration factor. |
| `quality-coupling` | P-07, P-08, P-09, P-10, P-19 | Continuous `QualityState` $\to$ stack parameters; wire `request.operating_temp_k` into `T_core` and reset thermal state per stack inside `_physics_step_lock`; populate or remove dead proto fields and wire `scripts/check_proto_sync.py` + `visualization/dashboard.js`; **remove `time.sleep(0.5)`**; **fail closed** (not "zero penalty") when SQLite quality fetch fails. |
| `sim-determinism` | E-01, M-05, M-06, M-09, T-03 | Diagnose Mode A & Mode B stalls; eliminate wall-clock race between `TICK_QUORUM_TIMEOUT_MS` and RPC execution; derive agent roster count dynamically; persist `droppedNerCount` to SQLite/CSV; separate comms/timeout errors from physical defects and fix `cancelPendingRpc` `"ok"` bug; make `SeededReplaySeed1..5Test` assert identical state/DB hashes across twin runs; clean up `.lut_generation.lock` and legacy `.pkl` files. |
| `control-policy-semantics` | M-01…M-04, E-05 | Enable deadlock recovery in both arms; add station/AMR power models; replace `force_commit` or rename 2PC honestly; implement or remove decorative MoISE `assign_tasks`. |
| `adacor-mode-switching` | M-01, M-03 | Implement genuine stationary (hierarchical supervisor scheduling) $\leftrightarrow$ transient (heterarchical autonomous holon) mode switching with recovery timer $\tau$. |
| `experiment-redesign` | E-04, E-01 (root cause), E-08, P-20 | Interleaved/randomized arm execution with JVM warm-up discard; $\ge 30$ paired seeds per arm with power analysis; physics-on vs. physics-off ablation. |
| `claims-and-docs` | D-01…D-07, E-06, E-07 (`report.tex`), M-07 | Reconcile `report.tex` and `README.md` with actual CSVs and test counts; replace placeholder Zenodo DOI and `file:///` links; add `edit_uri` to `mkdocs.yml`; fix Kleemann/Bitay citations; adopt "co-simulation testbed" terminology. |

---

## 14. Reproduction

Run from the repository root with `numba`, `grpcio`, `protobuf`, `CoolProp`, `scipy`, and `pandas` installed:

| Script / Command | Reproduces |
|---|---|
| `python need-to-fix/verify_scripts/verify_physics.py` | P-01 ($35.04\text{ mV/dec}$), P-02 ($j_0$), P-03 ($V > \text{OCV}$), P-04 ($53\%\text{--}79\%$ heat), P-05 ($6.7\text{ s}$ vs. $167\text{ s}$), P-06 ($\Delta T_{\text{core}} = -0.0847\text{ K}$) |
| `python need-to-fix/verify_scripts/verify_p2_and_deadcode.py` | P-02 $\eta_{\text{act}}$ cancellation table, P-09 dead call-graph check |
| `python need-to-fix/verify_scripts/verify_e2e_rpc.py` | P-07 defect table, variance & ECSA threshold sweeps, P-08 ($T_{\text{core}}$ persistence), P-16 ($-6.31\text{ V}$ cell reversal) |
| `python need-to-fix/verify_scripts/verify_e2e_2.py` | P-07 ohmic resistance budget ($0.1045$ vs. $0.1474\ \Omega\cdot\text{cm}^2$), P-08 `operating_temp_k` invariance, $1\text{ bar}$ vs. $2\text{ bar}$ `LOW_ACT` flags |
| `python need-to-fix/verify_scripts/verify_stats.py` | E-01 (Mode A & Mode B stalls), E-03 ($p = 0.030 \to 0.438 / 0.056 / 0.180$), E-05 ($\sim 6 \times 10^{-6}\text{ EUR}$), E-06 ($276/325$ vs. $302/488$ order totals) |
| `python need-to-fix/verify_scripts/verify_unverified_items.py` | Reproduces and verifies P-17 (coincident $E_2$ & Motta DOI resolution), P-18 (isotherm & dead code), P-19 (fail-open perfect stack runtime test), P-20 (cyber-physical time mismatch), M-05 (10 ms vs 6 s sleep & agent count regex bug), M-07 (zero PLC/hardware interfaces), M-09 (0x10 comms error & cancel "ok" pass), D-06 (snapshot drift), T-03 (tracked lockfile & 1.3 GB pickles), and resolves Bitay / Yonkist literature citations |
| `python scripts/check_proto_sync.py` | Verifies byte-identity of the 3 `sim_bridge.proto` copies |
| `git grep -n "phase4_monte_carlo_secure_key"` | Reproduces T-02 (3 self-matches in `tests/test_repo_hygiene.py` and `need-to-fix/SPEC-baseline-freeze.md`) |