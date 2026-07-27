# Station 1: MEA Resin Cure Kinetics (Reference)

This document details the mathematical formulations, kinetic equations, and calibration parameters for **Station 1: MEA Preparation & Hot-Press Lamination**.

---

## Physical Process Description

Station 1 models the thermal curing of thermosetting resin frames encapsulating the Membrane Electrode Assembly (MEA) during hot-press lamination. The degree of cure conversion $\alpha \in [0, 1]$ is computed using Kamal–Sourour autocatalytic reaction kinetics. Under-curing ($\alpha < 0.85$) introduces delamination risks, while over-curing ($\alpha > 0.98$) risks thermal degradation and membrane pinhole formation.

---

## Mathematical Formulation

### 1. Kamal–Sourour Autocatalytic Curing Kinetics

The rate of cure conversion $\alpha$ over time is expressed as:

$$\frac{\mathrm{d}\alpha}{\mathrm{d}t} = \left( k_1 + k_2 \alpha^m \right) (1 - \alpha)^n$$

where Arrhenius reaction rate constants $k_1$ and $k_2$ at hot-press temperature $T_{\mathrm{press}}$ ($\mathrm{K}$) are defined by:

$$k_1(T) = A_1 \exp\left( -\frac{E_1}{R T_{\mathrm{press}}} \right)$$

$$k_2(T) = A_2 \exp\left( -\frac{E_2}{R T_{\mathrm{press}}} \right)$$

### 2. Defect Risk Functions & Execution Pacing

Degree of cure $\alpha$ is integrated via 4th-order Runge–Kutta (RK4) over dwell time $t_{\mathrm{dwell}}$:

* **Delamination Risk ($\alpha < 0.85$):** 

$$R_{\mathrm{delam}} = \max\left(0, \frac{\alpha_{\mathrm{min}} - \alpha}{\alpha_{\mathrm{min}}}\right)$$

* **Pinhole Risk ($\alpha > 0.98$):** 

$$R_{\mathrm{pinhole}} = \max\left(0, \frac{\alpha - \alpha_{\mathrm{max}}}{1 - \alpha_{\mathrm{max}}}\right)$$

Processing variance ratio $V_{\mathrm{ratio}}$ scales execution variability:

$$V_{\mathrm{ratio}} = 1.0 + 0.30 R_{\mathrm{delam}} + 0.25 R_{\mathrm{pinhole}}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Frequency Factor 1 | $A_1$ | $1.2 \times 10^4$ | $\mathrm{s}^{-1}$ | Fernandes et al. (2018) |
| Frequency Factor 2 | $A_2$ | $5.5 \times 10^6$ | $\mathrm{s}^{-1}$ | Fernandes et al. (2018) |
| Activation Energy 1 | $E_1$ | $58.2$ | $\mathrm{kJ/mol}$ | Fernandes et al. (2018) |
| Activation Energy 2 | $E_2$ | $68.5$ | $\mathrm{kJ/mol}$ | Fernandes et al. (2018) |
| Reaction Order $m$ | $m$ | $0.48$ | — | Experimental Fit |
| Reaction Order $n$ | $n$ | $1.52$ | — | Experimental Fit |
| Nominal Press Temp. | $T_{\mathrm{press}}$ | $433.15$ ($160^\circ\mathrm{C}$) | $\mathrm{K}$ | Hot-Press Specification |
| Nominal Dwell Time | $t_{\mathrm{dwell}}$ | $180.0$ | $\mathrm{s}$ | Process Recipe |
| Min Bonding Cure | $\alpha_{\mathrm{min}}$ | $0.85$ | — | Structural Adhesion Limit |
| Max Safe Cure | $\alpha_{\mathrm{max}}$ | $0.98$ | — | Degradation Limit |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station1_mea_preparation.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station1_mea_preparation.py)
