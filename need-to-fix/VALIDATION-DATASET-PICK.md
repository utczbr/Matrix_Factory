# Validation Dataset Pick (for your confirmation)

## The pick

**EH-31 PEMFC polarization curves from Gass, Li, Outbib, Jemei & Hissel**, *"An advanced 1D physics-based model for PEM hydrogen fuel cells with enhanced overvoltage prediction"*, arXiv:2404.07508 (v2, 27 Jan 2026; preprint submitted to *Int. J. Hydrogen Energy*). Parameter tables: Tables 4, 9, 10, 11, 12; curves: Fig. 4 (and Fig. 9 for the 1.5 bar case).
Numeric points + operating conditions: **AlphaPEM** repository, `data/EH/` (BSD-3-Clause, © 2026 Raphaël Gass), pinned at commit `bd286b5e2fc994cc5c8fb12b2a5a1fd75acf01ea` (package v2.0.0).

### Why this one

| Requirement you gave | EH-31 |
|---|---|
| Published | Peer-review-track paper + open-source data/code (SoftwareX companion: doi:10.1016/j.softx.2024.102002, cited as ref [40]) |
| **Complete parameter tables** | Yes, *and* the paper separates **measured** (A_act = 85 cm², channel width 450 µm, channel length 9.67 m) from **estimated** (membrane 20 µm, CL 10 µm, GDL 200 µm, channel height 500 µm) values (Table 10) |
| Operating conditions stated | T = 74 °C (347.15 K), P_a = P_c ∈ {1.5, 2.0, 2.25, 2.5} bar, S_a/S_c = 1.2/2.0, RH_a/RH_c = 0.4/0.6, H₂/air |
| Numeric (not just a figure) | Yes: arrays `i_exp` (A/cm²) and `U_exp` (V), plus a `before_voltage_drop` subset for each curve |
| Held-out protocol already exists | The paper calibrates on 2.0 and 2.25 bar and validates on 2.5 bar, reporting max deviation ≤ 1.2 % (calibration) / ≤ 1.8 % (held-out) for its 1D two-phase model |

### Data inventory (verified by me)

| Curve | P (bar) | n points (full) | i_max (A/cm²) | n pre-drop | SHA-256 |
|---|---|---|---|---|---|
| `Pa_2_0.yml` | 2.00 | 49 | 2.46 | 28 | `ca37a5cf91e5e4740988449f059e3c575bd121e773341c58aafc80e9fc2aaf02` |
| `Pa_2_25.yml` | 2.25 | 54 | 2.79 | 33 | `c1dd8fd9bbb5ff7a8880efa17581deacbbb10e8db083bd053c4f008df8419544` |
| `Pa_2_5.yml` | 2.50 | 56 | 2.99 | 33 | `e68a22d78f6d2c7a0c6776e2eec69e1456a82ca4abf7ac2a8a879f0628c6dff4` |
| `nominal.yml` | 1.50 | 37 | 2.25 | 29 | `2db1db361ee1842c4379cbe9245437437eee422d1e3006bf966947e49a64e4a8` |
| `stack.jl` (parameters) | n/a | n/a | n/a | n/a | `b8031bd2fd27ed554f8d9500448bf752d02e8e895cd48e77570f44e15ff165bd` |

Voltages are per cell (0.900 V at 0.050 A/cm²).

## Caveats you should weigh before confirming

1. **Manufacturer-supplied curves.** `source:` in each file is ehgroup.ch. The paper itself raises the possibility that the vendor swept dynamically rather than at steady state (relevant to the 1.5 bar curve). Treat this as a *published reference curve for model adequacy*, not ground truth.
2. **Redistribution.** The repo's BSD-3 licence covers the code; the data's origin is the vendor. I recommend committing the four small fixtures with an attribution note and asking the author if you want certainty. *(Your call: see questions.)*
3. **Calibrated values drift between paper and repo.** Paper Table 12 (i₀,c = 2.79 A/m², κ_c = 1.61, ε_gdl = 0.701, R_e = 5.7·10⁻⁷ Ω·m²) ≠ repo `stack.jl` (i₀,c = 14.43, κ_c = 0.4152, ε_gdl = 0.5002, R_e = 1.0·10⁻⁶, H_mem = 16.06 µm). That is why the commit is pinned, and why **we do not reuse their calibrated values** (they are specific to a 1D two-phase model). We reuse only measured/estimated geometry and operating conditions.
4. **Pt loading and ECSA are not given**, so the roughness factor must be *fitted within physical bounds*, not looked up.
5. **One temperature (74 °C)**: this dataset cannot validate the temperature dependence of the model. (See the optional second dataset below.)
6. **YAML pitfall:** PyYAML parses `2.0e5` as a **string** (YAML 1.1 needs `2.0e+5`); all 12 files hit this. The loader must coerce with `float()`, and a unit test will pin it.
7. **Not checked:** I compared the arrays only against the repo, **not** against Fig. 4 of the paper (I had text, not images). Please eyeball ~3 points per curve against Fig. 4 once.

## Proposed validation protocol (full detail goes into `SPEC-pemfc-validation.md`)

Designed to attack the identifiability problem found in the audit (P-02): each parameter is either **fixed from literature** or **fitted within physical bounds on the region that identifies it**.

| Stage | Data | Free parameters | Fixed |
|---|---|---|---|
| 1: kinetics + ohmic | 2.0 and 2.25 bar, **pre-voltage-drop** points | roughness factor *rf* ∈ [20, 600]; lumped R ∈ [0.02, 0.25] Ω·cm² | Tafel α·n = 1.0; E_act; Nernst; hydration |
| 2: mass transport | **full** curves 2.0 and 2.25 bar | j_lim ∈ [2, 8] A/cm² | stage-1 values |
| Held-out | 2.5 bar and 1.5 bar | none | all |

### Feasibility evidence (my prototype, **not** repo code; ideal-gas activities, Buck p_sat, j₀ ∝ a_O₂, fixed concentration slope; indicative only)

| Model | Fitted | Cal RMSE 2.0 / 2.25 bar | **Held-out 2.5 bar** (RMSE / max) | Held-out 1.5 bar |
|---|---|---|---|---|
| Repo kinetics **as-is** (α·z = 2, ECSA ≤ 1) | R = 0.088, **ECSA = 0.05 (bound)**, **j_lim = 6.0 (bound)** | 27.4 / 23.3 mV | **25.6 / 48.6 mV** | 43.5 mV |
| Corrected (α·n = 1), staged | **rf = 426**, R = 0.072 Ω·cm², j_lim = 2.99 | 7.4 / 5.3 mV | **9.1 / 17.6 mV** | 27.4 mV |

**Identifiability result** (why the slope is fixed, not fitted):

| α·n | rf needed | Cal RMSE | Verdict |
|---|---|---|---|
| 1.00 | 426 | 7.4 / 5.3 mV | plausible rf |
| 0.85 | **2149** | 6.3 / 5.1 mV | fits equally well, **implausible rf** (would mean >1000 cm²_Pt/cm²_geo) |
| 0.70 | 3000 (bound) | 36 / 40 mV | fails |

Fit quality alone cannot tell α·n = 0.85 from 1.0; only the physical bound on *rf* can. That is exactly the compensation problem hiding in the current code.

### Proposed gates (**numbers to confirm**: derived as roughly 1.5–2× the source paper's own held-out error, widened because ours is a 2-parameter lumped model)

| ID | Gate |
|---|---|
| V-1 | Fixtures match the SHA-256 above; loader coerces string floats |
| V-2 | Stage-1 calibration RMSE ≤ **10 mV** on each of 2.0 and 2.25 bar (pre-drop) |
| V-3 | Held-out 2.5 bar (pre-drop): RMSE ≤ **15 mV**, max |error| ≤ **30 mV** |
| V-4 | No fitted parameter within 2 % of its bound |
| V-5 | Held-out 1.5 bar (pre-drop): RMSE ≤ **35 mV** as a *guard rail only* (source paper flags this curve as difficult) |
| V-6 | Stage-2 j_lim inside [2, 8]; full-curve RMSE **reported, not gated** (pressure dependence of mass transport is not in a single-j_lim model; prototype held-out full-curve RMSE was 35 mV at 2.5 bar) |
| V-7 | **Negative control:** the same harness on an in-test copy of the *current* kinetics must **fail** V-3 or V-4 (shows the gate can fail) |
| V-8 | Identifiability table (α·n ∈ {0.85, 1.0}) regenerated and asserted: rf(0.85) > rf_max |

## Optional second dataset (only if you confirm)

**ZSW HyFaB Generic Stack**: Zenodo DOI 10.5281/zenodo.14223364 (ZSW open-design stack; confirmed to exist and to be used for third-party model validation), transcribed in AlphaPEM `data/ZSW/2024/pola/` (8 curves: **temperature sweep 62/76/84 °C**, four pressure variants, nominal 68 °C; 26 cells, 283.87 cm²; anode H₂/N₂ 70/30; S_a = S_c = 1.6).
*Value:* the only way to validate the **temperature dependence** of Tafel slope / j₀ Arrhenius (it is exactly what the P-01 fix changes).
*Limits:* I could not open the Zenodo files from the sandbox, so the transcription is unchecked against the source; some "parameters" in its `stack.jl` are clearly **optimiser outputs** (e.g. `Hgdl = 89.236…e-6`), not measurements; `T_des` is the coolant temperature, not cell temperature.

## Fallback if EH-31 data licensing is a blocker

A CC-BY dataset of a 50 cm² PEM cell with polarization curves repeated three times across temperature, pressure and cathode stoichiometry (*Data* 2020, 5(2), 47: Ramírez-Cruzado et al.). I saw only its abstract; its parameter tables are **not evaluated**.

## What I need from you

1. **Confirm EH-31 (Gass et al.) as the primary validation dataset?**
2. **Fixtures committed with attribution** (default) or ask the author first?
3. **Gate numbers V-2…V-5 acceptable?** (They get re-baselined only by your decision, never auto-relaxed.)
4. **Add ZSW as an optional temperature-dependence check?** (default: *no*, revisit after `pemfc-validation` v1)
