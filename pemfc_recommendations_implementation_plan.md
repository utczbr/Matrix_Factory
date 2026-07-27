# Implementation Plan: PEMFC Digital Twin — §6 Recommendations

**Source document:** *From Discrete Assembly to Physically Grounded Certification: A Full-Pipeline Academic Analysis of the Matrix_Factory PEM Fuel-Cell Digital Twin (Stations 1–5)* — `pemfc_report.tex`, §"Recommendations for Improvement"
**Target codebase:** [`utczbr/Matrix_Factory`](https://github.com/utczbr/Matrix_Factory) (`main`, verified against the current tree while drafting this plan)
**Scope:** turn the report's nine recommendations into a sequenced, file-level engineering plan — what changes, where, in what order, with what tests, and at what cost.

---

## 1. How to read this plan

Each of the report's nine recommendations gets its own section with the same structure:

- **Addresses** — which numbered Physical Gap (§"Physical Gaps & Limitations") it closes, if any.
- **Current state** — exact files/functions/lines as they exist in `main` today.
- **Target design** — the equation or mechanism from the report, translated into an interface.
- **Implementation tasks** — an ordered checklist of concrete edits.
- **Test plan** — what a reviewer should be able to run to confirm the change is correct.
- **Effort** — T-shirt size against the scale below.
- **Depends on** — other recommendations that should land first.

**Effort scale** (single engineer, focused time, excludes review/CI latency):

| Size | Range | Meaning |
|---|---|---|
| S | 1–3 days | Localized change, existing test patterns apply |
| M | 1–2 weeks | New interface/proto field(s), moderate new test surface |
| L | 3–6 weeks | New physical submodel, cross-language (Java+Python) wiring |
| XL | 6+ weeks / multi-sprint | New subsystem or open-ended modeling research |

Recommendations are renumbered **R1–R9** below in the report's own listed order (not implementation order — see §2 for sequencing).

| # | Report title | Addresses | Effort |
|---|---|---|---|
| R1 | Microstructure-Grounded, Exposure-Normalized Quality Mapping | Gap 5 | M |
| R2 | 1D Dynamic Membrane Hydration (λ Model) | Gap 3 | XL |
| R3 | Dynamic ECSA & Catalyst Kinetic Parameterization | Gap 2 | L |
| R4 | Transient Electro-Thermal Batch Coupling | Gap 4 | L |
| R5 | CoolProp/LUT Thermodynamic Partial-Pressure Coupling into Nernst | Gap 8 | M |
| R6 | First-Principles Process Models for Stations 1–4 | Gap 6 | XL |
| R7 | Cathode Air-Supply Balance-of-Plant Subsystem | Gap 7 | L |
| R8 | Idempotent, Non-Destructive Quality-Profile Access | Gap 9 | S |
| R9 | Automated Cross-Validation Harness for `numba_ops.py` | parity gap (§"Compiled/Interpreted Numerical Parity") | S/M |

Two scope notes worth flagging up front rather than burying in the appendix:

- **Gap 1** (*Lumped Stack Uniformity — No Cell Heterogeneity*) has **no corresponding recommendation** in the report's list of nine. The report's own framing ("nine recommendations, ordered to match §Physical Gaps") is approximate — R9 in the list actually closes the separate parity gap, not a numbered physical gap, and cell-level heterogeneity is left open. This plan treats that as an intentional deferral rather than an omission to silently patch; §12 sketches what closing it would look like if it's wanted later.
- **§13 (Addendum)** adds a tenth item, **R10**, sourced not from the report but from a delivered code artifact (`stage1_stage2_physics_corrected.py`) that materially accelerates Phase 6 and unblocks parts of R1 and R2. It's appended after the original plan rather than folded into §1's table, to keep that table an honest 1:1 mirror of the report's own nine.
- The report's own **Conclusion** already states a priority order: *"prioritizing the idempotency fix and the compiled/interpreted parity harness as the lowest-effort, highest-integrity gains."* That's R8 and R9. This plan follows that instruction literally — see §2.

---

## 2. Sequencing rationale

Rather than working the list top-to-bottom, group by what the change actually touches, because several recommendations edit the **same choke points**:

- `calculate_pemfc_voltage` / `batch_polarization_sweep` (in `physical_engine/factory_simulation/pemfc_model.py`) are touched by R3 and R4 — both change what gets passed into the Numba-JIT kernel signature.
- `calculate_nernst_potential` and the `BatchTestRequest`/`AdvanceTime` activity computation (in `pemfc_model.py` and `physical_engine/sim_bridge_server.py`) are touched by R2 and R5 — both change how `a_h2`/`a_o2` are derived.
- `DatabaseArtifact.getQualityProfile` / `QualityProfile` (in `src/main/java/factory/DatabaseArtifact.java`) and `TestBenchArtifact.processOrder` are touched by R1 and R8 — same method, same call site.

Doing the members of each group together avoids two rounds of proto/signature churn on the same function. Sequencing:

```
Phase 0  (days)      R8  Idempotency fix
                      R9  Parity harness   [independent of R8, run first as a CI safety net
                                             before any kernel touches begin in later phases]

Phase 1  (~1 wk)      R1  Quality mapping normalization   [same files as R8, do right after]

Phase 2  (~1–2 wk)    R5  CoolProp/LUT → Nernst coupling  [wires already-built infra, no new physics]

Phase 3  (~4–8 wk)    R4  Transient thermal coupling       [bundle: both touch the pemfc_model.py
                      R3  Dynamic ECSA                      kernel signature + BatchTestRequest proto]

Phase 4  (~8–12 wk)   R2  Membrane hydration (λ model)     [depends on R5's RH plumbing]

Phase 5  (~4–6 wk)    R7  Cathode BOP subsystem             [benefits from R5's RH/partial-pressure work]

Phase 6  (parallel,   R6  Station 1–4 first-principles pilot [independent track; its Station 2
          open-ended)                                        catalyst-loading pilot output is what
                                                               would make R3's ECSA input "real"
                                                               instead of test-supplied]
```

Phase 6 (R6) can start in parallel with Phase 1 onward since it lives in a different part of the codebase (Java `BaseStationArtifact` / new Python station-physics modules) and has no upstream dependency on the Station 5 kernel work — but its *payoff* compounds if R3 has already landed, since a real per-stack ECSA distribution needs somewhere to plug into.

---

## Phase 0 — Integrity fixes

### R8 — Idempotent, Non-Destructive Quality-Profile Access

**Addresses:** Gap 9 — *"the single highest-priority defect identified in this report."*

**Current state**

`src/main/java/factory/DatabaseArtifact.java:132-144`, `getQualityProfile` performs a **consuming read**:

```java
QualityProfile p = qualityProfilesCache.asMap().remove(stackId);
if (p == null) p = QualityProfile.EMPTY;
```

`TestBenchArtifact.processOrder` (`src/main/java/factory/TestBenchArtifact.java:82-92`) calls this exactly once, on every attempt, before building `BatchTestRequest`. `order_holon.asl:141-153` retries a failed step unconditionally and indefinitely — there is currently **no scrap/rework or max-retry mechanism anywhere in the agent layer** (checked: no `scrap`/`retry_count`/`give_up` logic exists in `order_holon.asl` or `resource_holon.asl`). So the report's second option for a terminal event ("an explicit scrap/rework decision") has no existing hook to attach to today; the only real terminal event in the current system is a confirmed **pass**.

Practical consequence: attempt 1 zeroes the cache regardless of outcome; attempt 2 (on failure) always sees `QualityProfile.EMPTY` and always passes.

**Target design**

- Reads become non-destructive (`asMap().get()`), so a retried stack still sees its accumulated defect/variance profile.
- Invalidation becomes an explicit, separate operation, fired only when Station 5 has actually accepted the stack (`passed == true`) — the one terminal event that exists in the current agent design.
- On failure, the entry is deliberately **left in place** (not re-incremented — Stations 1–4 aren't revisited on a Station-5-only retry, since `call_for_proposals` re-solicits the same recipe `Step` and only Station 5 can bid for it). The 30-minute `expireAfterAccess` TTL continues to serve its original purpose: reclaiming stacks that never return (e.g., ADACOR Phase-1 suspend/abort mid-test).

**Implementation tasks**

1. `DatabaseArtifact.java`: rename semantics of the read path.
   ```java
   @OPERATION
   public void peekQualityProfile(String stackId, OpFeedbackParam<Integer> defectCount,
                                   OpFeedbackParam<Integer> stationsVisited,
                                   OpFeedbackParam<Double> cumulativeVarianceRatio) {
       QualityProfile p = qualityProfilesCache.asMap().get(stackId);   // non-destructive
       if (p == null) p = QualityProfile.EMPTY;
       defectCount.set(p.defectCount());
       stationsVisited.set(p.stationsVisited());
       cumulativeVarianceRatio.set(p.cumulativeVarianceRatio());
   }

   @OPERATION
   public void invalidateQualityProfile(String stackId) {
       qualityProfilesCache.asMap().remove(stackId);
   }
   ```
   Keep the old `getQualityProfile` name as a deprecated alias for one release if other call sites exist (grep first — currently `TestBenchArtifact` is the only caller), or do a straight rename in one PR since it's a single call site.
2. `TestBenchArtifact.java:82-92` (fetch call): swap to `peekQualityProfile`.
3. `TestBenchArtifact.java` `onMessage` callback (the block that currently does `boolean passed = resp.getPassed(); ... currentSummary = passed ? ...`): after confirming `passed == true`, add:
   ```java
   execLinkedOp(databaseArtifactId, "invalidateQualityProfile", stackId);
   ```
   guarded the same way `execInternalOp("handleResult", ...)` already is (best-effort, log-and-continue on exception — don't fail a passed test because cache cleanup hiccuped).
4. No proto change, no Python-side change — this is entirely within `DatabaseArtifact.java` + `TestBenchArtifact.java`.

**Test plan**

- New JUnit test on `DatabaseArtifact`: record two defect events for a stack, `peekQualityProfile` twice in a row, assert both reads return `defectCount == 2` (proves non-destructive).
- New JUnit/CArtAgO integration test simulating the actual bug scenario: record a defect → simulate a failed Station-5 test (don't call invalidate) → `peekQualityProfile` again → assert the profile is *still* non-empty (this is the regression test for the exact bug described in §"Idempotency of the Consuming-Read Quality Cache Under Contract-Net Retry").
- Extend `physical_engine/factory_simulation/quality_bridge_test.py` conceptually is not needed — that file exercises `RunBatchTest` in isolation and never touches the Java cache, so this fix is purely Java-side; the existing Python quality-bridge tests are unaffected and should still pass unchanged (regression check).
- Manual/system-level check: rerun the existing `SeededReplayTests.java` / `SystemIntegrationTests.java` in `src/test/java/factory/` to confirm no behavioral change to the non-retry, single-pass path (bit-for-bit replay should be unaffected since seeding is untouched).

**Effort:** S (1–2 days including tests).
**Depends on:** nothing. **Blocks:** R1 (same files).

---

### R9 — Automated Cross-Validation Harness for `numba_ops.py`

**Addresses:** the "Compiled/Interpreted Numerical Parity: An Unverified Assumption" finding (§"Mathematical & Numerical Fidelity"), called out in the report's Conclusion alongside R8 as the two lowest-effort/highest-integrity fixes.

**Current state**

- `physical_engine/optimization/numba_ops.py` is a shim: it imports from the compiled `_numba_ops_core` (built from `_numba_ops_core.pyx` via Cython) if available, else falls back to `_numba_ops_core_python.py`, gated by `H2PLANT_HARDENED`.
- `.github/workflows/ci.yml` already runs `cythonize -i physical_engine/optimization/_numba_ops_core.pyx` and executes `pytest physical_engine/` under **both** `H2PLANT_HARDENED=0` and `H2PLANT_HARDENED=1` — so the compiled extension **is** built and present in CI today. The missing piece is not build infrastructure; it's a test that actually compares the two code paths' outputs.
- `physical_engine/optimization/test_numba_ops.py` currently has exactly **two** test functions (`test_pem_voltage_jit`, `test_compression_work`), both importing directly from `physical_engine.optimization._numba_ops_core_python` — bypassing the `numba_ops` shim entirely, and never touching `_numba_ops_core` at all.
- `numba_ops.__all__` currently lists **73 names**: 10 module-level constants, 2 private numeric helpers (`_compute_T_out_for_P_jit`, `_integral_cp` — `_antoine_psat_water` is a third, listed but not present as a standalone constant/private split in the shim's explicit re-export block), and **61 public callable kernels**. None of the 61 are currently exercised against both implementations.

**Target design**

A parametrized, `hypothesis`-driven parity suite that, for every exported *callable* kernel (constants excluded — they're identical Python objects by construction, not computed), generates randomized inputs within a physically valid domain, calls both `_numba_ops_core.<fn>` and `_numba_ops_core_python.<fn>` with identical arguments, and asserts `np.allclose` (with a per-kernel tolerance, since some kernels return arrays/tuples).

**Implementation tasks**

1. Add `hypothesis` to `requirements.txt` (not currently a dependency).
2. Create `physical_engine/optimization/parity_test.py`:
   - Import both `_numba_ops_core` and `_numba_ops_core_python` directly (not through the `numba_ops` shim, so the test is explicit about which two things are being compared).
   - Skip the whole module with a clear message if `_numba_ops_core` fails to import (e.g., local dev environment without a Cython build) rather than failing — CI always has it built, so CI is where this gates merges.
   - Define one `hypothesis.strategies` input generator per kernel *signature shape* (many kernels share a shape — e.g., `(j, T, P_op, R, F, z, alpha, j0, j_lim, delta_mem, sigma_base, P_ref)` for the PEM-voltage family — so this is closer to ~15–20 distinct strategies than 61, since several kernels can share a generator via `st.builds` composition). Bound each physically: current density `j ∈ (1e-6, 5.0)`, temperature `T ∈ (250, 420)` K, pressure `P ∈ (1e4, 1e8)` Pa, mass fractions summing to 1, etc. — pull the bounds from each kernel's existing docstring/usage in `pem_physics.py`, `compressor.py`, `h2_tank.py` rather than inventing new ones.
   - For each kernel: `@given(<strategy>)` + `@settings(max_examples=200, deadline=None)` (Numba JIT compilation on first call is slow; disable Hypothesis's per-example deadline rather than tune it away).
   - Array/tuple-returning kernels: compare element-wise with `np.allclose(..., rtol=1e-9, atol=1e-12)` as a default, with documented per-kernel overrides where a kernel intentionally uses a coarser numerical method on one side (if any are found during implementation — flag and fix rather than loosen the tolerance silently).
3. Wire a coverage check: a small `test_all_kernels_covered` test that diffs `numba_ops.__all__`'s public-function subset against the set of kernel names referenced by the parity suite's `@given`-decorated tests, failing loudly if a newly-added kernel in `numba_ops.py` has no corresponding parity test. This is what "gates CI merges" in the report's language actually means in practice — otherwise the suite silently stops being comprehensive as the module grows.
4. `ci.yml`: no change needed structurally — `pytest physical_engine/` already picks up the new file; just confirm the `H2PLANT_HARDENED=1` matrix leg still passes (it should, since parity_test.py imports `_numba_ops_core` directly, not through the hardened-gated shim).

**Test plan**

This recommendation *is* the test plan. Verification of the harness itself:

- Deliberately introduce a one-line numerical discrepancy into a Python-fallback kernel in a scratch branch, confirm `parity_test.py` fails.
- Revert, confirm it passes.
- Confirm `test_all_kernels_covered` fails if a kernel is added to `__all__` without a matching strategy (add a dummy kernel, confirm the coverage test catches it, remove the dummy).

**Effort:** S/M (3–5 days: most of the time is in defining ~15–20 input-domain strategies precisely, not in the test-runner scaffolding itself).
**Depends on:** nothing. Recommended to land **before** Phase 3 (R4/R3) starts touching kernel-adjacent code, so it's already acting as a safety net by the time higher-risk kernel changes begin. (Note: `pemfc_model.py`'s own njit functions — `calculate_pemfc_voltage`, `batch_polarization_sweep`, etc. — are self-contained in that module and are **not** part of the `numba_ops.py` compiled/interpreted shim, so R9 does not cover them; `pemfc_test.py` already covers that module's own correctness separately.)

---

## Phase 1 — Quality-bridge correctness

### R1 — Microstructure-Grounded, Exposure-Normalized Quality Mapping

**Addresses:** Gap 5 — heuristic, unnormalized quality bridge mapping.

**Current state**

`src/main/java/factory/TestBenchArtifact.java:82-100`:
```java
OpFeedbackParam<Integer> stationsVisitedParam = new OpFeedbackParam<>();
...
execLinkedOp(databaseArtifactId, "getQualityProfile", stackId,
        defectCountParam, stationsVisitedParam, varianceRatioParam);
int defectCount = defectCountParam.get();
double cumulativeVarianceRatio = varianceRatioParam.get();
// stationsVisitedParam.get() is never called
rInternalPenalty += defectCount * 0.08;
rInternalPenalty += cumulativeVarianceRatio * 0.02;
activityDerate = Math.min(0.6, defectCount * 0.15);
```
`stationsVisited` is fetched from the (now, post-R1, `peekQualityProfile`) call and silently dropped. The Python-side mirror in `sim_bridge_server.py:RunBatchTest` (`r_internal_penalty_ohm_cm2`, `activity_derate_fraction` fields on `BatchTestRequest`) receives whatever raw `rInternalPenalty` the Java side computed — it has no visibility into `stationsVisited` at all, so the normalization has to happen on the Java side before the gRPC call, not in the physics engine.

**Target design (from report)**

```
ΔR_internal = 0.08 · n_defect + 0.02 · σ²_cum / max(N_v, 1)
```
plus the fuller microstructural form the report proposes as the eventual target:
```
σ_eff = σ_0 (1-ε)^m
R_internal,eff = δ_mem / σ_eff + R_contact(P_assembly)
```
The report frames the second equation as the deeper physical grounding (Bruggeman/Archie's-law effective-medium relation between assembly variance and porosity/contact resistance) and the first as the immediately implementable normalization fix. This plan splits R1 into two milestones for exactly that reason — they have very different risk/effort profiles.

**Implementation tasks**

*Milestone 1 (normalization fix — do this first, it's the load-bearing correctness fix):*

1. `TestBenchArtifact.java`: call `stationsVisitedParam.get()`, use it in the penalty formula:
   ```java
   int stationsVisited = stationsVisitedParam.get();
   rInternalPenalty += defectCount * 0.08;
   rInternalPenalty += cumulativeVarianceRatio * 0.02 / Math.max(stationsVisited, 1);
   ```
2. Unit test on the Java side (or a small pure-function extraction if the penalty math is pulled into a testable helper): given `stationsVisited = 4` vs `stationsVisited = 1` with the same `cumulativeVarianceRatio`, assert the 4-station stack gets a proportionally smaller variance penalty.
3. Re-run `quality_bridge_test.py`'s existing scenarios conceptually (that file feeds `r_internal_penalty_ohm_cm2` directly into `RunBatchTest`, so it's unaffected by *how* Java computes the penalty — but add a note in that file's docstring pointing at the Java-side normalization so a future reader doesn't think the Python engine does this normalization itself).

*Milestone 2 (microstructural R_contact / porosity model — larger, optional, defer if time-boxed):*

4. Decide where `R_contact(P_assembly)` and `ε` (porosity) get their inputs from. Neither `defectCount` nor `cumulativeVarianceRatio` currently encodes an assembly *pressure* — Station 4 ("Robotic Stack Assembly") is the physical station that would produce this, but it's currently a phenomenological Gaussian/Bernoulli surrogate (Gap 6 / R6). **This milestone is therefore gated on at least a partial R6** (a Station 4 clamping-pressure model) to have a real `P_assembly` value to feed in; without it, `R_contact` would have to be back-derived from `cumulativeVarianceRatio` as a proxy, which is exactly the kind of un-derived heuristic the recommendation is trying to move away from. **Update:** §13 (R10) delivers close to exactly this — `simulate_stage2_clamping`'s internal `p_clamp_mpa` is a real, mechanistically-computed assembly pressure, once it's added to that function's return tuple (§13.2, issue 2). This is now the recommended `P_assembly` source for Milestone 2, ahead of waiting on a full Station 4 live-integration.
5. If proceeding without waiting for R6: implement `Bruggeman/Archie` as a new pure function in `pem_physics.py` or a new `microstructure.py`, parameterized by an *assumed* porosity distribution (documented as provisional), with a clear `TODO(R6)` marking where real Station-4 output should replace it.

**Test plan**

- Java unit test for the normalization arithmetic (Milestone 1).
- Extend `quality_bridge_test.py` with a parametrized case sweeping `stationsVisited ∈ {1, 2, 4}` at fixed `cumulativeVarianceRatio`, asserting monotonic decrease in effective penalty (Milestone 1, cross-checked at the physics-engine boundary even though the normalization happens upstream in Java — this test exercises the *contract*, i.e. that a smaller `r_internal_penalty_ohm_cm2` on the wire actually produces a smaller ohmic overpotential).
- Milestone 2: property test that `R_contact` is monotonically decreasing in `P_assembly` and `σ_eff` is monotonically decreasing in `ε` (physical sanity bounds, not exact-value tests, since there's no ground-truth dataset yet).

**Effort:** M (Milestone 1: 2–3 days; Milestone 2: 2–3 weeks, and only if not deferred to sit behind R6).
**Depends on:** R8 (same files/call site — do this fix on top of R8's `peekQualityProfile`, not the old `getQualityProfile`, to avoid a merge conflict on the same lines).

---

## Phase 2 — Wire existing infrastructure

### R5 — CoolProp/LUT Thermodynamic Partial-Pressure Coupling into the Nernst Term

**Addresses:** Gap 8 — disconnected real-gas/CoolProp layer.

**Current state**

- `physical_engine/optimization/lut_manager.py` (`LUTManager`, `LUTConfig`) and `physical_engine/optimization/coolprop_lut.py` (`CoolPropLUT`) are fully operational and already used by `h2_tank.py`'s `TankArray` (density inversion) and indirectly by `compressor.py`. Neither is imported by `pemfc_model.py`.
- `calculate_nernst_potential` (`physical_engine/factory_simulation/pemfc_model.py`) takes `a_h2`, `a_o2` as plain floats, unitless activities already computed *before* the call.
- Those activities are computed in two places, both bypassing any real-gas/CoolProp logic entirely:
  - `sim_bridge_server.py::AdvanceTime` (around line 228): `a_o2 = 1.0` hardcoded constant; `a_h2` taken straight from `H2_TANK_PRESSURE_BAR` state, clipped to `[0.5, 10.0]`.
  - `sim_bridge_server.py::RunBatchTest` (around line 316): `a_h2 = np.clip(request.inlet_pressure_h2_bar * 1e5 / P_ref, 0.5, 10.0)`, `a_o2` likewise from `inlet_pressure_o2_bar` — simple pressure ratios, no fugacity correction, no water-vapor partial pressure subtraction.
- `SimBridgeServicer.__init__` already constructs and warms an `LUTManager` instance (`self._lut`) for the tank — it is sitting right there, unused by the electrochemistry.

**Target design (from report)**

```
P_H2 = P_in,anode − RH_anode · P_sat(T)
a_H2 = φ_H2 · P_H2 / P_ref
```
(symmetric form for O2/cathode once R7 exists; until then, treat the cathode side as dry air at fixed RH=0 as an explicit, documented simplification rather than an implicit one).

**Implementation tasks**

1. Add a `RH_anode` field (default `0.0`, i.e. bone-dry, backward compatible) to `BatchTestRequest` in `physical_engine/protos/sim_bridge.proto` (pattern-match the existing `r_internal_penalty_ohm_cm2` field's doc comment style), regenerate `sim_bridge_pb2.py`/`sim_bridge_pb2_grpc.py`, and the Java stub side (`SimBridgeProto`) — this is a proto field addition, not a state-vector change, so `ProtoIndex.java`/`ThermoStateIndex` are untouched here.
2. New pure function in `pem_physics.py` or directly in `lut_manager.py`: `water_vapor_partial_pressure(T, RH) -> P_sat` using `self._lut.lookup(...)` for H2O against the existing LUT grid (already covers H2O per the report's fluid list), falling back to `CoolPropLUT.PropsSI` for out-of-LUT-bounds queries (mirroring the two-tier pattern `TankArray` already uses).
3. New function `real_gas_activity(P_species, T, fluid) -> (a, phi)` computing the fugacity coefficient via CoolProp/LUT and returning both the corrected activity and the raw φ (for telemetry/debugging).
4. Modify `SimBridgeServicer` to hold a reference the Nernst-computation call site can use (it already has `self._lut` — thread it through to wherever `a_h2`/`a_o2` are computed in both `AdvanceTime` and `RunBatchTest`, replacing the direct pressure-ratio clip with a call to the new function).
5. `calculate_nernst_potential`/`calculate_pemfc_voltage` in `pemfc_model.py` stay untouched in signature — they still just take `a_h2`, `a_o2` as floats. This keeps the change contained to the *caller* (sim_bridge_server.py), not the JIT-compiled kernel, which is the lower-risk order of operations (no Numba signature/type-inference changes in this phase).
6. Explicitly document (code comment + this plan) that cathode-side RH is fixed at 0 until R7 lands, so `a_o2`'s fugacity correction currently only reflects total-pressure→fugacity, not humidity — avoids silently overclaiming symmetry that R7 hasn't built yet.

**Test plan**

- Unit tests for `water_vapor_partial_pressure` and `real_gas_activity` against known CoolProp reference values at a few `(T, RH)` points (e.g., 80 °C, RH=0.8 — check against a hand/CoolProp-computed `P_sat` independently).
- Regression: at `RH_anode = 0.0` (the new field's default), confirm `RunBatchTest`/`AdvanceTime` produce **bit-identical** voltages to pre-change behavior for a fixed request — this is the backward-compatibility contract, analogous to how `quality_bridge_test.py::test_missing_penalty_fields_default_to_zero` already protects the existing penalty fields.
- New test: increasing `RH_anode` at fixed total pressure should *decrease* `a_h2` (less H2 partial pressure available) and therefore *decrease* `E_ocv` — a monotonicity check against `calculate_nernst_potential`.
- Extend `pemfc_test.py::TestNernstPotential` is intentionally **not** touched — that module's activity-bounds validation (`0.5 ≤ a_h2 ≤ 10.0`) stays exactly where it is; the new real-gas correction happens strictly upstream of it, in `sim_bridge_server.py`.

**Effort:** M (1.5–2 weeks: mostly proto/codegen plumbing and cross-language regeneration, the physics itself is a direct application of already-built LUT infrastructure).
**Depends on:** nothing structurally, but do this before R2 (membrane hydration) — R2's water-transport boundary conditions want RH available, and this phase is what makes RH a first-class input to the system.

---

## Phase 3 — Core kernel extension (thermal + kinetics, bundled)

These two are grouped because both change the `batch_polarization_sweep` / `calculate_pemfc_voltage` call signature and the `BatchTestRequest` proto — doing them as one migration avoids two separate rounds of Numba re-compilation-signature churn and two separate proto-field-addition PRs.

### R4 — Transient Electro-Thermal Batch Coupling with a Stability-Aware Integrator

**Addresses:** Gap 4 — thermal self-heating decoupled from the EOL sweep.

**Current state**

- `batch_polarization_sweep` (`pemfc_model.py`, `@njit(nogil=True, cache=True, parallel=True)`) takes a single static `T` for the whole 12-point sweep. It has no notion of thermal state.
- `RunBatchTest` (`sim_bridge_server.py:293-390`) does simulate *wall-clock* pacing (`time.sleep(0.5)` per point, mirroring `j`/`V` into `_state` for telemetry) but never calls `self._thermal.step(...)` during the sweep — that only happens in `AdvanceTime`, which the sweep doesn't invoke.
- `StackThermalModel.step(dt, Q_gen, T_coolant)` (`stack_thermal_model.py:148-172`) is a plain-Python/NumPy forward-Euler integrator — **not** Numba-compiled — while `batch_polarization_sweep` is `@njit(parallel=True)`. This is the central architectural obstacle: you cannot call a plain-Python bound method from inside a `prange` loop in nopython mode.
- No runtime check exists against the stability bound derived in the report (`Δt < 2/λ_max`), Eq. for `euler_stability`. **Correction/addition (verified against the live repo, not assumed from the report alone):** `StackThermalModel` already has a *different*, already-implemented validity check — `validate_yonkist(q_gen_volumetric, delta_T)` (`stack_thermal_model.py:109-142`), backed by a dedicated `TestYonkistValidation` test class in `test_stack_thermal.py`. It checks a dimensionless `Yo < Bi` condition for whether the **lumped-capacitance modeling assumption itself** holds under volumetric heat generation — a physical-validity check, not a numerical-stability one. It's currently only invoked on the `AdvanceTime` path (`stack_thermal_model.py:174-181`); nothing calls it from `RunBatchTest`, since the sweep doesn't touch the thermal model at all today. This is a second, complementary check to the forward-Euler stability guard below (one asks "is this ODE model physically appropriate here," the other asks "is this integrator numerically stable at this Δt") — the thermal-coupled sweep should invoke both, not just the new one.

**Target design (from report)**

```
C_core dT_core/dt = I(t)Σηh(t) − (T_core − T_skin)/R_th,in
C_skin dT_skin/dt = (T_core − T_skin)/R_th,in − (T_skin − T_coolant)/R_th,out
```
stepped across the sweep's current increments, with either (a) an explicit runtime assertion of the stability bound guarding the existing forward-Euler step, or (b) a switch to an unconditionally-stable integrator (2nd/4th-order Runge-Kutta or implicit trapezoidal).

**Implementation tasks**

1. **Resolve the Numba/plain-Python boundary first** — this is the actual hard part, not the ODE math. Two viable approaches; pick one deliberately rather than discovering the constraint mid-implementation:
   - **(a) JIT-compile the thermal step.** Extract `StackThermalModel.step`'s core arithmetic into a standalone `@njit` function (`_thermal_step_jit(T_core, T_skin, dt, Q_gen, T_coolant, C_core, C_skin, hA_int, hA_ext) -> (T_core, T_skin)`), keep `StackThermalModel` as a thin stateful Python wrapper around it for the `AdvanceTime` path (unchanged there), and call the new `_thermal_step_jit` directly from inside `batch_polarization_sweep`'s loop.
   - **(b) Move the sweep out of `prange`.** Since thermal self-heating makes each point in the sweep *sequentially dependent* on the previous point's temperature (current point's `T` depends on prior heat accumulation), the sweep is no longer embarrassingly parallel once thermal coupling is added — this is a genuine physical constraint, not just an implementation inconvenience. **Recommendation: go with (b)** — replace `prange` with a plain sequential loop for the physically-coupled sweep, and keep the existing parallel `batch_polarization_sweep` available under its current name/signature as a static-temperature diagnostic mode (some callers, e.g. quick QC re-sweeps, may legitimately want the fast static-T approximation). Add a new `batch_polarization_sweep_thermal(...)` (or a `thermal_coupled: bool` flag with a signature branch — Numba dispatch on a boolean is fine since it's a compile-time-constant-friendly branch) that is sequential and carries thermal state across points.
2. Implement the stability guard per the report's Eq. for `euler_stability`:
   ```python
   dt_max = 2.0 / max(hA_int / C_core, (hA_int + hA_ext) / C_skin)
   if dt >= dt_max:
       raise ValueError(f"Forward-Euler thermal step unstable: dt={dt} >= {dt_max}")
   ```
   placed in `_thermal_step_jit` (or its Python wrapper, whichever is cheaper given njit's exception-raising constraints — Numba supports raising simple exceptions in nopython mode, matching the existing `raise ValueError` pattern already used in `batch_polarization_sweep`'s input-validation loop). Given the report's own estimate that default parameters keep this bound "on the order of tens of seconds," this guard should never fire under current defaults — it's there for the "future change to Δt/C/hA" scenario the report explicitly flags as currently silent.
3. **Wire the existing `validate_yonkist()` check into the sweep, not just `AdvanceTime`.** Once the sweep is carrying thermal state per-point (task 1), call `validate_yonkist(q_gen_volumetric, delta_T)` at each point alongside the new stability guard (task 2) — a high-current point late in the sweep is exactly the transient condition most likely to push `Yo` toward or past `Bi`, and today nothing would catch that during a test, only during ordinary tick-loop operation. Surface a violation the same way `AdvanceTime` already does (log + `is_valid` flag) rather than treating it as fatal — same severity level the existing call site uses, for consistency.
4. Wire `Q_gen = I·(η_act + η_ohm)` per-point inside the new sequential sweep (same formula `sim_bridge_server.py::AdvanceTime` already uses at line ~247 — reuse rather than reimplement to avoid the two call sites drifting apart).
5. `RunBatchTest`: switch to the new thermal-coupled sweep variant, threading the current `self._thermal.T_core`/`T_skin` in as the sweep's starting state and writing the *final* post-sweep state back to `self._thermal` afterward (so a stack's thermal history persists correctly into subsequent `AdvanceTime` calls after the test completes — don't let the sweep's transient excursion "vanish" and silently reset to pre-test temperature).
6. Decide whether to also offer the RK4/implicit-trapezoidal alternative integrator now or defer it: given the report frames the stability *assertion* as sufficient ("should replace the un-guarded forward-Euler step" — assertion or integrator swap, either satisfies the recommendation), **ship the assertion first** (task 2) as the P0 fix, and track the RK4 swap as a follow-up only if profiling later shows the guard actually firing under realistic parameter sweeps (e.g., a future miniaturized-stack config with smaller `C_core`/`C_skin`).

**Test plan**

- Extend `test_stack_thermal.py`: unit test `_thermal_step_jit` directly against the existing Python `StackThermalModel.step` reference implementation for numerical equivalence (this is itself a small parity check, in the spirit of R9, between the new JIT thermal core and the existing Python model it's extracted from).
- New test: stability guard raises `ValueError` when `dt` exceeds the computed bound (construct a deliberately-small `C_core` to trigger it cheaply rather than an unrealistically large `dt`).
- New test: sweep-level `validate_yonkist()` call surfaces a violation for a deliberately extreme high-`j`/low-`Bi` scenario, reusing `TestYonkistValidation`'s existing violation-triggering parameters (`test_stack_thermal.py:57-62`) as the known-bad input rather than inventing new ones.
- New integration test on `RunBatchTest`/`quality_bridge_test.py`-style harness: run the 12-point sweep at high `j` (near `j_lim`) and assert stack temperature rises monotonically across the sweep (sanity check that self-heating is actually being applied, not just present in the API).
- Confirm `pemfc_test.py::TestBatchSweep::test_consistency_with_scalar` and `test_twelve_point_sweep` still pass unchanged against the **static-T** `batch_polarization_sweep` (task 1 preserves it as-is) — this is the regression guard that the existing fast/static path isn't broken by adding the new thermal-coupled path alongside it.

**Effort:** L (3–5 weeks — the sequential/parallel restructuring and the njit/plain-Python boundary work dominate; the ODE math itself is already correct and just needs relocating).
**Depends on:** R9 ideally in place first (kernel-adjacent changes benefit from the parity safety net, even though this specific kernel isn't in `numba_ops.py`'s shim — the *practice* of having a parity-test habit in the codebase is worth establishing before this phase, not a hard technical dependency).

---

### R3 — Dynamic ECSA & Catalyst Kinetic Parameterization

**Addresses:** Gap 2 — static kinetic parameters, no direct catalyst decay.

**Current state**

`pemfc_model.py`'s `_PEMFCConstantsData` (frozen dataclass) hardcodes `j0_orr = 1e-9` and `alpha_orr = 0.5` as module-level constants, re-declared as local literals inside every `@njit` function (`calculate_pemfc_voltage`, `newton_raphson_solver`, `batch_polarization_sweep`) rather than threaded through as parameters — this is a deliberate isolation pattern (per the module's own docstring, to prevent legacy-electrolyzer parameter cross-contamination), but it also means there is currently no parameter slot for a per-stack, per-test catalyst-health input at all.

**Target design (from report)**

```
j0 = j0,ref · (ECSA_eff / ECSA_0) · exp( −E_act/R T · (1 − T/T_ref) )
```

**Implementation tasks**

1. Add `ecsa_ratio` (`ECSA_eff / ECSA_0`, default `1.0` = pristine catalyst) as an explicit new parameter to `calculate_pemfc_voltage`, `newton_raphson_solver`, and `batch_polarization_sweep`'s signatures — following the exact pattern `R_internal` already uses (a per-call float, not a module constant), since `R_internal` demonstrates this codebase's established way of threading a manufacturing-derived scalar into the kernel.
2. Add the Arrhenius-corrected `j0` computation as a small `@njit` helper (`_effective_j0(j0_ref, ecsa_ratio, T, E_act, T_ref) -> j0_eff`), called once at the top of `calculate_pemfc_voltage` in place of the current hardcoded `j0 = 1e-9` local.
3. Pick a defensible default `E_act` (activation energy for ORR on Pt/C, literature range ~20–40 kJ/mol is typical for low-temperature PEMFC ORR kinetics) — flag this explicitly as a **calibration placeholder** requiring a literature citation or experimental fit before this ships as anything beyond a structurally-correct-but-uncalibrated model. Do not silently pick a number without a comment pointing at where it should be validated.
4. `PEMFCConstants` frozen dataclass: add `ecsa_ref_e_act_j_mol` (or similar) as a new named constant alongside `j0_orr`/`alpha_orr`, keeping the existing runtime contamination guard (`z_pemfc != 4`) pattern intact and unmodified.
5. Proto: add `ecsa_ratio` (default `1.0`) to `BatchTestRequest`, mirroring `r_internal_penalty_ohm_cm2`'s doc-comment style, and thread it through `TestBenchArtifact.java` → `sim_bridge_server.py::RunBatchTest` → the kernel call. For now, `TestBenchArtifact.java` can hardcode `1.0` (no upstream signal yet — that's what R6's Station 2 pilot would eventually supply); the point of this phase is to make the *kernel and wire format* support the input, not to have a real value flowing through it yet.
6. Update `AdvanceTime`'s `calculate_pemfc_voltage` call site with the same new parameter (default `1.0` — steady-state telemetry between tests isn't testing a specific stack's catalyst health, so pristine is the right default there).

**Test plan**

- Extend `pemfc_test.py::TestPEMFCVoltage`: at `ecsa_ratio = 1.0`, assert bit-identical output to the pre-change signature (backward-compat contract — same pattern used for R5/R1's default-value regression tests).
- New test: sweep `ecsa_ratio ∈ {1.0, 0.5, 0.1}` at fixed `j`, assert `eta_act` increases monotonically as `ecsa_ratio` decreases (lower effective exchange current density → higher activation overpotential at the same current — this is the direct physical claim the recommendation makes).
- New test: confirm a sufficiently degraded `ecsa_ratio` can trip `LOW_ACTIVATION` **directly** via the kinetic path, distinct from the existing `a_h2`/`a_o2` starvation-proxy path — this is the specific improvement the report calls out ("allows Station 5 to directly detect catalyst-deposition defects... instead of only through the activity-derate heuristic").
- `quality_bridge_test.py::test_missing_penalty_fields_default_to_zero`-style test extended to also assert `ecsa_ratio` defaults to `1.0` and produces unchanged `passed`/`failure_flags` for a legacy-shaped request.

**Effort:** L (2–4 weeks — signature threading across 3 languages/layers is mechanical but touches many files; the Arrhenius term itself is small).
**Depends on:** R4 (bundle the two proto/signature changes into one migration per §2's rationale — do R4's signature work first since it's larger, then add `ecsa_ratio` to the same already-open signatures rather than reopening them twice).

---

## Phase 4 — Membrane hydration

### R2 — 1D Dynamic Membrane Hydration (λ Model)

**Addresses:** Gap 3 — omission of dynamic water & membrane hydration.

**Current state**

Membrane proton conductivity is currently folded entirely into the constant `R_internal` (`eta_ohm = j * R_internal`, `pemfc_model.py`). There is no `λ` state anywhere in the codebase — no water-content variable, no electro-osmotic drag, no back-diffusion, no GDL liquid-water saturation limit. The `eta_conc` C¹-patched logarithmic term (`eta_conc_patched` in the report) is explicitly an *artificial* numerical patch standing in for the physical liquid-water flooding limit this recommendation would replace.

**Target design (from report)**

```
σ_mem(λ, T) = (0.005139λ − 0.00326) · exp(1268 · (1/303 − 1/T)),  λ ∈ [1, 14]
```
This is the standard Springer–Zawodzinski–Gottesfeld membrane conductivity correlation. The report frames this as replacing the artificial concentration patch with physical liquid-water saturation limits.

**Implementation tasks — this is the largest single-recommendation undertaking in the report; break it into an explicit sub-sequence rather than one PR:**

1. **Model selection & literature grounding (research spike, ~1 week).** The Springer-Zawodzinski conductivity correlation above needs a companion **water-transport model** to actually produce a `λ` value to feed it — the report names "electro-osmotic drag and back-diffusion" but doesn't specify a full transport PDE. Before writing code, pin down: 1D steady-state vs. transient water-balance across the membrane thickness; drag coefficient `n_d(λ)` correlation; back-diffusion coefficient `D_λ(λ, T)` correlation. This spike's deliverable is a short design note (equations + boundary conditions), not code — get this reviewed before building against it, since a wrong transport model is much more expensive to discover after implementation than before.
2. **New module** `physical_engine/factory_simulation/membrane_hydration.py`: a `@njit`-compatible function computing steady-state (or single-step transient, matching the thermal model's own step-based pattern for consistency) `λ(x)` across `N` membrane nodes given `j`, `T`, and boundary RH (anode/cathode) — the boundary RH values are exactly what R5's `RH_anode` field (and R7's future cathode-side equivalent) supply, which is why this phase sits behind Phase 2/5 in the sequencing.
3. Replace the constant `sigma_base` term inside `eta_ohm`'s `R_internal` computation with `delta_mem / sigma_mem(λ_avg, T)` (average or minimum-λ node, per the design-spike decision), added to (not replacing) the manufacturing-derived `R_contact`/`ΔR_internal` terms from R1 — ohmic resistance becomes membrane-hydration-state **plus** manufacturing-defect penalty, not either/or.
4. Replace the artificial `eta_conc_patched` term's role: once real liquid-water saturation limits exist (from the water-transport sub-model), `j_lim` itself should become a function of local water saturation rather than the current fixed `j_lim_pemfc = 2.5` constant — this is the actual "replaces the artificial concentration patch" claim in the recommendation. Keep the existing C¹ patch as a numerical-safety net regardless (singularity protection is good practice independent of what determines `j_lim`'s value), but let `j_lim` itself vary with the hydration state. **Note:** §13 (R10) surfaces a second, independent candidate input here — `simulate_stage2_clamping`'s `gdl_porosity`/`e_tangent_mpa` outputs are a mechanically-derived GDL compression state that could feed `j_lim(saturation)` alongside (not instead of) this phase's own water-transport sub-model. Treat as an optional enrichment to evaluate once both exist, not a dependency.
5. Decide on state ownership: does `λ(x)` persist across `AdvanceTime` calls like `StackThermalModel`'s temperature state does (a `MembraneHydrationModel` class instantiated once per `SimBridgeServicer`, analogous to `self._thermal`), or is it recomputed fresh per call assuming fast equilibration relative to the tick rate? Given the thermal model's precedent (persistent state, stepped each tick), **persistent state is the more consistent architectural choice** — document the equilibration-timescale assumption either way.
6. Wire into both `AdvanceTime` and `RunBatchTest`/the R4 thermal-coupled sweep — since `λ` depends on `T` (via `sigma_mem(λ,T)`) and `j` (via drag), and R4 already made the sweep sequential/stateful, adding `λ` as a second piece of carried-forward state through the same per-point loop is a natural (if substantial) extension of R4's restructuring rather than a third parallel state-threading effort.

**Test plan**

- Unit tests for `sigma_mem(λ, T)` against known reference points from the Springer-Zawodzinski literature (e.g., λ=14, T=353.15K has a well-documented reference conductivity value — validate against that, not against a self-consistency check alone).
- Property tests: `σ_mem` monotonically increasing in `λ` over `[1,14]`; monotonically increasing in `T` (matches the existing `TestNernstPotential::test_temperature_dependence` style already used elsewhere in the test suite for the analogous Nernst monotonicity check).
- Boundary tests: `λ → 1` (dry membrane) should push `R_internal` sharply upward and `V_stack` down; `λ → 14` (fully hydrated) should approach the current model's baseline behavior at a comparable `sigma_base` — i.e., confirm the new dynamic model degenerates sensibly toward the old static-conductivity behavior at "normal" operating hydration, which is the concrete regression check that this recommendation strictly *adds* fidelity rather than silently changing baseline QC pass rates.
- Integration test: a sweep starting from a dry membrane should show `V_stack` recovering (λ rising toward equilibrium) as the sweep progresses at moderate current, if the transport sub-model's timescale is fast relative to the sweep's ~0.5s/point pacing — or, if the spike concludes equilibration is *not* fast relative to that pacing, this is itself an important finding to surface (it would mean Station 5's 0.5s/point pacing needs re-examination independent of this recommendation).

**Effort:** XL (8–14 weeks — this is genuinely the most open-ended item; the research spike's conclusions could meaningfully change the size of the implementation task, so the estimate has wide error bars until that spike completes).
**Depends on:** R5 (RH plumbing), R4 (sequential/stateful sweep architecture to extend).

---

## Phase 5 — Cathode Balance-of-Plant

### R7 — Cathode Air-Supply Balance-of-Plant Subsystem

**Addresses:** Gap 7 — fixed cathode oxidant supply.

**Current state**

- `sim_bridge_server.py::AdvanceTime`: `a_o2 = 1.0` hardcoded.
- `TestBenchArtifact.java::processOrder`: `double pO2Bar = 2.0;` hardcoded local, sent on every `BatchTestRequest` regardless of actual conditions.
- The H2 side has a real, symmetric pattern to mirror: `TankArray` (`h2_tank.py`, ~45 lines, real-gas density inversion via `LUTManager` with an ideal-gas fallback) and `CompressorStage` (`compressor.py`, ~17 lines, wraps `numba_ops.calculate_compression_work`). Both are small, self-contained classes instantiated once in `SimBridgeServicer.__init__` (`self._tank = TankArray(...)`, `self._compressor = CompressorStage()`).
- The shared Java/Python state-vector contract (`ThermoStateIndex` in `physical_engine/proto_index.py`, mirrored by `ProtoIndex.java`) is currently a fixed 9-element vector. `ProtoIndex.java` **already contains an explicit runtime check and warning message** for exactly this situation:
  ```java
  throw new IllegalStateException(
      "thermo_state_vector length mismatch: expected " + VECTOR_LENGTH
      + ", got " + actualLength + ". Sync proto_index.py with ProtoIndex.java and redeploy all daemons.");
  ```
  Any new BOP state (O2 pressure, blower power, cathode RH) that needs telemetry visibility must extend this vector on **both** sides in lockstep — this is a known, already-guarded seam in the codebase, not a new risk this plan introduces.

**Target design (from report)**

A `BlowerStage` + humidifier, analogous to `CompressorStage`/`TankArray`, replacing the fixed `a_o2=1.0`/`pO2Bar=2.0` constants with a stoichiometric-excess-ratio-driven supply pressure and RH state.

**Implementation tasks**

1. New `physical_engine/factory_simulation/blower.py`, mirroring `compressor.py`'s structure exactly:
   ```python
   class BlowerStage:
       """Cathode air supply: stoichiometric-excess-ratio-driven O2 delivery,
       symmetric with CompressorStage on the H2 side."""
       def __init__(self, stoich_ratio: float = 2.0, ambient_rh: float = 0.5):
           self.stoich_ratio = stoich_ratio
           self.ambient_rh = ambient_rh

       def supply_pressure_bar(self, I_total_a: float, N_cells: int) -> float:
           # O2 demand from Faraday's law (z=4), scaled by stoich_ratio,
           # converted to required blower discharge pressure.
           ...
   ```
   Keep it this small and focused deliberately — `CompressorStage` is 17 lines and does one thing well; this should follow that precedent rather than growing into a general BOP framework on its own.
2. New `physical_engine/factory_simulation/humidifier.py` (or fold into `blower.py` if the design spike from R2 concludes cathode RH is simple enough not to warrant a separate module) — computes cathode-side RH analogous to what R5 built for the anode, reusing R5's `water_vapor_partial_pressure`/`real_gas_activity` functions rather than reimplementing them.
3. Extend `BatchTestRequest` (proto) with `stoich_ratio` (or compute supply pressure server-side from a fixed default and drop the need for a new field — decide based on whether Station 5 test conditions should be caller-configurable or server-fixed; the existing `inlet_pressure_o2_bar` field already exists on the proto and is currently just... hardcoded by the Java caller. **The cheapest correct fix that doesn't require any proto change at all**: have `TestBenchArtifact.java` compute `pO2Bar` from a real stoichiometric calculation instead of the literal `2.0`, using the same current-density/cell-count inputs it already has, before this field ever reaches the wire. This is worth calling out explicitly as an option because it delivers real value without Phase 5's full new-subsystem scope.)
4. For the `AdvanceTime` (continuous telemetry) path: instantiate `BlowerStage` in `SimBridgeServicer.__init__` alongside `self._compressor`, extend `ThermoStateIndex`/`ProtoIndex.java` with `O2_SUPPLY_PRESSURE_BAR`, `BLOWER_POWER_KW`, `CATHODE_RH` (3 new indices, `_VECTOR_LENGTH` 9→12), update `validate_vector`/`validateVectorLength`, update `MainSimulator.assembleTelemetryFrame` (Java) and the `.proto` `thermo_state_vector` consumer to read the new indices, and update `TelemetryHub`/dashboard consumers if the frontend surfaces these fields (check `visualization/dashboard.js` for any hardcoded assumption about vector length before shipping).
5. Replace `a_o2 = 1.0` in `AdvanceTime` with `self._blower.compute(...)`-derived value.

**Test plan**

- Unit tests for `BlowerStage`/humidifier against hand-calculated stoichiometric O2 demand at a few `(I_total, N_cells, stoich_ratio)` points, same style as `compressor.py`'s implicit validation via `calculate_compression_work`'s existing formula.
- `ProtoIndex.java`/`ThermoStateIndex` vector-length regression test: confirm both sides agree on `_VECTOR_LENGTH`/`VECTOR_LENGTH == 12` post-change (a trivial but load-bearing test given the existing runtime guard's own warning text).
- End-to-end: confirm `MainSimulator`'s telemetry frame assembly and the WebSocket/dashboard path don't throw or silently truncate on the longer vector — this is exactly the kind of cross-language contract break the existing `IllegalStateException` message anticipates, so exercise it directly rather than trusting the guard alone.
- Regression: at default `stoich_ratio=2.0`/current defaults, confirm resulting `a_o2` stays within a range that doesn't change any existing `pemfc_test.py`/`quality_bridge_test.py` pass/fail outcomes unexpectedly — flag (don't silently absorb) any QC-threshold shift this causes, since Station 5's certification behavior changing is a consequential, visible change that stakeholders should sign off on rather than discover.

**Effort:** L (4–6 weeks, mostly the cross-language state-vector extension and telemetry/dashboard follow-through rather than the physics itself, which is a straightforward stoichiometric calculation).
**Depends on:** R5 (reuses its water-vapor/fugacity functions for cathode RH).

---

## Phase 6 — Upstream station physics (parallel track)

### R6 — First-Principles Process Models for Stations 1–4

**Addresses:** Gap 6 — purely phenomenological Stations 1–4.

**Current state**

`physical_engine/factory_simulation/station_stochastics.py` defines `STATION_PARAMS: Dict[int, StationParameters]` — four stations, each just `(name, t_mean_s, t_std_s, defect_rate)`. The module's own docstring is explicit that these are *"validation references for the Phase 1 physical engine — actual stochastic sampling occurs on the JVM side"* via `BaseStationArtifact.java`'s truncated-Gaussian + Bernoulli draw. There is no mechanistic model anywhere for hot-press lamination, catalyst-ink deposition, stamping tolerance stack-up, or clamping-pressure distribution — this is confirmed exactly as the report describes it.

**Target design (from report)**

The report itself scopes this conservatively: *"Even a partial, single-station pilot would let the digital twin validate whether its aggregate statistical calibration... is consistent with a bottom-up physical model."* It names three candidate models: a hot-press cure-kinetics model (Station 1), an areal catalyst-loading uniformity model (Station 2, explicitly noted as feeding R3's ECSA), and a stamping force/tolerance-stack-up model (Station 3).

**Implementation tasks**

Follow the report's own scoping: **pilot one station, not all four.** Recommend **Station 2 (Catalytic Deposition)** as the pilot, for a concrete reason this plan can state explicitly: it's the only one of the three candidate models with a *downstream consumer already planned* — R3's `ecsa_ratio` input. A Station 1 or Station 3 pilot would be scientifically interesting but would dead-end without a corresponding "R-something" to consume its output; Station 2's output has a home.

**Update:** §13 (R10) below adds a second candidate pilot — Stations 3 & 4 (stamping/clamping) — that has the same property (a planned downstream consumer, R1 Milestone 2 and R2) and is materially further along, since working kernel code already exists pending calibration data and a station-identity fix. Given that head start, §13.4 recommends treating Stations 3–4 as the track that actually ships first, with this Station 2 pilot following once that lands.

1. **Research spike (2–3 weeks):** slot-die coating-speed variance → local ECSA distribution. Needs: a coating-speed/loading-uniformity correlation (literature-grounded — catalyst-ink rheology and drying kinetics are an active research area; this is not something to derive from first principles in-house without domain literature) and a way to map a *distribution* of local ECSA values across the active area down to the single scalar `ecsa_ratio` R3's kernel consumes (mean? worst-case percentile? area-weighted average?). This choice materially affects how conservative Station 5's resulting `LOW_ACTIVATION`/kinetic penalty is, so it deserves explicit sign-off before implementation, not an implicit default.
2. New Python module (e.g., `physical_engine/factory_simulation/station2_catalyst_deposition.py`) implementing the chosen model, callable both as a standalone validation script (to compare its aggregate output distribution against `STATION_PARAMS[2]`'s current `t_mean_s=12.0, t_std_s=15.0, defect_rate=0.012` — this is literally the validation the report asks for: "consistent with a bottom-up physical model") and as a per-stack ECSA-ratio generator.
3. Java-side integration is the larger question: does `BaseStationArtifact.java` gain a mechanistic mode (calling out to the Python physical engine via a new/extended gRPC method, mirroring how Station 5 already calls out to Python) or does the mechanistic model stay Python-side-only as an offline calibration/validation tool feeding *updated* `STATION_PARAMS` constants rather than running per-stack in the live simulation loop? **Recommend starting with the latter** (offline calibration tool) as the pilot's actual deliverable — it satisfies the report's stated validation goal without requiring a new synchronous Station-1-4-to-Python RPC path (which would be a structural change to the currently pure-Java-stochastic Stations 1-4, a much bigger architectural commitment). If the pilot's findings justify it, a live per-stack mechanistic Station 2 (with its own `RunStation2Test`-style gRPC call, `getQualityProfile`-analogous data flow into `ecsa_ratio`) becomes a well-justified Phase 6b, not a Phase-6a assumption.
4. Feed the pilot's per-stack ECSA output (once/if Phase 6b exists) into `TestBenchArtifact.java`'s `ecsa_ratio` field (currently hardcoded to `1.0` per R3 task 5) via the same `getQualityProfile`-style Database bridge pattern R1/R8 already established — i.e., Station 2 would call a new `recordCatalystQuality`-analogous op, and Station 5 would fetch it alongside the existing defect/variance profile.

**Test plan**

- Research spike deliverable is a design note + a standalone offline script comparing the mechanistic model's aggregate output distribution (mean/variance of simulated "effective ECSA" or "defect-equivalent" outcomes) against the existing `STATION_PARAMS[2]` calibration — the acceptance criterion is *"consistent with,"* per the report's own phrasing, not exact replication.
- If Phase 6b (live integration) proceeds: full regression suite on `SeededReplayTests.java` to confirm deterministic seeding is preserved (Station 2's mechanistic model, if it introduces new RNG draws, must be seeded from the same `stationId.hashCode() ^ runId` scheme the rest of the pipeline relies on for bit-for-bit replay — this is a hard constraint from the existing reproducibility design, not optional).

**Effort:** XL (research spike 2–3 weeks; offline-calibration-tool deliverable 3–5 weeks total; live Phase 6b integration, if pursued, is its own multi-month XL effort on top and should be scoped separately once 6a's findings are in).
**Depends on:** nothing blocking (can start immediately, in parallel with Phase 0), but its value compounds once R3 exists to consume its output.

---

## 10. Cross-cutting engineering practices to establish alongside this plan

A few things aren't tied to any single recommendation but come up repeatedly across the phases above and are worth calling out once:

- **Proto field additions are cheap; proto field *removals*/state-vector-length changes are not.** R5 and R3 both add optional, default-zero fields to `BatchTestRequest` — low risk, backward compatible by construction (proto3 semantics). R7's `ThermoStateIndex`/`ProtoIndex` extension is different in kind — it's a fixed-length vector both languages hand-maintain in parallel, with an existing runtime guard that will loudly fail if the two drift. Treat any `_VECTOR_LENGTH` change as requiring a coordinated, single-PR change across `proto_index.py`, `ProtoIndex.java`, `MainSimulator.java`'s frame assembly, and anything in `visualization/` that assumes the current length.
- **Kernel signature changes compound.** R3 and R4 both add parameters to `calculate_pemfc_voltage`/`batch_polarization_sweep`. Land R4's (larger) restructuring first, then add R3's `ecsa_ratio` parameter to the already-open signature rather than doing two separate rounds of "add a parameter, update every call site, update `pemfc_test.py`'s fixtures."
- **Every new default value needs an explicit backward-compatibility regression test.** This pattern already exists in the codebase (`quality_bridge_test.py::test_missing_penalty_fields_default_to_zero`) — every recommendation above that adds a new optional input (R3's `ecsa_ratio`, R5's `RH_anode`, R7's stoich parameters) should ship with the equivalent test: default value in, bit-identical output to pre-change behavior out.
- **R9 should be treated as a standing CI gate, not a one-time deliverable.** Once it exists, any future kernel addition to `numba_ops.py` (including ones this plan doesn't currently anticipate) should be required to add a corresponding parity strategy — that's what the `test_all_kernels_covered` coverage check in R9's task 3 is for.

---

## 11. Risk register

| Risk | Affected phase(s) | Mitigation already in this plan |
|---|---|---|
| R4's sequential-vs-parallel sweep restructuring degrades Station-5 throughput at scale (30 concurrent daemons) | Phase 3 | Keep the existing static-T parallel sweep available as a fast mode; only the new thermal-coupled variant is sequential |
| R2's water-transport sub-model choice turns out to need a much larger PDE than initially scoped | Phase 4 | Research spike deliverable gated *before* implementation begins, explicitly to catch this early |
| R7's state-vector length change breaks an undiscovered downstream consumer (dashboard, analysis notebooks) | Phase 5 | `visualization/dashboard.js` and `analysis/` explicitly called out for review in R7's test plan |
| R6's live Station 2 integration (Phase 6b) breaks deterministic seeded replay | Phase 6 | `SeededReplayTests.java` regression explicitly required before Phase 6b ships |
| R1 Milestone 2 (Bruggeman/Archie model) has no real `P_assembly` input without R6 | Phase 1 | Explicitly gated/deferred in R1's task list rather than silently stubbed |
| Calibration constants introduced without citation (R3's `E_act`, R6's coating-uniformity correlation) ship as if validated | Phase 3, 6 | Both explicitly flagged as "calibration placeholder" requiring literature grounding before being treated as final |
| R10's `simulate_stage1_stamping` station-identity ambiguity (its `is_station_2` branch's `t_base` values match the real repo's Station 1/2 timing, not Station 3's) gets wired to production before being resolved | §13 (R10) | Explicitly called out as a blocking, team-decision item (§13.2 issue 1) with two concrete resolution paths, not silently patched with a guessed value |
| R10's GROUP B constants (Archard wear coefficients, `C_CRIT_NCL`, GDL modulus, die-friction placeholders) get treated as production-ready because the kernel compiles and runs | §13 (R10) | The module's own `run_calibration_sanity_checks()` is designed to fail until real data replaces them — this plan treats a passing self-test as the integration gate, not optional |

---

## 12. Appendix — Gap 1 (cell heterogeneity), for future scoping

Not part of the report's nine recommendations, but since Gap 1 (*"Eq. multiplies single-cell potential by N_cells... assumes all cells... possess identical ohmic resistance, temperature, and gas-channel flow distribution"*) is the one physical gap left without a corresponding recommendation, a brief sketch of what closing it would look like, for whoever scopes it later:

- Replace the scalar `N_cells × V_cell` in `calculate_pemfc_voltage` with a per-cell array (`R_internal[i]`, `T[i]` if R4's thermal model is extended to a per-cell rather than per-stack lump), and `V_stack = Σ V_cell[i]` — the weakest-cell effect the report describes (*"a single flooded or drying cell can fail a stack even if the average cell voltage appears healthy"*) only shows up once cells are no longer assumed identical.
- This interacts with R2 (each cell would have its own `λ[i]`) and R4 (each cell its own thermal state) — if ever pursued, it's naturally a *generalization* of both rather than a separate effort, and would be sequenced after both land, not before.
- Flagged here as a scope note, not committed to a phase, since the report itself didn't propose it.

---

## 13. Addendum — R10: Stations 3–4 Mechanistic Stamping & Clamping Physics (from `stage1_stage2_physics_corrected.py`)

**Status:** new, added after the original nine-recommendation plan above, via the additive method. Not part of `pemfc_report.tex` — sourced from a delivered code artifact, `stage1_stage2_physics_corrected.py`, uploaded separately. Everything in §1–§12 above is unchanged.

### 13.1 What the file actually is

The uploaded module is a **working draft of first-principles physics for two of the manufacturing stations** the report's Gap 6 describes as "purely phenomenological" — i.e., it is a concrete, partially-built head start on exactly what R6 (§9) scoped as a future research spike. Its own header is explicit about its maturity: *"structurally corrected and tested (compilation, array contracts, edge cases). The PHYSICAL CALIBRATION of sigma_1/NCL and the target clamping torque is NOT validated."* That distinction — structurally sound vs. physically calibrated — is the organizing idea for this whole addendum: this plan treats the two as separately gateable, and doesn't let the first stand in for the second.

Two `@numba.njit(nogil=True, cache=True)` kernels, each with an explicit typed signature and a Python-side `_safe` validation wrapper:

- **`simulate_stage1_stamping(press_force_kn, die_stroke_count, w0_initial_wear, use_duplex_coating, is_station_2, k_time)`** — models a metal-forming/stamping process via **Archard adhesive wear** (`wear_raw = w0 + k_wear · strokes · (F/F_nom)^1.8`, correctly clamped to `[0, 0.99999]` — the file notes this clamp genuinely fixes a prior divergence/sign-inversion bug, verified by test to `1e9` strokes) feeding a **Cockcroft–Latham-style normalized ductile-damage integral** (`damage_ncl = work_plastic / C_CRIT_NCL`, closed-form under the stated constant-stress-per-increment assumption) against a Hollomon power-law flow-stress curve for 316L stainless steel (a standard bipolar-plate material choice, consistent with the report's Gap 6 candidate: *"a stamping force/tolerance-stack-up model for Station 3"*). Dual failure mode: `is_defective = damage_index > 1.0 OR wear_ratio >= W_CRIT`.
- **`simulate_stage2_clamping(applied_torques, friction_coefficients, is_station_4, k_time)`** — converts bolt torque to preload force via a standard VDI 2230-style thread-friction formula (pitch, flank half-angle, effective bearing radius — all traceable to ISO fastener geometry, not calibration-dependent), sums four bolts' clamp force (with a simplified scalar elastic-interaction term between tightening sequence neighbors) into a stack clamp pressure, then derives **GDL compression** (thickness, porosity, tangent modulus) from that pressure via a mass-conservation-consistent thickness/porosity relation, plus a **DIN EN ISO 16047-referenced** torque-imbalance check (Bessel-corrected N−1 sample std across the 4 bolts). `is_defective` combines under-clamped, over-clamped, and imbalanced conditions.
- **`k_time` is a call parameter, not a compiled-in constant** — switches between an "accelerated" mode matching `factory.jcm`'s existing tick timings and a 10× "industrial" mode matching `doc2_physical_modeling.md`, without forcing JIT recompilation. This is exactly the same pattern already established in the real repo for `R_internal` (a manufacturing-derived scalar threaded through as a per-call float rather than a module constant) — the file independently arrived at the same architectural idiom this plan already relies on in R1/R3/R4, which is a good sign for how cleanly it will drop into the existing codebase.
- **A self-test harness, `run_calibration_sanity_checks()`**, that is *designed to fail* until the placeholder constants are replaced with sourced data — and one of its four checks already validates simulated defect rate under assumed process noise against the **real** target from `station_stochastics.py` (`STATION_PARAMS[3].defect_rate = 0.002`, confirmed against the live repo). This is, almost verbatim, the offline-validation deliverable Phase 6a (§9) already proposed building from scratch for a Station 2 pilot — here it already exists for Station 3.
- **Every non-ISO-standard constant carries an explicit provenance tag** — `[NAO VERIFICADO]`, `[PLACEHOLDER SEM FONTE]`, `[PLAUSIVEL]`, `[ILUSTRATIVO]`, `[DECIDIDO PELO TIME]` — distinguishing traceable engineering parameters (Group A: bolt geometry, nominal forces, ISO standards) from unconfirmed physical calibration constants (Group B: wear coefficients, damage-criterion constant, GDL modulus, die-friction placeholders). This is materially more rigorous calibration bookkeeping than this plan assumed would need to be built in Phase 3/6 — treat it as a head start to preserve and extend, not a formality to strip out during integration.

### 13.2 Adaptation required before integration

Working through the file with the same scrutiny applied to the report's own nine recommendations surfaces seven concrete issues. None of them are disqualifying — the file says so itself — but each needs a decision or a small code change before this can be wired into `physical_engine/` for real.

1. **Station-identity mismatch in `simulate_stage1_stamping`'s `t_base` (flagged by the file's own author, left unresolved).** The kernel's default `t_base = 5.0` / `is_station_2 → t_base = 12.0` are the real repo's `STATION_PARAMS[1]` (MEA Preparation, 5.0s) and `STATION_PARAMS[2]` (Catalytic Deposition, 12.0s) — stations with no physical relationship to stamping. The real stamping station, `STATION_PARAMS[3]` (Bipolar Plate Stamping), has `t_mean_s = 3.0`. By contrast, `simulate_stage2_clamping`'s `t_base = 3.0 / 24.0` (for `is_station_4 = False/True`) *do* already match the real Station 3/4 values. This needs a team decision between two readings, not a unilateral fix:
   - **(a)** `is_station_2`'s two force presets (120 kN / 250 kN) represent two passes of a genuine multi-stage progressive stamping die *within* the real Station 3 — a common industrial stamping pattern. If so, keep the two-preset structure but re-derive both `t_base` values from Station 3's real 3.0s total (e.g., split proportionally across passes), not from Stations 1/2's unrelated timings.
   - **(b)** `is_station_2` is a leftover artifact from an earlier draft's own internal numbering that got bound to the wrong real station identifiers. If so, drop the two-preset branch entirely; the kernel represents Station 3 alone, with a single nominal force and `t_base = 3.0`.
   This is the single blocking item — nothing downstream should consume this kernel's timing output until it's resolved.
2. **`p_clamp_mpa` is computed inside `simulate_stage2_clamping` but never returned** (only `gdl_porosity` and `e_tangent_mpa`, derived from it, are). Add it to the return tuple. This is a direct, low-risk fix, and it's the specific piece R1 Milestone 2 (§5, updated above) needs as its `P_assembly` input — do this regardless of which integration path (offline vs. live, task 5 below) is chosen.
3. **`gdl_porosity` / `e_tangent_mpa` have no consumer yet.** They're a mechanically-derived GDL compression state with no current home in `pemfc_model.py`. R2 (§7, updated above) is the natural consumer, as an optional enrichment to its own water-transport-derived `j_lim(saturation)`, evaluated once both exist — not a dependency in either direction.
4. **`ELASTIC_COUPLING_COEF` is a single scalar (0.18)** approximating what the source document describes as a full interaction matrix `A_ij ∈ [0.15, 0.28]` dependent on tightening order, and the tightening topology modeled is a simple sequential chain (`0←3, 1←0, 2←1, 3←2`), not a true crisscross pattern. The file itself flags this as a known simplification. Leave it as a documented approximation for the pilot; don't guess at a full matrix without a real tightening-sequence specification to calibrate against.
5. **Group B calibration constants need real primary sources before production use** — Archard wear coefficients (`K_WEAR_PVD`, `K_WEAR_DUPLEX`, `W_CRIT`), the damage-criterion constant `C_CRIT_NCL`, 316L hardening constants (plausible-but-unconfirmed for this specific source), GDL modulus (`GDL_E0_MPA`, `GDL_KS`), and the die-geometry/friction placeholders (`R_DIE_MM`, `THETA_DIE_RAD`, `MU0_FRICTION`, `ALPHA_F_FRICTION` — explicitly "no source" in the file's own comments). This is precisely what `run_calibration_sanity_checks()` already gates on; the integration task is to source the data, not to bypass a currently-red test suite.
6. **Naming.** Once issue 1 is resolved, rename/split the module along real station identity — e.g. `station3_bipolar_plate_stamping.py` and `station4_stack_clamping.py` under `physical_engine/factory_simulation/` — so the ambiguous "stage1/stage2" framing doesn't propagate into the rest of the codebase.
7. **`EPS_P_SCALE`'s Monte Carlo inverse calibration assumes ±5% Gaussian force noise**, explicitly flagged by the file as plausible but unconfirmed. The resulting constant (0.2433) correctly reproduces the real target defect rate *under that noise assumption* — if real process-noise data later shows a different distribution, this constant needs re-inversion, not just re-use.

### 13.3 New recommendation: R10 — Integrate Stations 3–4 Mechanistic Physics

**Addresses:** Gap 6 (same as R6), and materially unblocks R1 Milestone 2 (§5) and enriches R2 (§7).

**Current state:** exists only as the uploaded, unintegrated `stage1_stage2_physics_corrected.py`. `BaseStationArtifact.java` (`src/main/java/factory/BaseStationArtifact.java:60-79`) remains purely stochastic for all four upstream stations — `tProc = tMean_s + rng.nextGaussian()·tStd_s` (clamped to `[0.1×, 3.0×]` of mean) and `defect = rng.nextDouble() < defectRate`, both drawn from a `SplittableRandom` seeded `stationId.hashCode() ^ runId`. The result is logged via `execLinkedOp(databaseArtifactId, "recordStationQuality", runId, orderId, stationId, defect, tProc, tMean_s, currentSimTime)` (`BaseStationArtifact.java:98-99`). Critically, `DatabaseArtifact.recordStationQuality` (`DatabaseArtifact.java:112-116`) **computes its own variance ratio internally** — `varianceRatio = |tProcS − tMeanS| / tMeanS` — from the two timing values passed in; it does not accept a pre-computed variance signal. And `QualityProfile` (`DatabaseArtifact.java:57`) is a 3-field record — `(defectCount, stationsVisited, cumulativeVarianceRatio)` — with no field for `damage_index`, `gdl_porosity`, `e_tangent_mpa`, or `p_clamp_mpa`. This matters concretely: **if this kernel is ever live-wired**, only its `proc_time_s` and `is_defective` outputs have an existing place to go through `recordStationQuality` as-is; its own internally-computed `var_ratio` field would currently be discarded (superseded by `recordStationQuality`'s own `tProc`/`tMean` based formula), and the richer signals (`damage_index`, `gdl_porosity`, `e_tangent_mpa`, `p_clamp_mpa`) have no wire path to Station 5 at all without extending `QualityProfile`, `recordStationQuality`'s signature, and — again — `BatchTestRequest` (a fourth addition to that proto, after R1/R5/R3; see §10's note on bundling signature changes).

**Target design:** the same two-path fork R6 already identified (§9) — offline calibration/validation tool now, live per-stack gRPC integration later — but with a concrete near-term step neither R6 candidate had: the file already ships its own offline validation harness. "Ship the offline tool" here is mostly *fixing and sourcing*, not *building from nothing*.

**Implementation tasks (ordered):**

1. Resolve the station-identity mapping (§13.2 issue 1) — a team decision, not a coding task, but blocking everything downstream of it.
2. Patch `simulate_stage2_clamping` to return `p_clamp_mpa` (§13.2 issue 2) — trivial, do regardless of which path (offline/live) is chosen, since R1 Milestone 2 wants it either way.
3. Source real primary data for the Group B constants (§13.2 issue 5) — the actual bottleneck. Until this lands, `run_calibration_sanity_checks()` stays red by design, and this module should not touch real stack defect rates.
4. Once 1–3 are resolved: rename/split per §13.2 issue 6, and fold into the same offline-validation script pattern Phase 6a already proposed — extend `run_calibration_sanity_checks()`'s Check 3 (currently Station 3 only) with an equivalent check against `STATION_PARAMS[4]`'s real Station 4 target (`defect_rate = 0.008`), so both stations this file covers are validated, not just one.
5. *(Optional, mirrors R6's own live-integration fork exactly)* — if the offline validation results justify it: new gRPC method(s) analogous to `RunBatchTest` (e.g. `RunStampingTest`, `RunClampingTest`), `BaseStationArtifact.java` gains a mechanistic mode, and `recordStationQuality`/`QualityProfile` get extended with the richer fields identified above. **Must preserve the existing deterministic-seeding contract** (`stationId.hashCode() ^ runId`) if taken — the same non-negotiable constraint already noted for R6's Station 2 live-integration path (§9), restated here because it applies identically.
6. Wire `p_clamp_mpa` into R1 Milestone 2's `R_contact(P_assembly)` once both exist (§5) — a sequencing dependency, not a new task.
7. Evaluate `gdl_porosity` as an input to R2's `j_lim(saturation)` refinement (§7) — optional enrichment, evaluate once both exist.

**Test plan:**

- Unit tests for each kernel's `_safe` wrapper input validation (array shape/sign checks), in the style already used by `quality_bridge_test.py` for the existing physics engine.
- Get all four of `run_calibration_sanity_checks()`'s checks to genuinely pass (not just run without crashing) once real Group B data lands — this is the module's own acceptance gate; treat it as non-negotiable, not advisory.
- Extend that harness with the Station 4 defect-rate cross-check described in task 4.
- If task 5 (live integration) is pursued: `SeededReplayTests.java` regression, identical requirement to R6's Phase 6b (§9).

**Effort:** M/L for tasks 1–4, 6, 7 (offline path — mostly data-sourcing and a light, low-risk refactor; the numerics are already written and structurally tested). XL if task 5 (live integration) is pursued, same caveat as R6.

**Depends on:** nothing blocking for the offline path — can start immediately, in parallel with Phase 0. R1 (task 6) and R2 (task 7) are downstream consumers of this work, not blockers to starting it.

### 13.4 Updated Phase 6 picture

Phase 6 (§9, "parallel track") now has two candidate pilots instead of one: the originally-proposed Station 2 (catalyst deposition, feeding R3's `ecsa_ratio`, still at the research-spike stage) and this addendum's Stations 3–4 (stamping/clamping, feeding R1 Milestone 2 and R2, already at working-draft-code maturity pending the calibration data and station-identity decision in §13.2). Given that head start, **this plan now recommends Stations 3–4 (R10) as the track that ships first**, with the original Station 2 pilot remaining the second target once R10 has landed and the offline-validation pattern it establishes can be reused.
