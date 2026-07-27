# Station 5: PEMFC Electrochemistry & Testing (Reference)

This document presents the non-linear electrochemistry, Butler–Volmer reaction kinetics, Springer membrane hydration model, and polarization curve equations for **Station 5: Quality Testing & PEMFC Performance Verification**.

---

## Physical Process Description

Station 5 subjects assembled fuel cell stacks to end-of-line electrical and gas crossover diagnostics. It simulates IV polarization curves, cell voltage distributions, activation losses, ohmic resistance, and mass transport limitation current densities $j_{\mathrm{lim}}$.

---

## Mathematical Formulation

### 1. Polarization Cell Voltage Equation

Cell voltage $V_{\mathrm{cell}}$ at current density $j$ ($\mathrm{A/cm}^2$) is governed by thermodynamic Nernst potential $E_{\mathrm{Nernst}}$ minus three loss overpotentials:

$$V_{\mathrm{cell}}(j) = E_{\mathrm{Nernst}} - \eta_{\mathrm{act}} - \eta_{\mathrm{ohmic}} - \eta_{\mathrm{trans}}$$

### 2. Activation Overpotential (Butler–Volmer Kinetics)

The cathode Oxygen Reduction Reaction (ORR) activation overpotential $\eta_{\mathrm{act}}$ is expressed via Tafel kinetics:

$$\eta_{\mathrm{act}} = \frac{R T}{\alpha_{\mathrm{ORR}} F} \ln\left( \frac{j + j_{\mathrm{loss}}}{j_0 \cdot \mathrm{ECSA} \cdot L_{\mathrm{Pt}}} \right)$$

where:
* $\alpha_{\mathrm{ORR}}$ is the cathodic charge transfer coefficient ($\approx 0.50$).
* $j_0$ is reference exchange current density ($\mathrm{A/cm}_{\mathrm{Pt}}^2$).
* $\mathrm{ECSA}$ is inherited from Station 2.

### 3. Ohmic Overpotential & Springer Membrane Hydration

Ohmic loss $\eta_{\mathrm{ohmic}}$ includes electronic membrane resistance $R_{\mathrm{mem}}$ and interfacial contact resistance $R_{\mathrm{contact}}$ (inherited from Station 4):

$$\eta_{\mathrm{ohmic}} = j \cdot \left( R_{\mathrm{mem}}(\lambda) + R_{\mathrm{contact}} \right)$$

Membrane ionic conductivity $\sigma_{\mathrm{mem}}$ depends on water content $\lambda \in [1, 14]$ (Springer model):

$$\sigma_{\mathrm{mem}}(\lambda, T) = (0.005139 \lambda - 0.00326) \exp\left( 1268 \left( \frac{1}{303} - \frac{1}{T} \right) \right)$$

$$R_{\mathrm{mem}} = \frac{t_{\mathrm{mem}}}{\sigma_{\mathrm{mem}}(\lambda, T)}$$

### 4. Mass Transport Concentration Overpotential

Concentration loss $\eta_{\mathrm{trans}}$ accounts for reactant gas starvation and liquid water flooding at high current densities:

$$\eta_{\mathrm{trans}} = -\frac{R T}{n F} \ln\left( 1 - \frac{j}{j_{\mathrm{lim}}} \right)$$

where mass transport limit current density $j_{\mathrm{lim}}$ is derated by GDL compression:

$$j_{\mathrm{lim}} = j_{\mathrm{lim},0} \cdot \left( \frac{\varepsilon_{\mathrm{gdl}}(P_{\mathrm{clamp}})}{\varepsilon_0} \right)^{1.5}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Reference Exchange Current | $j_0$ | $2.5 \times 10^{-8}$ | $\mathrm{A/cm}_{\mathrm{Pt}}^2$ | Neyerlin et al. (2007) |
| Charge Transfer Coeff. | $\alpha_{\mathrm{ORR}}$ | $0.50$ | — | Springer et al. (1991) |
| Membrane Thickness | $t_{\mathrm{mem}}$ | $15.0$ | $\mu\mathrm{m}$ | Nafion HP Datasheet |
| Baseline Limiting Current | $j_{\mathrm{lim},0}$ | $2.40$ | $\mathrm{A/cm}^2$ | Experimental Polarization |
| Membrane Water Content | $\lambda$ | $12.5$ | — | Relative Humidity = 80% |

---

## Code Reference

* Main Model: [`physical_engine/factory_simulation/pemfc_model.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/pemfc_model.py)
* Test Suite: [`physical_engine/factory_simulation/pemfc_test.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/pemfc_test.py)
