# Corrected & Improved Implementation Plan: R6 (Stations 1–4 First-Principles Models), R10 (Stamping/Clamping Physics), and R1 Milestone 2 (Contact Resistance)

**Supersedes:** `r6_r10_implementation_plan.md`.
**Re-audited against:** `utczbr/Matrix_Factory@main`, fresh clone, 2026-07-26 — every factual claim below was checked directly against source (grep, `view`, and in one case running the delivered kernel), not carried over from the prior draft.
**Source artifact for R10:** `stage1_stage2_physics_corrected.py`, as uploaded — also executed directly (see §1.2) rather than only read.
**Research grounding:** *Mathematical Grounding & Parameter Provenance for a PEMFC & Manufacturing Digital Twin* (uploaded), Domains 1–5.

---

## 0. Why this revision exists

The prior plan (`r6_r10_implementation_plan.md`) is well-structured and gets most of the Java/proto/stochastics side exactly right. But two of its central factual claims are wrong, and one of its test-plan recommendations doesn't fit the tooling it names. Those errors matter because they change the actual size and order of the work: the plan treats R1 Milestone 2 as unbuilt (driving an "M effort, build from scratch" task) when the core function already exists in the repo — unwired and untested, but real — and it treats the stamping kernel's miscalibration as purely a "waiting on real supplier data" problem when part of it is a reproducible internal bug independent of any real data ever arriving.

This document is organized so a reader can trust it without re-deriving everything themselves: §1 lists every correction with the exact evidence, §2 confirms what the prior plan got right (so it isn't discarded wholesale), and §3–§5 give the revised R6/R10/R1-M2 task plan.

---

## 1. Corrections to the prior plan (read this first)

### 1.1 — Major: `R_contact(P_assembly)` already exists — R1 Milestone 2 is not a from-scratch build

**Prior plan claimed (§0, §2.7):** *"`R_contact(P_assembly)` / Bruggeman-Archie porosity coupling does not exist anywhere in `pem_physics.py` or a `microstructure.py`."* — and scoped a new "Effort: M" task to build it.

**Actual state:** `physical_engine/factory_simulation/microstructure.py` exists today, in full, with:
- `compute_effective_porosity_conductivity(sigma_bulk, gdl_porosity, m_exponent=1.5)` — a correct Bruggeman relation, σ_eff = σ_bulk·(1−ε)^m.
- `compute_contact_resistance(p_assembly_mpa, gdl_porosity=0.78, r_contact_0=R_CONTACT_0)` — already implements a U-shaped resistance-vs-pressure response, already defaults `gdl_porosity` to the same `0.78` used as `GDL_EPS0` in the stamping/clamping kernel, and already sources `R_CONTACT_0 = 0.0042 Ω·cm²` and `R_CONTACT_UNCOATED = 0.0185 Ω·cm²` to Mason et al. (2012) and El-Kharouf et al. (2012) — matching the research doc's Domain 3 provenance exactly.

**But it is completely orphaned.** A repo-wide search confirms:
```
grep -rn "microstructure\|compute_contact_resistance\|compute_effective_porosity_conductivity" --include="*.py" --include="*.java" .
```
returns **zero matches outside the file itself.** Nothing calls it, no test imports it (`find . -iname "*microstructure*"` returns only the module), and it has no `run_calibration_sanity_checks()`-style self-test — unlike every other Group-A/B-labeled module in this codebase.

**Impact on the plan:** §2.7 is not "build `R_contact(P_assembly)`." It's "integrate, test, and reconcile an already-written function that nobody has wired up or checked." That's a smaller, differently-shaped task — see the rewritten §5.1 below.

### 1.2 — Major: the stamping/NCL kernel fails its own documented calibration claim, independent of any real data

The uploaded file's header comment states the shipped `EPS_P_SCALE = 0.2433` was obtained by Monte Carlo inversion against the real Station-3 defect-rate target (0.2%), and specifically claims: *"D_NCL nominal (sem ruído) = 0.863."*

I ran the file's own `run_calibration_sanity_checks()` and additionally hand-traced the formula. Both agree, and both contradict that claim:

```
$ python3 stage1_stage2_physics_corrected.py
[FALHOU] stage1_nominal_nao_defeituoso
          damage_index: 1.398918722289787
          esperado: damage_index << 1.0, is_defective=False
[PASSOU] stage2_torque_nominal_dentro_da_faixa
[FALHOU] stage1_taxa_defeito_proxima_do_alvo_real_S3
          taxa_empirica: 100.000%
          alvo_real_repositorio: 0.20%
[PASSOU] k_time_razao_10x_entre_modos
```

Direct kernel call at **zero wear, zero stroke count** (brand-new die, best possible case) already gives `damage_index ≈ 1.399`, not the documented `0.863`, and `is_defective=True`. Hand-tracing confirms it's not a code bug in the sense of a typo — the formula executes exactly as written; the constant just doesn't hit its own stated target:

```
eps_p_final = 0.2433 → sigma_flow_mpa ≈ 696.9 MPa, sigma_1_mpa ≈ 799.4 MPa
work_plastic ≈ 0.489 → damage_ncl = 0.489 / 0.35 ≈ 1.397   (not 0.863)
```

Because the nominal (noise-free) point is already above the defect threshold, the Monte Carlo check is mechanically guaranteed to show ~100% empirical defect rate regardless of the ±5% force-noise assumption — **these are one root cause, not two independent failures.** The file's own comment even acknowledges the two parameters (channel geometry, `EPS_P_SCALE`) aren't independent and must be re-inverted together — but the version that shipped doesn't reproduce that inversion's own stated result. This most likely means `EPS_P_SCALE` was fit against a slightly different `N_CHANNELS`/`CHANNEL_WIDTH_MM`/`CHANNEL_ENGAGED_LENGTH_MM` triple than the one that ended up in the file, or the comment records an intermediate result from before a later edit.

**Impact on the plan:** the prior plan's §2.4 ("Source Group B calibration constants") treats this purely as "waiting on real supplier/lab data." That's true for the *magnitude* of `K_STRENGTH_316L`, `C_CRIT_NCL`, `N_CHANNELS`, etc. — but the self-consistency of `EPS_P_SCALE` against whatever geometry constants are currently in the file is a fixable-today bug, not a data-sourcing wait. It should be a separate, immediate task (§4.4a below), done *before* real Group-B data lands, so the calibration harness has any chance of passing once real data replaces the placeholders — right now it would still fail even with perfect data, because the internal self-consistency is broken.

### 1.3 — Minor but real: a stale, self-contradicting comment inside the same file

Within the kernel body (around the `eps_p_final` line), a comment reads: *"EPS_P_SCALE=0.30 é calibrado por inversão contra a taxa-alvo real... não é um valor geométrico."* But the constant actually defined at the top of the file is `0.2433`, not `0.30`. This is a leftover from a prior revision that was never updated when the constant changed. Anyone reading the kernel body in isolation (a likely thing to do when debugging) will get a wrong reference value. Flag for cleanup alongside §1.2's fix — don't just fix the number, fix the comment that references the old number too.

### 1.4 — Minor: a genuinely dead constant, unlike its labeled-obsolete neighbor

`E_STEEL_GPA = 193.0` (316L Young's modulus) is defined but never referenced anywhere in the kernel body. Unlike `MEMBRANE_STRESS_SCALE`, which is explicitly commented `[OBSOLETO — não mais usado]`, `E_STEEL_GPA` carries no such flag — it reads as if it should still be doing something. Either wire it into a genuine elastic-deformation term (if one was intended and dropped when the Hollomon flow-stress formulation replaced an earlier elastic model) or remove it and flag it obsolete like its neighbor, so the next reader doesn't spend time looking for its call site.

### 1.5 — Architectural correction to §2.7's wiring instructions

The prior plan's §2.7 task 2 said to wire the new contact-resistance term into **`TestBenchArtifact.java`'s `rInternalPenalty` accumulation** — i.e., compute/consume it Java-side.

That's inconsistent with how every other physically-modeled quantity in this codebase is handled. Every actual physics kernel — `pemfc_model.py`, `membrane_hydration.py`, and now `microstructure.py` — lives in Python and is called from `sim_bridge_server.py`; Java only ever aggregates *manufacturing-event counts* (`defectCount`, `cumulativeVarianceRatio`) into a scalar penalty and hands that scalar across the wire. `R_contact(P_assembly)` is a physics function, not an event count — it belongs in the same place `_effective_j0`'s Arrhenius/ECSA scaling already lives: computed server-side in Python, from raw physical inputs sent across the wire.

**Corrected design:** add `p_clamp_mpa` and `gdl_porosity` as two *new* `BatchTestRequest` fields (proto field numbers 11 and 12 — confirmed free; the message currently ends at field 10, `ecsa_ratio`), mirroring exactly how `ecsa_ratio` and `rh_anode` were added previously. `sim_bridge_server.py`'s `RunBatchTest` calls `microstructure.compute_contact_resistance(p_clamp_mpa, gdl_porosity)` and adds its result into `R_internal_effective` **alongside, not instead of,** the existing `r_internal_penalty_ohm_cm2` term — these are two distinct physical contributions (defect-driven heuristic penalty vs. mechanistically-derived clamping-pressure contact resistance) and conflating them into one channel is exactly the "two upstream signals landing on the same downstream effect" trap the prior plan itself warned about for `ecsa_ratio` (§0 point 4 in the original). Java's role is just to pass `p_clamp_mpa`/`gdl_porosity` through from `MechanisticSignal` onto the new request fields — no physics computed on the JVM side.

### 1.6 — Test-plan tooling correction: §2.8's "extend R9's `parity_test.py`" doesn't fit

The prior plan recommends extending `physical_engine/optimization/parity_test.py`'s "hypothesis-driven harness" to cover the new Station 3/4 kernels. I read that file: it is specifically a **compiled-Cython-vs-pure-Python-fallback numerical agreement check** for the utility kernels in `_numba_ops_core` / `_numba_ops_core_python` (gas properties, tank fill dynamics, heat-exchanger correlations — the `h2_tank`/`cathode_air_bop`/`compressor` domain). It asserts every exported kernel has a registered parity test between its two implementations. Station 3/4's kernels have only one implementation (`@numba.njit`, no separate Cython/pure-Python fallback pair), so there is nothing for them to have parity *against* — "extending" this file literally doesn't apply.

**Corrected recommendation:** build a new, separate property-based test module (e.g. `station_mechanistic_test.py`), reusing the same `hypothesis` library and the same spirit (physically-valid input-domain strategies, `@settings(max_examples=...)`) — but as its own harness, checking invariants like *no NaN/negative outputs, monotonicity where physically expected, bounds respected* — not attempting to force-fit it into the compiled/fallback parity concept.

### 1.7 — Scope note: `rh_anode` is wired but permanently dead, and materially different from the other three fields

The prior plan's §0 point 4 lists `rh_anode` alongside `r_internal_penalty_ohm_cm2`, `activity_derate_fraction`, and `ecsa_ratio` as "the four fields already wired end-to-end." That's true only in the narrow sense that it exists on the proto and is read server-side (`rh_anode = getattr(request, "rh_anode", 0.0)`). Unlike the other three, **nothing on the Java side ever calls `.setRhAnode(...)`** — grep confirms zero references in `TestBenchArtifact.java`. Every stack tested today is tested with a bone-dry anode (`rh_anode=0.0`) regardless of anything Stations 1–4 do. This isn't a bug — it's simply unscoped — but it means the research doc's Domain 4 water-transport physics (electro-osmotic drag, back-diffusion, λ(a_w) sorption) has **no producer at all** among the four manufacturing stations today, unlike `ecsa_ratio` (has a hardcoded stand-in) or `r_internal_penalty_ohm_cm2`/`activity_derate_fraction` (have live heuristics). Recommend explicitly scoping this **out** of R6/R10 (it would need its own research spike tying, e.g., Station 1's hot-press dwell/humidity history to inlet membrane pre-conditioning) but naming it here so it isn't silently forgotten the way it evidently already has been once.

### 1.8 — Process note: two copies of the proto must move together

`physical_engine/protos/sim_bridge.proto` and `src/main/proto/sim_bridge.proto` are maintained as separate, currently byte-identical files (confirmed via `diff`). Any new field (§5.1's `p_clamp_mpa`/`gdl_porosity`, §4.5's `j_lim_derate_fraction`) must be added to **both**, plus the regenerated `sim_bridge_pb2.py`/`sim_bridge_pb2_grpc.py` stubs and the Java-side generated proto classes, or the two language runtimes will silently drift apart. Not a new problem introduced by this plan, but worth a standing checklist item since this plan adds three new fields across two PRs.

---

## 2. What the prior plan got right (independently re-verified, unchanged)

To be clear about what *isn't* being revised — I checked each of these directly against source rather than assuming the prior plan's description was accurate, and confirmed all of them:

- `station_stochastics.py`'s `STATION_PARAMS` — exact values confirmed (Station 1: 5.0/5.0/0.005 … Station 4: 24.0/30.0/0.008), and independently cross-checked against `factory.jcm`'s `base_station_*` artifact declarations, which match exactly.
- `BaseStationArtifact.processOrder`'s stochastic model (`tMean_s + rng.nextGaussian()·tStd_s`, clamped `[0.1×,3.0×]`, `rng.nextDouble() < defectRate`, seeded `stationId.hashCode() ^ runId`) — confirmed verbatim.
- `TestBenchArtifact.java`'s `double ecsaRatio = 1.0;` bare literal, the `min(0.6, defectCount*0.15)` activity-derate cap, and the `+0.08 Ω·cm²`-per-defect ohmic penalty scale — confirmed verbatim, including the exact comment marking it as a Station-2 R6/R10 placeholder.
- `DatabaseArtifact.QualityProfile`'s 3-field record (`defectCount`, `stationsVisited`, `cumulativeVarianceRatio`) and its `peekQualityProfile`/`recordStationQuality`/`invalidateQualityProfile` operations — confirmed verbatim, including the Caffeine-cache-with-TTL design for orphaned-stack cleanup.
- `BatchTestRequest`'s four existing quality-bridge fields (7–10) and `BatchTestResponse.failure_flags`'s five bits — confirmed verbatim against the live `.proto` (both copies, identical) and the generated `_pb2.py`.
- `pemfc_model.py`'s `j_lim = 2.5` bare literal repeated at exactly four call sites (`calculate_pemfc_voltage` line 279, `newton_raphson_solver` line 326, `batch_polarization_sweep` line 391, `batch_polarization_sweep_thermal` line 454) while `PEMFCConstants.j_lim_pemfc` sits defined-but-unreferenced in the dataclass — confirmed verbatim.
- `stage1_stage2_physics_corrected.py`'s station-identity mixup: the stamping kernel's `t_base` values (5.0/12.0) really are Station 1/2's real timings, not Station 3's real `3.0`, while the clamping kernel's `t_base` (3.0/24.0) already correctly matches Stations 3/4 — confirmed by cross-referencing `factory.jcm`.
- `simulate_stage2_clamping`'s return-tuple bug: `p_clamp_mpa` is computed internally but the `numba.types.Tuple(...)` signature and the `return` statement both only carry 5 values, silently dropping it — confirmed by direct inspection of the decorator and the `return` line.
- Neither `station3_bipolar_plate_stamping.py`/`station4_stack_clamping.py` nor any calibration script under `physical_engine/scripts/` exist yet — confirmed by directory listing; only `prebuild_luts.py` exists there today, matching the convention the plan asks §2.6 to follow.
- CI (`pytest physical_engine/`, `./gradlew test`) needs no changes to pick up new modules/tests placed under the existing directories — confirmed from `.github/workflows/ci.yml`.

---

## 3. R6 — First-Principles Process Models for Stations 1–4 (revised)

Scope and rationale are unchanged from the prior plan: cover all four stations, with Stations 3/4 substantially pre-designed by the uploaded file (→ R10, §4) and R6 proper scoped to the shared architecture plus Stations 1 and 2.

### 3.1 Shared architecture (build once, all four stations use it)

Unchanged from the prior plan — this pattern is sound and worth keeping as written:

- One `@numba.njit(nogil=True, cache=True)` kernel per station, own module under `physical_engine/factory_simulation/` (`station1_mea_preparation.py`, `station2_catalyst_deposition.py`, and R10's `station3_bipolar_plate_stamping.py` / `station4_stack_clamping.py`).
- A `_safe` wrapper per kernel doing array-shape/sign validation outside the JIT boundary.
- A `run_calibration_sanity_checks()` self-test per module, following the Group A (traceable engineering constants) / Group B (unverified calibration constants) convention the uploaded file establishes — **and now, per §1.1, extend this same convention to `microstructure.py`, which currently has none.**
- One explicit, reviewed decision per station on which of the Station-5 target signals it feeds (table below), made before implementation starts.

| Station | Real name | Mechanistic output | Station-5 signal(s) it feeds | New wiring required? |
|---|---|---|---|---|
| 1 | MEA Preparation | Degree of cure α; delamination/pinhole probability | `activity_derate_fraction`, `r_internal_penalty_ohm_cm2` | No — both fields exist |
| 2 | Catalytic Deposition | Per-stack effective ECSA ratio | `ecsa_ratio` | No — field exists, currently hardcoded 1.0 |
| 3 | Bipolar Plate Stamping | `damage_index`, `wear_ratio` | `r_internal_penalty_ohm_cm2` | No — field exists |
| 4 | Robotic Stack Assembly | `p_clamp_mpa`, `gdl_porosity`, `e_tangent_mpa` | `R_contact(P_assembly)` term (§5.1, **new fields**, computed Python-side); mass-transport signal (§4.5) | **Yes — 3 new proto fields total across §5.1/§4.5** |
| *(none currently)* | *(Domain 4 water transport)* | Membrane inlet hydration | `rh_anode` | **Out of scope — see §1.7.** Field exists, wired to Python, but has no upstream producer; flagged so it isn't lost. |

Java-side plumbing (extend `DatabaseArtifact.QualityProfile` additively via a parallel `MechanisticSignal` record; new `recordMechanisticQuality`/`peekMechanisticSignal` operations, kept separate from `recordStationQuality`/`peekQualityProfile` so existing callers are untouched) is unchanged from the prior plan and remains correct — the design rationale (don't overload the existing 3-field record's semantics; `ecsaRatioMin`-style worst-case reduction chosen once, not re-litigated per station) still holds:

```java
public record MechanisticSignal(double ecsaRatioMin, double damageIndexMax,
                                  double pClampMpaLast, double gdlPorosityLast) {
    static final MechanisticSignal EMPTY = new MechanisticSignal(1.0, 0.0, 0.0, 0.78);
    MechanisticSignal combine(MechanisticSignal other) {
        return new MechanisticSignal(
            Math.min(this.ecsaRatioMin, other.ecsaRatioMin),
            Math.max(this.damageIndexMax, other.damageIndexMax),
            other.pClampMpaLast,     // last-write, not additive — a physical state, not a count
            other.gdlPorosityLast);
    }
}
```

**One addition per §1.5:** `pClampMpaLast`/`gdlPorosityLast` are read out of this record by `TestBenchArtifact.java` and placed directly onto the new `BatchTestRequest.p_clamp_mpa` / `.gdl_porosity` fields — Java never computes `R_contact` itself.

### 3.2 Station 1 — MEA Preparation (hot-press lamination)

Unchanged from the prior plan; still correctly scoped and still not built. Kamal–Sourour autocatalytic cure kinetics:

```
dα/dt = (K1 + K2·α^m)·(1 − α)^n
K_i = A_i · exp(−E_i / R·T_press)
```

Given `T_press`, `t_dwell`, α₀=0, integrate (RK4, fixed small step) to `α_final`. Two failure modes:
- **Under-cure** (`α_final < α_min_bond`): delamination risk → contact-resistance penalty.
- **Over-cure** (`α_final > α_max_safe`): pinhole risk → activity derating.

**Implementation tasks:**
1. Research spike (literature-grounded — the research doc's Domain 5 gives `E_1≈58.2 kJ/mol`, `E_2≈46.8 kJ/mol`, `m≈0.48`, `n≈1.52` as *illustrative starting points from Kamal & Sourour (1976) and Anisiko et al. (2021)*, not Nafion/PFSA-adhesive-specific values — this specific system's constants still need sourcing).
2. New module `station1_mea_preparation.py`: `simulate_hot_press_cure(t_press_k, dwell_time_s, k_time)` → `(proc_time_s, is_defective, alpha_final, delamination_risk, pinhole_risk)`.
3. Map `delamination_risk` → additive term on `r_internal_penalty_ohm_cm2` (reuse the existing `+0.08 Ω·cm²` per-defect scale as the starting point).
4. Map `pinhole_risk` → additive term on `activity_derate_fraction`, capped by the existing `min(0.6, ...)` ceiling.
5. Offline calibration: Monte Carlo against `STATION_PARAMS[1].defect_rate = 0.005`, following the (now twice-proven, see §1.2's cautionary tale) `run_calibration_sanity_checks()` pattern — **and this time, actually run the self-test before calling it calibrated**, not just document an inversion result that the shipped constant doesn't reproduce.
6. Live wiring (Phase 6b, only after step 5 passes): `BaseStationArtifact.java` gains a mechanistic mode, new gRPC method (`RunStation1Test` or shared `RunStationMechanisticTest`), logs via `recordMechanisticQuality`.

**Effort:** L. **Depends on:** §3.1's shared `MechanisticSignal` plumbing.

### 3.3 Station 2 — Catalytic Deposition

Unchanged — still the cleanest win in the plan. `ecsa_ratio` already exists on the wire and is already correctly consumed by `_effective_j0`'s Arrhenius scaling (confirmed at `pemfc_model.py:206-209`); the only missing piece is a real number instead of `1.0`.

**Implementation tasks:**
1. Research spike (2–3 weeks): coating-speed/loading-uniformity correlation, plus an explicit, signed-off choice of how a distribution of local ECSA collapses to a scalar `ecsa_ratio` (mean / worst-case percentile / area-weighted) — same decision as §3.1's `MechanisticSignal.ecsaRatioMin` reduction; resolve once, not twice.
2. New module `station2_catalyst_deposition.py`, standalone-callable against `STATION_PARAMS[2]` (`t_mean_s=12.0, t_std_s=15.0, defect_rate=0.012`).
3. Offline-first validation.
4. Live wiring (Phase 6b): `TestBenchArtifact.java`'s `double ecsaRatio = 1.0;` becomes a fetch from `peekMechanisticSignal`, mirroring the `peekQualityProfile` call immediately above it.

**Effort:** L. **Depends on:** nothing blocking; §3.1 shared plumbing for live wiring only.

### 3.4 Stations 3–4

Covered by R10 (§4). R6's role: confirm R10's two kernels are the Station 3/4 models this recommendation calls for (true, once §4.1's station-identity fix lands), plus the `j_lim` parameterization below.

### 3.5 Parameterizing `j_lim` (unchanged from prior plan, re-verified)

Confirmed the exact four call sites (`pemfc_model.py:279,326,391,454`) and the unreferenced `PEMFCConstants.j_lim_pemfc` dataclass field. Tasks are unchanged:

1. Replace all four `j_lim = 2.5` local literals with a passed-in parameter defaulting to `PEMFCConstants.j_lim_pemfc`.
2. Add `j_lim_derate_fraction` to `BatchTestRequest` — this becomes proto field **#13** (after §5.1's #11/#12), keeping all new fields in this plan sequential and reviewed together rather than landing across scattered, uncoordinated PRs (see §1.8).
3. Thread the parameter through all four functions in the same PR wave as R6/R10's other signature touches.
4. Backward-compatibility test: default `j_lim_derate_fraction=0.0` reproduces bit-identical output (same pattern as `quality_bridge_test.py::test_missing_penalty_fields_default_to_zero`, confirmed to exist and follow this exact pattern today).
5. Wire Station 4's `gdl_porosity` → `j_lim_derate_fraction` via a documented-as-provisional linear relation in porosity deficit from `GDL_EPS0=0.78`, pending real GDL diffusivity data (Bruggeman tortuosity correction — consistent with `microstructure.py`'s `compute_effective_porosity_conductivity`, which already exists and already does this exponent form — is the natural eventual upgrade).

**Test plan:** new property-based test module per §1.6 (not a `parity_test.py` extension); the four-function backward-compat test; an integration test confirming `MASS_TRANSPORT_STARVATION` trips at high porosity deficit + high current density and not at nominal porosity.

**Effort:** M. **Depends on:** R10's `gdl_porosity` output existing and being wired live, or at minimum available offline for step 5's calibration.

**R6 overall effort:** XL (Station 1: L; Station 2: L; §3.5: M; shared infra: S/M). **Depends on:** nothing blocking to start; §3.5 depends on R10 producing `gdl_porosity`.

---

## 4. R10 — Stamping/Clamping Physics Integration (revised)

**Current state (re-confirmed):** exists only as the uploaded file — zero matches for Archard/Cockcroft/VDI-2230-specific terms anywhere else in `main`.

### 4.1 Station-identity resolution (blocking, do first) — unchanged, confirmed correct

Take path (b): collapse the `is_station_2` two-preset branch into a single nominal-force stamping model with `t_base=3.0`, dropping `F_NOM_S2`. Rationale unchanged — `F_NOM_S1`/`F_NOM_S2` carry the same "borrowed from the wrong station" ambiguity as `t_base`; there's no independent evidence of a genuine two-pass progressive-die schedule. One-line change plus a team sign-off comment replacing the `NOTA A PARTE` block. Blocking everything else in §4.

### 4.2 Return-tuple fix (trivial, do regardless of path) — unchanged, confirmed correct

`simulate_stage2_clamping` computes `p_clamp_mpa` (confirmed at the line computing `p_clamp_pa = f_total_n / A_STACK`) but the numba signature and `return` statement both stop at 5 values, silently dropping it.

```python
@numba.njit(
    numba.types.Tuple((numba.float64, numba.boolean, numba.float64,
                        numba.float64, numba.float64, numba.float64))(   # +1 float64
        numba.float64[:], numba.float64[:], numba.boolean, numba.float64
    ),
    nogil=True, cache=True,
)
def simulate_stage2_clamping(...):
    ...
    return proc_time_s, is_defective, var_ratio, gdl_porosity, e_tangent_mpa, p_clamp_mpa
```

Update `simulate_stage2_clamping_safe` and any call site. Extend `run_calibration_sanity_checks()`'s Check 2 to assert `3.0 <= r2[5] <= 5.5` directly against the returned pressure (confirmed by direct call: at the team-decided `TORQUE_NOMINAL_NM=46.0`, `p_clamp_mpa≈4.217`, `gdl_porosity≈0.772`, `e_tangent_mpa≈5401.75` — all internally self-consistent with the Kleemann tangent-modulus formula when hand-checked against `GDL_E0_MPA=2.80`, `GDL_KS=28.5`).

### 4.3 Rename/split per resolved station identity — unchanged

Once §4.1 lands: `station3_bipolar_plate_stamping.py` (from `simulate_stage1_stamping`), `station4_stack_clamping.py` (from `simulate_stage2_clamping`). Do a clean-cache test run after the move (`numba`'s disk cache has been known to key partially on file path in some versions).

### 4.4 Source Group B calibration constants — table unchanged, one task added

| Constant | What it needs |
|---|---|
| `K_WEAR_PVD`, `K_WEAR_DUPLEX`, `W_CRIT` | Supplier datasheet or ASTM G133-style pin-on-disk bench test against the real die/coating pair |
| `C_CRIT_NCL` | Controlled forming-limit test for 316L under the real strain path |
| `K_STRENGTH_316L`, `N_HARDENING_316L` | ISO 6892 tensile test on the actual plate stock lot, or mill certificate |
| `GDL_E0_MPA`, `GDL_KS` | Compression-tester data sheet from the actual GDL supplier/part number |
| `R_DIE_MM`, `THETA_DIE_RAD`, `MU0_FRICTION`, `ALPHA_F_FRICTION` | Real die/tooling drawing plus a friction measurement for the real lubricant/coating pair |
| `N_CHANNELS`, `CHANNEL_WIDTH_MM`, `CHANNEL_ENGAGED_LENGTH_MM` | The real flow-field/die channel drawing |
| `EPS_P_SCALE` | Must be **re-inverted** once real geometry lands — see §4.4a, which is a prerequisite, not a follow-on |

#### 4.4a — NEW, immediate: fix `EPS_P_SCALE`'s internal self-consistency now (§1.2)

Before any real Group-B data sourcing begins, re-run (or fix) the Monte Carlo inversion that produced `EPS_P_SCALE` so that it actually reproduces its own documented target against the geometry constants **currently shipped** (`N_CHANNELS=60`, `CHANNEL_WIDTH_MM=1.0`, `CHANNEL_ENGAGED_LENGTH_MM=20.0`). Today, even brand-new-die/zero-noise conditions compute `damage_index≈1.40` against a documented target of `0.863` — a reproducible discrepancy, confirmed by direct execution, not a hypothetical. This task is independent of whether the illustrative geometry constants turn out to be the real ones later (§4.4's `N_CHANNELS` row) — if/when real geometry lands, the inversion must be re-run again, but it should be re-run correctly *this time* first so the calibration harness has a working baseline to build on. Also fix the stale in-body comment (§1.3) that still references the superseded `EPS_P_SCALE=0.30`, and either wire or remove the dead `E_STEEL_GPA` constant (§1.4).

**Task:** this is a data-sourcing task for the Group B table rows, but §4.4a itself is a same-day fix — re-run the existing Monte Carlo inversion script against the actual shipped constants and confirm Check 1/Check 3 pass before moving on. **Blocking for:** treating any Check-1/Check-3 pass as meaningful; not blocking for §4.1–§4.3, §4.5, or §4.6, which don't depend on this kernel's calibration state.

### 4.5 Extend the calibration harness for Station 4 — unchanged

Add an equivalent to Check 3 for Station 4 against `STATION_PARAMS[4].defect_rate = 0.008` (assumed torque-noise distribution, flagged as assumed, 50k-sample Monte Carlo, empirical-vs-target comparison) — same shape as the existing Check 3, different kernel and target.

### 4.6 Ship the offline calibration/validation tool — unchanged

Package §4.1–§4.5 into `physical_engine/scripts/calibrate_stamping_clamping.py`, following the existing convention (`physical_engine/scripts/` currently contains only `prebuild_luts.py` — confirmed).

### 4.7 Integrate `R_contact(P_assembly)` — REWRITTEN per §1.1/§1.5 (this is R1 Milestone 2)

This is the section that changes most. The pure function already exists in `microstructure.py`; the work is integration, self-testing, and reconciling its formula against the research doc's actual target design — not building it from nothing.

**A formula mismatch worth resolving first:** the research doc's Domain 3 target design is a power law,
```
R_contact(P) = R_bulk + R_contact,0 · (P_ref/P)^ξ
```
but the shipped `compute_contact_resistance` instead implements a symmetric quadratic-deviation heuristic,
```
r_contact = r_contact_0 · (1 + 0.35·p_dev + 0.25·p_dev²),  p_dev = |P − 4.25|/4.25
```
— structurally identical in form to the *stamping kernel's* `var_ratio = 1.0 + 0.35·wear_ratio + 0.30·damage_index²` and the *clamping kernel's* `var_ratio = 1.0 + 0.35·p_dev + 0.25·tau_std`. This is very likely the same heuristic reused across three places rather than an independent derivation of the Domain 3 power law. It does produce the right qualitative shape (U-shaped, both under- and over-clamping penalized) and the right nominal value at `P=4.25 MPa` (`r_contact=r_contact_0` exactly, by construction), so it is usable as an interim model — but it should be explicitly labeled as the heuristic it is, not conflated with the Bruggeman/Archie-sourced conductivity function sitting right next to it in the same file, which *is* independently and correctly derived.

**Implementation tasks:**
1. Add a `run_calibration_sanity_checks()`-style self-test to `microstructure.py` (it currently has none) — at minimum: unit tests at fixed porosity/pressure points against hand-computed values, and a check that both under-clamped and over-clamped pressures away from `P_NOMINAL_MPA=4.25` increase `R_contact` (U-shaped, not monotonic).
2. As a team decision (not a code default): either (a) keep the quadratic heuristic as documented-provisional pending real Mason-et-al.-style pressure-sweep data for *this specific* coating/GDL pair, or (b) replace it with the power-law form from the research doc, re-fit `ξ` and `R_bulk` against the same `R_contact,0=4.20 mΩ·cm²`/`R_contact,unc=18.50 mΩ·cm²` anchor points already in the Group B table. Either is defensible; leaving it unlabeled (as today) is not.
3. Add `p_clamp_mpa` and `gdl_porosity` as new `BatchTestRequest` proto fields (11, 12) — see §1.5, §1.8.
4. `sim_bridge_server.py`'s `RunBatchTest` calls `microstructure.compute_contact_resistance(request.p_clamp_mpa, request.gdl_porosity)` and adds the result into `R_internal_effective` **additively alongside** (not replacing) the existing `r_internal_penalty_ohm_cm2` term.
5. `TestBenchArtifact.java` reads `pClampMpaLast`/`gdlPorosityLast` from `MechanisticSignal` (§3.1) and sets the two new request fields — no physics computed in Java.
6. **Interim stopgap, if Station 3/4 live integration (§4.8) lands before step 2's decision is finalized:** the clamping kernel's own `var_ratio` output can feed the existing `cumulativeVarianceRatio` channel as a bridge, exactly as the prior plan suggested — but flag this explicitly in code comments as superseded once `compute_contact_resistance` is calibrated and wired via steps 3–5, so it doesn't quietly become the permanent path.

**Test plan:** the unit tests from task 1; an integration test in `quality_bridge_test.py`'s style (that file's existing pattern — in-process `SimBridgeServicer.RunBatchTest` calls, no gRPC transport — is directly reusable) confirming `R_contact` actually moves `r_internal_penalty`-equivalent resistance in the expected direction as pressure moves away from `4.25 MPa` in *either* direction; a backward-compatibility test confirming default `p_clamp_mpa=0.0`/`gdl_porosity=0.78` (proto3 defaults) doesn't silently produce a nonsensical `R_contact` at `P=0` (the function's `p_safe = max(0.5, p_assembly_mpa)` floor should already handle this — confirm it does).

**Effort:** S/M (down from the prior plan's "M" — the core function and its Bruggeman conductivity sibling already exist; the remaining work is the self-test, the formula-provenance decision, three new proto fields, and the additive-wiring integration, not new physics). **Depends on:** §4.2 (needs `p_clamp_mpa` returned) and, for a trustworthy `gdl_porosity`, §4.4's real GDL compression data (though the wiring itself can and should land before that, using illustrative values, exactly as the rest of §4 does).

### 4.8 Optional: live gRPC integration (Phase 6b-style)

Only pursue once §4.4/§4.6's offline validation results justify it. Unchanged from the prior plan except:

1. New RPC(s): shared `RunStationMechanisticTest`, consistent with §3.1's shared-infra recommendation.
2. `BaseStationArtifact.java` gains a mechanistic mode (boolean/enum toggle at `init()`), pure-stochastic mode remains the fast-path default.
3. Extend `QualityProfile`/`recordStationQuality` per §3.1's `MechanisticSignal` design — add the parallel `recordMechanisticQuality` op, don't overload the existing 4-argument signature.
4. Any new RNG draws inside the mechanistic kernels must be seeded from the same `stationId.hashCode() ^ runId` scheme (confirmed this is exactly what `BaseStationArtifact.init()` does today) or `SeededReplayTests.java` will correctly fail.

**Test plan:** `SeededReplayTests.java` full regression; **the new `station_mechanistic_test.py` module from §1.6** (not a `parity_test.py` extension) covering `simulate_stage1_stamping`/`simulate_stage2_clamping` (now `station3_.../station4_...`).

**Effort:** XL, scope as its own milestone once §4.4–§4.6 findings are in.

**R10 overall effort:** M/L for §4.1–§4.7 (mostly data-sourcing plus low-risk refactors, and now a smaller integration task at §4.7 than previously scoped); XL if §4.8 is pursued.
**Depends on:** nothing blocking for §4.1–§4.2, §4.4a, §4.6 (start immediately); §4.7 depends on §4.2 and benefits from, but doesn't strictly require, §4.4's real data; §4.8 depends on §4.4–§4.6's findings justifying it.

---

## 5. Newly surfaced scope items (not present in the prior plan)

1. **§1.1 / §4.7** — R1 Milestone 2's core function exists; the milestone is smaller than previously scoped, but it also inherits a "no tests, unlabeled formula provenance" debt that needs paying down as part of closing it out.
2. **§1.2 / §4.4a** — a same-day, data-independent bug fix (`EPS_P_SCALE` self-consistency) that should land before Group B data-sourcing begins, or the harness will still fail once real data arrives.
3. **§1.7** — `rh_anode` is a dead input with no upstream producer; explicitly out of scope here, but named so it isn't lost a second time.
4. **§1.8** — the dual-proto-file maintenance burden is pre-existing but now directly relevant, since this plan adds three fields (`p_clamp_mpa`, `gdl_porosity`, `j_lim_derate_fraction`) across two PRs; add a checklist step to every PR in §4.7/§3.5 confirming both `.proto` copies and both generated-stub sets were updated together.

---

## 6. Revised sequencing

```
Immediate, parallelizable, no blockers:
  §4.1   Station-identity fix (team decision + 1-line change)     — blocking everything else in §4
  §4.2   p_clamp_mpa return-tuple fix                             — trivial
  §4.4a  Fix EPS_P_SCALE self-consistency (data-independent bug)  — same-day, do before §4.4's data-sourcing work
  §4.4   Source Group B constants                                 — data-sourcing, longest lead time, start now

Once §4.1–§4.2 land:
  §4.3   Rename/split modules
  §4.5   Extend calibration harness (Station 4 check)
  §4.6   Ship offline calibration script                           — R10's near-term deliverable

Can start immediately, independent of §4.4's real-data gate:
  §4.7 tasks 1-2   microstructure.py self-test + formula-provenance decision
  §4.7 tasks 3-5   proto fields + sim_bridge_server.py wiring + Java MechanisticSignal passthrough
                   (uses illustrative gdl_porosity until §4.4 lands, same convention as the rest of §4)

In parallel with all of the above (independent track):
  §3.2   Station 1 research spike + offline module
  §3.3   Station 2 research spike + offline module — highest-value target for live wiring first,
         since ecsa_ratio's wire path already exists end-to-end

Only after offline findings justify it, scoped separately, each its own XL:
  §3.2/§3.3 live wiring (Phase 6b, Stations 1/2)
  §4.8      live wiring (Phase 6b, Stations 3/4)

Explicitly out of scope, flagged for future consideration:
  rh_anode producer (§1.7) — needs its own research spike, no current candidate station owns it
```

---

## 7. Effort/impact summary

| Item | Prior plan's estimate | Revised estimate | Why it changed |
|---|---|---|---|
| R1 M2 / `R_contact(P_assembly)` (§4.7) | M ("build") | S/M ("integrate + test + decide formula provenance") | Function already exists; work is testing, proto wiring, and a labeling decision, not new physics |
| `EPS_P_SCALE` fix (§4.4a) | *(not identified as separate)* | XS, same-day | New finding — a data-independent bug, not a data-sourcing wait |
| R10 §4.1–§4.6 | M/L | M/L (unchanged) | Fully re-verified as accurate |
| R6 §3.2/§3.3 (Stations 1/2) | L / L | L / L (unchanged) | Fully re-verified as accurate |
| §3.5 (`j_lim` parameterization) | M | M (unchanged) | Fully re-verified as accurate |
| Test tooling for §4.8/§3.5 | "extend `parity_test.py`" | New `station_mechanistic_test.py` module | `parity_test.py` checks a different thing (compiled-vs-fallback), doesn't apply |
