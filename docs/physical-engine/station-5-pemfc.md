# Station 5: PEMFC Electrochemistry & Testing (Reference)

This document presents the non-linear electrochemistry, Butler–Volmer reaction kinetics, Springer membrane hydration model, and polarization curve equations for **Station 5: Quality Testing & PEMFC Performance Verification**.

---

## Physical Process Description

Station 5 subjects assembled fuel cell stacks to end-of-line electrical and gas crossover diagnostics. It simulates IV polarization curves, cell voltage distributions, activation losses, ohmic resistance, and mass transport limitation current densities $j_{\mathrm{lim}}$.

---

## Mathematical Formulation

### 1. Polarization Cell Voltage Equation

Cell voltage $V_{\mathrm{cell}}$ at current density $j$ ($\mathrm{A/cm}^2$) follows the **subtractive** fuel cell convention:

$$V_{\mathrm{cell}}(j) = E_{\mathrm{Nernst}} - \eta_{\mathrm{act}} - \eta_{\mathrm{ohm}} - \eta_{\mathrm{conc}}$$

$$V_{\mathrm{stack}}(j) = N_{\mathrm{cells}} \cdot V_{\mathrm{cell}}(j)$$

### 2. Activation Overpotential (Butler–Volmer 4-Electron ORR Kinetics)

Cathodic Oxygen Reduction Reaction (ORR) activation overpotential $\eta_{\mathrm{act}}$ accounts for the **$z = 4$** electron transfer pathway:

$$\eta_{\mathrm{act}} = \frac{R T}{\alpha_{\mathrm{orr}} z F} \ln\left( \frac{j}{j_0} \right)$$

where:
* **$\alpha_{\mathrm{orr}} = 0.50$** — Charge transfer coefficient.
* **$z = 4$** — ORR electron transfer number (hard runtime assertion).
* **$j_0$** — Arrhenius temperature & ECSA scaled exchange current density ($j_{0,\mathrm{ref}} = 2.5 \times 10^{-8}\mathrm{ A/cm}_{\mathrm{Pt}}^2$, $E_{\mathrm{act}} = 68.5\mathrm{ kJ/mol}$; Gasteiger et al. 2005; Neyerlin et al. 2006):

$$j_0 = j_{0,\mathrm{ref}} \cdot \mathrm{ECSA}_{\mathrm{ratio}} \cdot \exp\left( -\frac{E_{\mathrm{act}}}{R T} \left( 1 - \frac{T}{T_{\mathrm{ref}}} \right) \right)$$

### 3. Ohmic Overpotential & Springer Membrane Hydration

Ohmic overpotential $\eta_{\mathrm{ohm}}$ incorporates bulk contact resistance $R_{\mathrm{internal}}$ and membrane ionic resistance $R_{\mathrm{mem}}$:

$$\eta_{\mathrm{ohm}} = j \cdot \left( R_{\mathrm{internal}} + R_{\mathrm{mem}}(\lambda, T) \right)$$

Membrane thickness is $t_{\mathrm{mem}} = 50.0\ \mu\mathrm{m}$ ($0.005\mathrm{ cm}$). Conductivity $\sigma_{\mathrm{mem}}$ ($\mathrm{S/cm}$) follows Springer's model for water content $\lambda \in [1, 14]$:

$$\sigma_{\mathrm{mem}}(\lambda, T) = (0.005139 \lambda - 0.00326) \exp\left( 1268 \left( \frac{1}{303.15} - \frac{1}{T} \right) \right)$$

$$R_{\mathrm{mem}} = \frac{t_{\mathrm{mem}}}{\sigma_{\mathrm{mem}}(\lambda, T)}$$

### 4. Mass Transport Concentration Overpotential

Concentration overpotential $\eta_{\mathrm{conc}}$ uses an empirical logarithmic formulation with a $C^1$ continuity patch at $j / j_{\mathrm{lim}} > 0.99$ ($B = 0.05$, $j_{\mathrm{lim}} = 2.5\mathrm{ A/cm}^2$):

$$\eta_{\mathrm{conc}} = -B \ln\left(1 - \frac{j}{j_{\mathrm{lim}}}\right) \quad \text{for } \frac{j}{j_{\mathrm{lim}}} \le 0.99$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| ORR Exchange Current | $j_{0,\mathrm{ref}}$ | $2.5 \times 10^{-8}$ | $\mathrm{A/cm}_{\mathrm{Pt}}^2$ | Gasteiger et al. (2005) [DOI: 10.1016/j.apcatb.2004.06.021] |
| ORR Activation Energy | $E_{\mathrm{act}}$ | $68.5$ | $\mathrm{kJ/mol}$ | Neyerlin et al. (2006) [DOI: 10.1149/1.2266294] |
| Electron Transfer Number | $z$ | $4$ | — | 4-Electron ORR Pathway |
| Charge Transfer Coeff. | $\alpha_{\mathrm{orr}}$ | $0.50$ | — | Kinetic Parameter |
| Membrane Thickness | $t_{\mathrm{mem}}$ | $50.0$ ($0.005\mathrm{ cm}$) | $\mu\mathrm{m}$ | Nafion Membrane Specs |
| Limiting Current | $j_{\mathrm{lim}}$ | $2.50$ | $\mathrm{A/cm}^2$ | Polarization Boundary |
| Concentration Coeff. | $B$ | $0.05$ | — | Fitted Empirical Constant |

---

## Code Reference

* Main Model: [`physical_engine/factory_simulation/pemfc_model.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/pemfc_model.py)
* Test Suite: [`physical_engine/factory_simulation/pemfc_test.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/pemfc_test.py)
