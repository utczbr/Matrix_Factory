# Station 5: PEMFC Electrochemistry & Test Bench

This document presents the non-linear electrochemistry, Butler–Volmer reaction kinetics, Springer membrane hydration model, thermal coupling, and polarization curve equations for **Station 5: Quality Testing & PEMFC Performance Verification**.

---

## Physical Process Description

Station 5 subjects assembled fuel cell stacks to end-of-line electrical and gas crossover diagnostics. It simulates IV polarization curves, cell voltage distributions, activation losses, ohmic resistance, mass transport limitation current densities $j_{\text{lim}}$, and — coupled to a two-lump thermal model — thermal runaway risk.

---

## Mathematical Formulation

### 1. Nernst Open-Circuit Potential

$$E_{\text{Nernst}} = 1.229 - 0.85\times10^{-3}\,(T - 298.15) + \frac{RT}{2F}\ln\!\left(a_{H_2}\cdot a_{O_2}^{0.5}\right)$$

valid for reactant activities $a_{H_2}, a_{O_2} \in [0.5, 10.0]$ (clamped upstream from real-gas fugacity via the CoolProp/LUT layer described in the [Overview](overview.md)).

### 2. Polarization Cell Voltage Equation

Cell voltage $V_{\text{cell}}$ at current density $j$ ($\text{A/cm}^2$) follows the **subtractive** fuel cell convention:

$$V_{\text{cell}}(j) = E_{\text{Nernst}} - \eta_{\text{act}} - \eta_{\text{ohm}} - \eta_{\text{conc}}$$

$$V_{\text{stack}}(j) = N_{\text{cells}} \cdot V_{\text{cell}}(j)$$

### 3. Activation Overpotential (Butler–Volmer 4-Electron ORR Kinetics)

Cathodic Oxygen Reduction Reaction (ORR) activation overpotential $\eta_{\text{act}}$ accounts for the **$z = 4$** electron transfer pathway:

$$\eta_{\text{act}} = \frac{R T}{\alpha_{\text{orr}} z F} \ln\left( \frac{j}{j_0} \right)$$

where:

* **$\alpha_{\text{orr}} = 0.50$** — Charge transfer coefficient.
* **$z = 4$** — ORR electron transfer number.
* **$j_0$** — Arrhenius temperature & ECSA scaled exchange current density ($j_{0,\text{ref}} = 2.5 \times 10^{-8}\text{ A/cm}_{\text{Pt}}^2$, $E_{\text{act}} = 68.5\text{ kJ/mol}$; Gasteiger et al. 2005; Neyerlin et al. 2006):

$$j_0 = j_{0,\text{ref}} \cdot \text{ECSA}_{\text{ratio}} \cdot \exp\left( -\frac{E_{\text{act}}}{R T} \left( 1 - \frac{T}{T_{\text{ref}}} \right) \right)$$

### 4. Ohmic Overpotential & Springer Membrane Hydration

Ohmic overpotential $\eta_{\text{ohm}}$ incorporates baseline internal resistance $R_{\text{internal}}$, bulk GDL resistance $R_{\text{gdl}}$ (from Station 4), and membrane ionic resistance $R_{\text{mem}}$:

$$\eta_{\text{ohm}} = j \cdot \left( R_{\text{internal}} + R_{\text{gdl}}(t_{\text{comp}}, \varepsilon_{\text{gdl}}) + R_{\text{mem}}(\lambda, T) \right)$$

Membrane thickness is $t_{\text{mem}} = 50.0\ \mu\text{m}$ ($0.005\text{ cm}$). Conductivity $\sigma_{\text{mem}}$ ($\text{S/cm}$) follows Springer's model for water content $\lambda \in [1, 14]$:

$$\sigma_{\text{mem}}(\lambda, T) = (0.005139 \lambda - 0.00326) \exp\left( 1268 \left( \frac{1}{303.15} - \frac{1}{T} \right) \right)$$

$$R_{\text{mem}} = \frac{t_{\text{mem}}}{\sigma_{\text{mem}}(\lambda, T)}$$

Equilibrium water content $\lambda$ as a function of water activity $a_w$ follows the Springer sorption isotherm:

$$\lambda(a_w) = \begin{cases} 0.043 + 17.81\,a_w - 39.85\,a_w^2 + 36.0\,a_w^3, & a_w \le 1.0 \\ 14.0 + 1.4\,(a_w - 1.0), & 1.0 < a_w \le 3.0 \end{cases}$$

clamped to $\lambda \in [1.0, 14.0]$.

### 5. Mass Transport Concentration Overpotential

$$\eta_{\text{conc}} = -B \ln\left(1 - \frac{j}{j_{\text{lim}}}\right), \qquad \frac{j}{j_{\text{lim}}} \le 0.99$$

For $j/j_{\text{lim}} > 0.99$, the log singularity is bypassed with a linear continuation matching value and slope at the boundary ($C^1$ continuity):

$$\eta_{\text{conc}} = -B\ln(0.01) + \frac{B}{0.01\,j_{\text{lim}}}\left(\frac{j}{j_{\text{lim}}} - 0.99\right), \qquad \frac{j}{j_{\text{lim}}} > 0.99$$

with $B = 0.05$, $j_{\text{lim}} = 2.5\text{ A/cm}^2$ nominal.

### 6. Manufacturing-to-Performance Coupling

`sim_bridge_server.py::RunBatchTest` combines upstream station outputs into the effective internal resistance and reactant conditions actually fed to the polarization solver:

$$R_{\text{internal,eff}} = R_{\text{internal},0} + \Delta R_{\text{penalty}} + R_{\text{contact}}\!\left(P_{\text{clamp}},\, \varepsilon_{\text{gdl}}\right) + R_{\text{gdl}}\!\left(t_{\text{comp}},\, \varepsilon_{\text{gdl}}\right)$$

$$a_{H_2}^{\text{eff}} = a_{H_2}\,(1 - \text{derate}), \qquad a_{O_2}^{\text{eff}} = a_{O_2}\,(1 - \text{derate})$$

$$j_{\text{lim}}^{\text{eff}} = \max\!\left(0.2,\ 2.5\,(1 - j_{\text{lim\_derate}})\right)$$

where $R_{\text{internal},0}$ is a per-run baseline resistance (default $0.06\ \Omega\cdot\text{cm}^2$), $\Delta R_{\text{penalty}}$ is a defect-accumulation penalty tracked by the agent layer, $R_{\text{contact}}(\cdot)$ is the Station 4 U-shaped contact-resistance model, $R_{\text{gdl}}(\cdot) = \frac{t_{\text{comp}} \times 10^{-4}}{\sigma_{\text{bulk}}(1-\varepsilon_{\text{gdl}})^m}$ is the GDL bulk electrical resistance (see [Station 4](station-4-assembly.md)), and $\text{derate}$/$j_{\text{lim\_derate}}$ are upstream-quality-derived fractions clamped to $[0, 0.95]$ and $[0, 0.90]$ respectively.

### 7. Thermal Coupling & Test-Bench QC Thresholds

Station 5 couples the electrochemical solve to a two-lump (core/skin) thermal model (`stack_thermal_model.py`), validated against the **Yonkist number** — a Buckingham-Pi-derived extension of the Biot-number lumped-capacitance criterion for bodies with internal heat generation ($Yo = \frac{q_{\text{gen}}L^2}{k\,\Delta T}$; valid when $Yo < Bi$).

Total irreversible voltage overpotential and entropic heat generation per unit area $Q_{\text{gen}}$ ($\text{W/cm}^2$) is:

$$Q_{\text{gen}} = j \cdot N_{\text{cells}} \cdot \left( \eta_{\text{act}} + \eta_{\text{ohm}} + \eta_{\text{conc}} + E_{\text{entropic}} \right)$$

where $E_{\text{entropic}} = \frac{-T \Delta S}{zF} \approx 0.23\text{ V}$ represents reversible entropic heat generation ($\Delta S = -163.2\text{ J/(mol} \cdot \text{K)}$ for liquid water formation), ensuring accurate thermal runaway prediction at high current density ($j \to j_{\text{lim}}$).

The end-of-line test bench flags a stack via a bitmask if any of the following hold during a sweep:

* **Ohmic degradation:** per-cell ohmic overpotential $\eta_{\text{ohm}} > 0.35\text{ V}$
* **Thermal shutdown:** core temperature $T > 358.15\text{ K}$ ($\approx 85^\circ\text{C}$)
* **Low activation kinetics:** catalyst surface area utilization $\text{ECSA}_{\text{ratio}} < 0.30$
* **Reactant gas starvation:** hydrogen or oxygen activity floor breach $a_{H_2} < 0.70$ or $a_{O_2} < 0.70$
* **Mass-transport starvation:** flagged upstream via monotonicity check on the voltage sweep
* **Solver non-convergence:** Newton–Raphson current-density solve fails to converge within 50 iterations to $10^{-4}\text{ V}$ tolerance

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| ORR Exchange Current | $j_{0,\text{ref}}$ | $2.5 \times 10^{-8}$ | $\text{A/cm}_{\text{Pt}}^2$ | Gasteiger et al. (2005) |
| ORR Activation Energy | $E_{\text{act}}$ | $68.5$ | $\text{kJ/mol}$ | Neyerlin et al. (2006) |
| Electron Transfer Number | $z$ | $4$ | — | 4-Electron ORR Pathway |
| Charge Transfer Coeff. | $\alpha_{\text{orr}}$ | $0.50$ | — | Kinetic Parameter |
| Membrane Thickness | $t_{\text{mem}}$ | $50.0$ ($0.005\text{ cm}$) | $\mu\text{m}$ | Nafion Membrane Specs |
| Limiting Current | $j_{\text{lim}}$ | $2.50$ | $\text{A/cm}^2$ | Polarization Boundary |
| Concentration Coeff. | $B$ | $0.05$ | — | Fitted Empirical Constant |
| Baseline Internal Resistance | $R_{\text{internal},0}$ | $0.06$ | $\Omega\cdot\text{cm}^2$ | Per-run baseline |
| Stack Characteristic Length | $L$ | $0.05$ ($5.0\text{ cm}$) | $\text{m}$ | Stack thermal geometry |
| Effective Thermal Conductivity | $k_{\text{eff}}$ | $1.25$ | $\text{W/(m} \cdot \text{K)}$ | Stack composite thermal property |
| Core-Skin Temp. Threshold | $\Delta T$ | $15.0$ | $\text{K}$ | Yonkist stability criterion |
| Reversible Entropic Potential | $E_{\text{entropic}}$ | $0.23$ | $\text{V}$ | Thermodynamic entropic term ($-T\Delta S/zF$) |
| Ohmic Degradation Threshold | — | $0.35$ | $\text{V}$ | QC threshold |
| Thermal Shutdown Threshold | — | $358.15$ ($85^\circ\text{C}$) | $\text{K}$ | QC threshold |
| Low-Activation ECSA Floor | — | $0.30$ | — | QC threshold |
| Reactant Activity Floor | — | $0.70$ | — | QC threshold (Gas starvation) |

---

## Code Reference

* Main Model: [`physical_engine/factory_simulation/pemfc_model.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/pemfc_model.py)
* Membrane Hydration: [`physical_engine/factory_simulation/membrane_hydration.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/membrane_hydration.py)
* Thermal Model: [`physical_engine/factory_simulation/stack_thermal_model.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/stack_thermal_model.py)
* Test Suite: [`physical_engine/factory_simulation/pemfc_test.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/pemfc_test.py)
