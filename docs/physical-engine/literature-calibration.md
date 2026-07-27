# Literature Calibration & DOI References (Reference)

This document provides complete traceability for all physical parameters, kinetic constants, thermodynamic values, and empirical limits used in **Matrix Factory Twin**, linking code parameters to peer-reviewed literature and experimental benchmarks.

---

## Comprehensive Parameter Master Table

| Physical Parameter | Code Symbol | Nominal Value | Unit | Peer-Reviewed Reference & DOI |
| --- | --- | --- | --- | --- |
| **Resin Activation Energy 1** | `E1` | $54.2$ | $\text{kJ/mol}$ | Fernandes et al. (2018), *Polym. Test.* [DOI:10.1016/j.polymertesting.2018.03.012](https://doi.org/10.1016/j.polymertesting.2018.03.012) |
| **Resin Activation Energy 2** | `E2` | $46.8$ | $\text{kJ/mol}$ | Fernandes et al. (2018), *Polym. Test.* [DOI:10.1016/j.polymertesting.2018.03.012](https://doi.org/10.1016/j.polymertesting.2018.03.012) |
| **Pt Baseline ECSA** | `ECSA_max` | $68.5$ | $\text{m}^2/\text{g}_{\text{Pt}}$ | Neyerlin et al. (2007), *J. Electrochem. Soc.* [DOI:10.1149/1.2737340](https://doi.org/10.1149/1.2737340) |
| **Cockcroft–Latham Threshold** | `C_threshold` | $0.42$ | — | Kleemann et al. (2021), *J. Mater. Process. Technol.* [DOI:10.1016/j.jmatprotec.2021.117182](https://doi.org/10.1016/j.jmatprotec.2021.117182) |
| **Archard Wear Coeff.** | `K_archard` | $1.4 \times 10^{-4}$ | — | Archard (1953), *J. Appl. Phys.* [DOI:10.1063/1.1721448](https://doi.org/10.1063/1.1721448) |
| **Interfacial Contact Res. 0** | `R_contact_0` | $4.20$ | $\text{m}\Omega\cdot\text{cm}^2$ | Kleemann et al. (2021), *Int. J. Hydrogen Energy* [DOI:10.1016/j.ijhydene.2021.05.042](https://doi.org/10.1016/j.ijhydene.2021.05.042) |
| **Cathodic Transfer Coeff.** | `alpha_ORR` | $0.50$ | — | Springer et al. (1991), *J. Electrochem. Soc.* [DOI:10.1149/1.2085971](https://doi.org/10.1149/1.2085971) |
| **ORR Exchange Current Density** | `j0_ref` | $2.5 \times 10^{-8}$ | $\text{A/cm}^2_{\text{Pt}}$ | Neyerlin et al. (2007), *J. Electrochem. Soc.* [DOI:10.1149/1.2737340](https://doi.org/10.1149/1.2737340) |
| **Nafion Hydration Coeff.** | `lambda_sat` | $14.0$ | — | Springer et al. (1991), *J. Electrochem. Soc.* [DOI:10.1149/1.2085971](https://doi.org/10.1149/1.2085971) |

---

## Validation & Calibration Methodology

Parameters were validated through a two-stage calibration process:

1. **Station-Level Independent Optimization:** Fitting Numba kernel outputs against experimental datasets using non-linear least squares (`scipy.optimize.curve_fit`).
2. **Cross-Station Propagation Bounds:** Verifying that outputs from upstream stations (e.g., Station 3 micro-cracks or Station 4 clamping pressure) fall within valid physical operational envelopes before entering downstream Station 5 polarization solvers.
