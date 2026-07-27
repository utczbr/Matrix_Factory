# Station 5: PEMFC Electrochemistry & Testing (Reference)

This document presents the non-linear electrochemistry, Butler–Volmer reaction kinetics, Springer membrane hydration model, and polarization curve equations for **Station 5: Quality Testing & PEMFC Performance Verification**.

---

## Physical Process Description

Station 5 subjects assembled fuel cell stacks to end-of-line electrical and gas crossover diagnostics. It simulates IV polarization curves, cell voltage distributions, activation losses, ohmic resistance, and mass transport limitation current densities $j_{\text{lim}}$.

---

## Mathematical Formulation

### 1. Polarization Cell Voltage Equation

Cell voltage $V_{\text{cell}}$ at current density $j$ ($\text{A/cm}^2$) follows the **subtractive** fuel cell convention:

$$V_{\text{cell}}(j) = E_{\text{Nernst}} - \eta_{\text{act}} - \eta_{\text{ohm}} - \eta_{\text{conc}}$$

$$V_{\text{stack}}(j) = N_{\text{cells}} \cdot V_{\text{cell}}(j)$$

### 2. Activation Overpotential (Butler–Volmer 4-Electron ORR Kinetics)

Cathodic Oxygen Reduction Reaction (ORR) activation overpotential $\eta_{\text{act}}$ accounts for the **$z = 4$** electron transfer pathway:

$$\eta_{\text{act}} = \frac{R T}{\alpha_{\text{orr}} z F} \ln\left( \frac{j}{j_0} \right)$$

where:
* **$\alpha_{\text{orr}} = 0.50$** — Charge transfer coefficient.
* **$z = 4$** — ORR electron transfer number (hard runtime assertion).
* **$j_0$** — Arrhenius temperature & ECSA scaled exchange current density ($j_{0,\text{ref}} = 2.5 \times 10^{-8}\text{ A/cm}_{\text{Pt}}^2$, $E_{\text{act}} = 68.5\text{ kJ/mol}$; Gasteiger et al. 2005; Neyerlin et al. 2006):

$$j_0 = j_{0,\text{ref}} \cdot \text{ECSA}_{\text{ratio}} \cdot \exp\left( -\frac{E_{\text{act}}}{R T} \left( 1 - \frac{T}{T_{\text{ref}}} \right) \right)$$

### 3. Ohmic Overpotential & Springer Membrane Hydration

Ohmic overpotential $\eta_{\text{ohm}}$ incorporates bulk contact resistance $R_{\text{internal}}$ and membrane ionic resistance $R_{\text{mem}}$:

$$\eta_{\text{ohm}} = j \cdot \left( R_{\text{internal}} + R_{\text{mem}}(\lambda, T) \right)$$

Membrane thickness is $t_{\text{mem}} = 50.0\ \mu\text{m}$ ($0.005\text{ cm}$). Conductivity $\sigma_{\text{mem}}$ ($\text{S/cm}$) follows Springer's model for water content $\lambda \in [1, 14]$:

$$\sigma_{\text{mem}}(\lambda, T) = (0.005139 \lambda - 0.00326) \exp\left( 1268 \left( \frac{1}{303.15} - \frac{1}{T} \right) \right)$$

$$R_{\text{mem}} = \frac{t_{\text{mem}}}{\sigma_{\text{mem}}(\lambda, T)}$$

### 4. Mass Transport Concentration Overpotential

Concentration overpotential $\eta_{\text{conc}}$ uses an empirical logarithmic formulation with a $C^1$ continuity patch at $j / j_{\text{lim}} > 0.99$ ($B = 0.05$, $j_{\text{lim}} = 2.5\text{ A/cm}^2$):

$$\eta_{\text{conc}} = -B \ln\left(1 - \frac{j}{j_{\text{lim}}}\right) \quad \text{for } \frac{j}{j_{\text{lim}}} \le 0.99$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| ORR Exchange Current | $j_{0,\text{ref}}$ | $2.5 \times 10^{-8}$ | $\text{A/cm}_{\text{Pt}}^2$ | Gasteiger et al. (2005) [DOI: 10.1016/j.apcatb.2004.06.021] |
| ORR Activation Energy | $E_{\text{act}}$ | $68.5$ | $\text{kJ/mol}$ | Neyerlin et al. (2006) [DOI: 10.1149/1.2266294] |
| Electron Transfer Number | $z$ | $4$ | — | 4-Electron ORR Pathway |
| Charge Transfer Coeff. | $\alpha_{\text{orr}}$ | $0.50$ | — | Kinetic Parameter |
| Membrane Thickness | $t_{\text{mem}}$ | $50.0$ ($0.005\text{ cm}$) | $\mu\text{m}$ | Nafion Membrane Specs |
| Limiting Current | $j_{\text{lim}}$ | $2.50$ | $\text{A/cm}^2$ | Polarization Boundary |
| Concentration Coeff. | $B$ | $0.05$ | — | Fitted Empirical Constant |

---

## Code Reference

* Main Model: [`physical_engine/factory_simulation/pemfc_model.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/pemfc_model.py)
* Test Suite: [`physical_engine/factory_simulation/pemfc_test.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/pemfc_test.py)
