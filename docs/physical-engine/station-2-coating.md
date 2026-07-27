# Station 2: Catalyst Coating & ECSA Models (Reference)

This document details the hydrodynamic coating equations, solvent drying kinetics, and Electro-Chemical Surface Area (ECSA) predictions for **Station 2: Catalyst Layer Deposition**.

---

## Physical Process Description

Station 2 models slot-die coating of Platinum/Carbon (Pt/C) catalyst ink onto polymer electrolyte membranes. The process determines catalyst layer thickness uniformity, platinum loading $L_{\text{Pt}}$ ($\text{mg/cm}^2$), and initial active surface area $\text{ECSA}_0$ ($\text{m}^2/\text{g}_{\text{Pt}}$).

---

## Mathematical Formulation

### 1. Slot-Die Coating Hydrodynamics & Capillary Number

The stable coating window is constrained by the Capillary number $Ca$:

$$Ca = \frac{\mu U_{\text{web}}}{\sigma_{\text{ink}}}$$

where:
* $\mu$ is dynamic ink viscosity ($\text{Pa}\cdot\text{s}$).
* $U_{\text{web}}$ is web line speed ($\text{m/s}$).
* $\sigma_{\text{ink}}$ is liquid-vapor surface tension ($\text{N/m}$).

Wet film thickness $h_{\text{wet}}$ is governed by mass conservation:

$$h_{\text{wet}} = \frac{Q_{\text{ink}}}{W_{\text{die}} \cdot U_{\text{web}}}$$

### 2. Solvent Evaporation & ECSA Formation

Dry thickness $h_{\text{dry}}$ depends on solid volume fraction $\phi_s$:

$$h_{\text{dry}} = h_{\text{wet}} \cdot \phi_s$$

Effective Electro-Chemical Surface Area ($\text{ECSA}$) is modeled as a function of drying rate $\dot{E}_{\text{dry}}$ and agglomerate porosity $\varepsilon_{\text{agg}}$:

$$\text{ECSA} = \text{ECSA}_{\text{max}} \cdot \left[ 1 - \gamma_{\text{dry}} \cdot \left( \frac{\dot{E}_{\text{dry}}}{\dot{E}_{\text{crit}}} - 1 \right)^2 \right] \cdot \left( \frac{\varepsilon_{\text{agg}}}{\varepsilon_{\text{target}}} \right)^{0.5}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Max Pt ECSA | $\text{ECSA}_{\text{max}}$ | $68.5$ | $\text{m}^2/\text{g}_{\text{Pt}}$ | Neyerlin et al. (2007) |
| Target Agglomerate Porosity | $\varepsilon_{\text{target}}$ | $0.48$ | — | Kleemann et al. (2021) |
| Ink Viscosity | $\mu$ | $0.045$ | $\text{Pa}\cdot\text{s}$ | Rheometer Measurements |
| Surface Tension | $\sigma_{\text{ink}}$ | $0.028$ | $\text{N/m}$ | Pendant Drop Method |
| Critical Drying Rate | $\dot{E}_{\text{crit}}$ | $1.2 \times 10^{-3}$ | $\text{kg/m}^2\text{s}$ | Drying Oven Specs |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station2_catalyst_deposition.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station2_catalyst_deposition.py)
