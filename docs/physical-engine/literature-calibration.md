# Literature Calibration & Empirical Validation

This document provides traceability for the physical parameters, kinetic constants, thermodynamic values, and empirical limits used in **Matrix Factory Twin**, linking code parameters to their primary literature sources.

---

## Comprehensive Parameter Master Table

| Physical Parameter | Code Symbol | Nominal Value | Unit | Claimed Reference | Verification |
| --- | --- | --- | --- | --- | --- |
| **Resin Activation Energy 1** | `E1_CURE` | $58.2$ | $\text{kJ/mol}$ | Fernandes et al. (2018), *Polym. Test.*, DOI `10.1016/j.polymertesting.2018.03.012` | Parameter source |
| **Resin Activation Energy 2** | `E2_CURE` | $68.5$ | $\text{kJ/mol}$ | Fernandes et al. (2018), *Polym. Test.*, DOI `10.1016/j.polymertesting.2018.03.012` | Parameter source |
| **Slot-Die Line Speed** | `V_COAT_NOMINAL` | $0.15$ ($15\text{ cm/s}$) | $\text{m/s}$ | Standard slot-die machine operating window | Operating specification |
| **Cockcroft–Latham Threshold** | `C_CRIT_NCL` | $0.35$ | — | Modanloo et al. (2018) | Ductile fracture limit |
| **Sliding Contact Distance** | `S_SLIDE` | $0.002$ ($2.0\text{ mm}$) | $\text{m}$ | Die draw contact length | Contact geometry |
| **Critical Die Wear Volume** | `V_CRIT_WEAR` | $0.05$ | $\text{mm}^3$ | Allowable coating wear volume limit | Wear threshold |
| **316L Strength Coeff.** | `K_STRENGTH_316L` | $1280.0$ | $\text{MPa}$ | Blandford (2007) / Mahabunphachai & Koc (2008), DOI `10.1016/j.jmatprotec.2007.10.052` | Material property |
| **Duplex Coating Wear Coeff.** | `K_WEAR_DUPLEX` | $1.47 \times 10^{-10}$ | $\text{mm}^3/(\text{N}\cdot\text{m})$ | Bitay et al. (2021) | Die tribology coefficient |
| **PVD Coating Wear Coeff.** | `K_WEAR_PVD` | $3.50 \times 10^{-6}$ | $\text{mm}^3/(\text{N}\cdot\text{m})$ | Fernandes et al. (2017) | Die tribology coefficient |
| **Archard Wear Law** | `GAMMA_ARCHARD` | $1.35$ | — | Archard (1953), *J. Appl. Phys.*, DOI `10.1063/1.1721448` | Verified Archard relation |
| **GDL Initial Elasticity** | `GDL_E0_MPA` | $2.80$ | $\text{MPa}$ | Kleemann et al. (2009), *J. Power Sources*, DOI `10.1016/j.jpowsour.2009.01.076` | GDL mechanics |
| **GDL Non-Linear Stiffness** | `GDL_KS` | $28.5$ | — | Norouzifard & Bahrami (2014), *Int. J. Hydrogen Energy*, DOI `10.1016/j.ijhydene.2014.04.148` | GDL mechanics |
| **Carbon Fiber Bulk Conductivity** | `SIGMA_BULK` | $220.0$ | $\text{S/cm}$ | Toray TGP-H-060 Datasheet | Material property |
| **Baseline Contact Res. (coated)** | `R_CONTACT_0` | $0.0042$ ($4.20\text{ m}\Omega\cdot\text{cm}^2$) | $\Omega\cdot\text{cm}^2$ | El-Kharouf, Mason, Brett & Pollet (2012), DOI `10.1016/j.jpowsour.2012.06.099` | Verified GDL contact resistance |
| **Baseline Contact Res. (uncoated)** | `R_CONTACT_UNCOATED` | $0.0185$ ($18.50\text{ m}\Omega\cdot\text{cm}^2$) | $\Omega\cdot\text{cm}^2$ | El-Kharouf, Mason, Brett & Pollet (2012), DOI `10.1016/j.jpowsour.2012.06.099` | Verified GDL contact resistance |
| **Micro-Crack Contact Penalty Coeff.** | `BETA_CRACK` | $0.15$ | — | Micro-crack stress non-uniformity factor | Degradation parameter |
| **ORR Exchange Current** | `j0_orr` | $2.5 \times 10^{-8}$ | $\text{A/cm}_{\text{Pt}}^2$ | Gasteiger et al. (2005), *Appl. Catal. B*, DOI `10.1016/j.apcatb.2004.06.021` | ORR kinetic parameter |
| **ORR Activation Energy** | `E_act` | $68.5$ | $\text{kJ/mol}$ | Neyerlin et al. (2006), *J. Electrochem. Soc.*, DOI `10.1149/1.2266294` | ORR activation energy |
| **Nafion Hydration Model** | `lambda_mem` | $14.0$ | — | Springer et al. (1991), *J. Electrochem. Soc.*, DOI `10.1149/1.2085971` | Sorption isotherm model |
| **Stack Characteristic Length** | `L_STACK` | $0.05$ ($5.0\text{ cm}$) | $\text{m}$ | Stack thermal geometry | Geometric parameter |
| **Effective Thermal Conductivity** | `K_EFF_THERMAL` | $1.25$ | $\text{W/(m}\cdot\text{K)}$ | Stack composite thermal property | Thermal property |
| **Core-Skin Temp. Threshold** | `DELTA_T_YONKIST` | $15.0$ | $\text{K}$ | Yonkist stability criterion | Thermal stability bound |
| **Reversible Entropic Potential** | `E_ENTROPIC` | $0.23$ | $\text{V}$ | Thermodynamic entropic term ($-T\Delta S/zF$) | Reversible heat term |
| **Die Draft/Friction Constants** (`μ0`, `α_f`, `θ_die`, `ε_p,scale`) | see [Station 3](station-3-stamping.md) | various | various | Process Calibration Baseline | Calibrated fit |
| **Bruggeman Exponent** | `BRUGGEMAN_EXP` | $1.5$ | — | Bruggeman (1935) | Fibrous porous media standard |

### Contact Resistance Primary Reference

Both baseline contact resistance values ($R_{\text{contact},0}$ for coated plates and $R_{\text{contact,uncoated}}$ for uncoated 316L plates) stem from the characterization dataset in:

> El-Kharouf, A.; Mason, T. J.; Brett, D. J. L.; Pollet, B. G. (2012). "Ex-situ characterisation of gas diffusion layers for proton exchange membrane fuel cells." *Journal of Power Sources*, 218, 393–404. **DOI: `10.1016/j.jpowsour.2012.06.099`.**

---

## Validation & Calibration Methodology

Parameters were validated through a multi-stage calibration process:

1. **Station-Level Independent Optimization:** Fitting JIT physics kernel outputs against target defect-rate/operating-range specifications using numerical sanity check functions (`run_calibration_sanity_checks()`), present in each station module.
2. **Cross-Station Monte Carlo Verification:** `physical_engine/scripts/calibrate_stamping_clamping.py` runs 10,000-iteration Monte Carlo sweeps for Stations 1–4, checking that nominal conditions stay non-defective and that injected process noise reproduces target defect rates (Station 3 targets 0.20% defect rate, Station 4 targets 0.80%).
3. **Cross-Station Propagation Bounds:** Verifying that outputs from upstream stations (e.g., Station 3 micro-cracks or Station 4 clamping pressure $P_{\text{clamp}}$) fall within valid physical operational envelopes before entering downstream Station 5 polarization solvers, via the coupling equation documented in [Station 5 §6](station-5-pemfc.md#6-manufacturing-to-performance-coupling).
