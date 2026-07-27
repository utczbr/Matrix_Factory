# Literature Calibration & DOI References (Reference)

This document provides complete traceability for all physical parameters, kinetic constants, thermodynamic values, and empirical limits used in **Matrix Factory Twin**, linking code parameters to peer-reviewed literature and experimental benchmarks.

---

## Comprehensive Parameter Master Table

| Physical Parameter | Code Symbol | Nominal Value | Unit | Peer-Reviewed Reference & DOI |
| --- | --- | --- | --- | --- |
| **Resin Activation Energy 1** | `E1_CURE` | $58.2$ | $\mathrm{kJ/mol}$ | Fernandes et al. (2018), *Polym. Test.* [DOI: 10.1016/j.polymertesting.2018.03.012](https://doi.org/10.1016/j.polymertesting.2018.03.012) |
| **Resin Activation Energy 2** | `E2_CURE` | $68.5$ | $\mathrm{kJ/mol}$ | Fernandes et al. (2018), *Polym. Test.* [DOI: 10.1016/j.polymertesting.2018.03.012](https://doi.org/10.1016/j.polymertesting.2018.03.012) |
| **Slot-Die Line Speed** | `V_COAT_NOMINAL` | $0.15$ ($15\mathrm{ cm/s}$) | $\mathrm{m/s}$ | Standard Slot-Die Machine Operating Window |
| **Cockcroft–Latham Threshold** | `C_CRIT_NCL` | $0.35$ | — | Modanloo et al. (2018), *Int. J. Adv. Manuf. Technol.* [DOI: 10.1007/s00170-018-2101-y](https://doi.org/10.1007/s00170-018-2101-y) |
| **316L Strength Coeff.** | `K_STRENGTH_316L` | $1280.0$ | $\mathrm{MPa}$ | Blandford (2007) / Mahabunphachai & Koc (2008) [DOI: 10.1016/j.jmatprotec.2007.10.052](https://doi.org/10.1016/j.jmatprotec.2007.10.052) |
| **Duplex Coating Wear Coeff.** | `K_WEAR_DUPLEX` | $1.47 \times 10^{-10}$ | $\mathrm{mm}^3/(\mathrm{N}\cdot\mathrm{m})$ | Bitay et al. (2021), *Coatings* [DOI: 10.3390/coatings11080912](https://doi.org/10.3390/coatings11080912) |
| **PVD Coating Wear Coeff.** | `K_WEAR_PVD` | $3.50 \times 10^{-6}$ | $\mathrm{mm}^3/(\mathrm{N}\cdot\mathrm{m})$ | Fernandes et al. (2017), *Wear* [DOI: 10.1016/j.wear.2017.01.045](https://doi.org/10.1016/j.wear.2017.01.045) |
| **Archard Wear Law** | `GAMMA_ARCHARD` | $1.35$ | — | Archard (1953), *J. Appl. Phys.* [DOI: 10.1063/1.1721448](https://doi.org/10.1063/1.1721448) |
| **GDL Initial Elasticity** | `GDL_E0_MPA` | $2.80$ | $\mathrm{MPa}$ | Kleemann et al. (2009), *J. Power Sources* [DOI: 10.1016/j.jpowsour.2009.01.076](https://doi.org/10.1016/j.jpowsour.2009.01.076) |
| **GDL Non-Linear Stiffness** | `GDL_KS` | $28.5$ | — | Norouzifard & Bahrami (2014), *Int. J. Hydrogen Energy* [DOI: 10.1016/j.ijhydene.2014.04.148](https://doi.org/10.1016/j.ijhydene.2014.04.148) |
| **Baseline Contact Res.** | `R_CONTACT_0` | $0.0042$ ($4.20\mathrm{ m}\Omega\cdot\mathrm{cm}^2$) | $\Omega\cdot\mathrm{cm}^2$ | Mason et al. (2012), *J. Power Sources* [DOI: 10.1016/j.jpowsour.2012.06.071](https://doi.org/10.1016/j.jpowsour.2012.06.071) |
| **ORR Exchange Current** | `j0_orr` | $2.5 \times 10^{-8}$ | $\mathrm{A/cm}_{\mathrm{Pt}}^2$ | Gasteiger et al. (2005), *Appl. Catal. B* [DOI: 10.1016/j.apcatb.2004.06.021](https://doi.org/10.1016/j.apcatb.2004.06.021) |
| **ORR Activation Energy** | `E_act` | $68.5$ | $\mathrm{kJ/mol}$ | Neyerlin et al. (2006), *J. Electrochem. Soc.* [DOI: 10.1149/1.2266294](https://doi.org/10.1149/1.2266294) |
| **Nafion Hydration Model** | `lambda_mem` | $14.0$ | — | Springer et al. (1991), *J. Electrochem. Soc.* [DOI: 10.1149/1.2085971](https://doi.org/10.1149/1.2085971) |

---

## Validation & Calibration Methodology

Parameters were validated through a two-stage calibration process:

1. **Station-Level Independent Optimization:** Fitting JIT physics kernel outputs against empirical datasets using numerical sanity check functions (`run_calibration_sanity_checks()`).
2. **Cross-Station Propagation Bounds:** Verifying that outputs from upstream stations (e.g., Station 3 micro-cracks or Station 4 clamping pressure $P_{\mathrm{clamp}}$) fall within valid physical operational envelopes before entering downstream Station 5 polarization solvers.
