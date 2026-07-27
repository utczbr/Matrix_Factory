# Station 2: Catalyst Coating & ECSA Models (Reference)

This document details the hydrodynamic coating equations, solvent drying kinetics, and Electro-Chemical Surface Area (ECSA) predictions for **Station 2: Catalyst Layer Deposition**.

---

## Physical Process Description

Station 2 models slot-die coating of Platinum/Carbon (Pt/C) catalyst ink onto polymer electrolyte membranes. The process determines catalyst layer thickness uniformity, platinum loading $L_{\mathrm{Pt}}$ ($\mathrm{mg/cm}^2$), and initial active surface area $\mathrm{ECSA}_0$ ($\mathrm{m}^2/\mathrm{g}_{\mathrm{Pt}}$).

---

## Mathematical Formulation

### 1. Slot-Die Coating Hydrodynamics & Capillary Number

The stable coating window is constrained by the Capillary number $Ca$:

$$Ca = \frac{\mu U_{\mathrm{web}}}{\sigma_{\mathrm{ink}}}$$

where:
* $\mu$ is dynamic ink viscosity ($\mathrm{Pa}\cdot\mathrm{s}$).
* $U_{\mathrm{web}}$ is web line speed ($\mathrm{m/s}$).
* $\sigma_{\mathrm{ink}}$ is liquid-vapor surface tension ($\mathrm{N/m}$).

Wet film thickness $h_{\mathrm{wet}}$ is governed by mass conservation:

$$h_{\mathrm{wet}} = \frac{Q_{\mathrm{ink}}}{W_{\mathrm{die}} \cdot U_{\mathrm{web}}}$$

### 2. Solvent Evaporation & ECSA Formation

Dry thickness $h_{\mathrm{dry}}$ depends on solid volume fraction $\phi_s$:

$$h_{\mathrm{dry}} = h_{\mathrm{wet}} \cdot \phi_s$$

Effective Electro-Chemical Surface Area ($\mathrm{ECSA}$) is modeled as a function of drying rate $\dot{E}_{\mathrm{dry}}$ and agglomerate porosity $\varepsilon_{\mathrm{agg}}$:

$$\mathrm{ECSA} = \mathrm{ECSA}_{\mathrm{max}} \cdot \left[ 1 - \gamma_{\mathrm{dry}} \cdot \left( \frac{\dot{E}_{\mathrm{dry}}}{\dot{E}_{\mathrm{crit}}} - 1 \right)^2 \right] \cdot \left( \frac{\varepsilon_{\mathrm{agg}}}{\varepsilon_{\mathrm{target}}} \right)^{0.5}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Max Pt ECSA | $\mathrm{ECSA}_{\mathrm{max}}$ | $68.5$ | $\mathrm{m}^2/\mathrm{g}_{\mathrm{Pt}}$ | Neyerlin et al. (2007) |
| Target Agglomerate Porosity | $\varepsilon_{\mathrm{target}}$ | $0.48$ | — | Kleemann et al. (2021) |
| Ink Viscosity | $\mu$ | $0.045$ | $\mathrm{Pa}\cdot\mathrm{s}$ | Rheometer Measurements |
| Surface Tension | $\sigma_{\mathrm{ink}}$ | $0.028$ | $\mathrm{N/m}$ | Pendant Drop Method |
| Critical Drying Rate | $\dot{E}_{\mathrm{crit}}$ | $1.2 \times 10^{-3}$ | $\mathrm{kg/m}^2\mathrm{s}$ | Drying Oven Specs |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station2_catalyst_deposition.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station2_catalyst_deposition.py)
