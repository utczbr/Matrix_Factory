# Station 5: PEMFC Electrochemistry & Testing (Reference)

This document presents the non-linear electrochemistry, Butler–Volmer reaction kinetics, Springer membrane hydration model, and polarization curve equations for **Station 5: Quality Testing & PEMFC Performance Verification**.

---

## Physical Process Description

Station 5 subjects assembled fuel cell stacks to end-of-line electrical and gas crossover diagnostics. It simulates IV polarization curves, cell voltage distributions, activation losses, ohmic resistance, and mass transport limitation current densities $j_{\text{lim}}$.

---

## Mathematical Formulation

### 1. Polarization Cell Voltage Equation

Cell voltage $V_{\text{cell}}$ at current density $j$ ($\text{A/cm}^2$) is governed by thermodynamic Nernst potential $E_{\text{Nernst}}$ minus three loss overpotentials:

$$V_{\text{cell}}(j) = E_{\text{Nernst}} - \eta_{\text{act}} - \eta_{\text{ohmic}} - \eta_{\text{trans}}$$

### 2. Activation Overpotential (Butler–Volmer Kinetics)

The cathode Oxygen Reduction Reaction (ORR) activation overpotential $\eta_{\text{act}}$ is expressed via Tafel kinetics:

$$\eta_{\text{act}} = \frac{R T}{\alpha_{\text{ORR}} F} \ln\left( \frac{j + j_{\text{loss}}}{j_0 \cdot \text{ECSA} \cdot L_{\text{Pt}}} \right)$$

where:
* $\alpha_{\text{ORR}}$ is the cathodic charge transfer coefficient ($\approx 0.50$).
* $j_0$ is reference exchange current density ($\text{A/cm}^2_{\text{Pt}}$).
* $\text{ECSA}$ is inherited from Station 2.

### 3. Ohmic Overpotential & Springer Membrane Hydration

Ohmic loss $\eta_{\text{ohmic}}$ includes electronic membrane resistance $R_{\text{mem}}$ and interfacial contact resistance $R_{\text{contact}}$ (inherited from Station 4):

$$\eta_{\text{ohmic}} = j \cdot \left( R_{\text{mem}}(\lambda) + R_{\text{contact}} \right)$$

Membrane ionic conductivity $\sigma_{\text{mem}}$ depends on water content $\lambda \in [1, 14]$ (Springer model):

$$\sigma_{\text{mem}}(\lambda, T) = (0.005139 \lambda - 0.00326) \exp\left( 1268 \left( \frac{1}{303} - \frac{1}{T} \right) \right)$$

$$R_{\text{mem}} = \frac{t_{\text{mem}}}{\sigma_{\text{mem}}(\lambda, T)}$$

### 4. Mass Transport Concentration Overpotential

Concentration loss $\eta_{\text{trans}}$ accounts for reactant gas starvation and liquid water flooding at high current densities:

$$\eta_{\text{trans}} = -\frac{R T}{n F} \ln\left( 1 - \frac{j}{j_{\text{lim}}} \right)$$

where mass transport limit current density $j_{\text{lim}}$ is derated by GDL compression:

$$j_{\text{lim}} = j_{\text{lim},0} \cdot \left( \frac{\varepsilon_{\text{gdl}}(P_{\text{clamp}})}{\varepsilon_0} \right)^{1.5}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Reference Exchange Current | $j_0$ | $2.5 \times 10^{-8}$ | $\text{A/cm}^2_{\text{Pt}}$ | Neyerlin et al. (2007) |
| Charge Transfer Coeff. | $\alpha_{\text{ORR}}$ | $0.50$ | — | Springer et al. (1991) |
| Membrane Thickness | $t_{\text{mem}}$ | $15.0$ | $\mu\text{m}$ | Nafion HP Datasheet |
| Baseline Limiting Current | $j_{\text{lim},0}$ | $2.40$ | $\text{A/cm}^2$ | Experimental Polarization |
| Membrane Water Content | $\lambda$ | $12.5$ | — | Relative Humidity = 80% |

---

## Code Reference

* Main Model: [`physical_engine/factory_simulation/pemfc_model.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/pemfc_model.py)
* Test Suite: [`physical_engine/factory_simulation/pemfc_test.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/pemfc_test.py)
