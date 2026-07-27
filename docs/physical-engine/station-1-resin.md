# Station 1: MEA Preparation & Hot-Press Lamination

This document details the mathematical formulations, kinetic equations, and calibration parameters for **Station 1: MEA Preparation & Hot-Press Lamination**.

---

## Physical Process Description

Station 1 models the thermal curing of thermosetting resin frames encapsulating the Membrane Electrode Assembly (MEA) during hot-press lamination. The degree of cure conversion $\alpha \in [0, 1]$ is computed using Kamal–Sourour autocatalytic reaction kinetics. Under-curing ($\alpha < 0.85$) introduces delamination risks, while over-curing ($\alpha > 0.98$) risks thermal degradation and membrane pinhole formation. A component is flagged defective if $\alpha < 0.85$ or $\alpha > 0.98$.

---

## Mathematical Formulation

### 1. Kamal–Sourour Autocatalytic Curing Kinetics

The rate of cure conversion $\alpha$ over time is expressed as:

$$\frac{d\alpha}{dt} = (k_1 + k_2 \alpha^m) (1 - \alpha)^n$$

where Arrhenius reaction rate constants $k_1$ and $k_2$ at hot-press temperature $T_{\text{press}}$ ($\text{K}$) are defined by:

$$k_1(T) = A_1 \exp\left(-\frac{E_1}{R T_{\text{press}}}\right)$$

$$k_2(T) = A_2 \exp\left(-\frac{E_2}{R T_{\text{press}}}\right)$$

Degree of cure $\alpha$ is integrated via 4th-order Runge–Kutta (RK4), fixed at 100 substeps over dwell time $t_{\text{dwell}}$, with $\alpha$ clamped to $[0, 0.9999]$ after every substep to keep $(1-\alpha)^n$ from becoming singular as $\alpha \to 1$.

### 2. Defect Risk Functions & Execution Pacing

* **Delamination Risk ($\alpha < 0.85$):**

$$R_{\text{delam}} = \max\left(0, \frac{\alpha_{\text{min}} - \alpha}{\alpha_{\text{min}}}\right)$$

* **Pinhole Risk ($\alpha > 0.98$):**

$$R_{\text{pinhole}} = \max\left(0, \frac{\alpha - \alpha_{\text{max}}}{1 - \alpha_{\text{max}}}\right)$$

Processing variance ratio $V_{\text{ratio}}$ scales execution variability:

$$V_{\text{ratio}} = 1.0 + 0.30\, R_{\text{delam}} + 0.25\, R_{\text{pinhole}}$$

Station cycle time $t_{\text{proc}}$ scales with deviations from nominal press temperature and dwell time:

$$t_{\text{proc}} = k_{\text{time}} \cdot t_{\text{base}} \left(1 + 0.15\, T_{\text{dev}} + 0.10\, t_{\text{dwell,dev}}\right)$$

where $t_{\text{base}} = 5.0\ \text{s}$, $T_{\text{dev}} = |T_{\text{press}} - T_{\text{press,nominal}}| / T_{\text{press,nominal}}$, and $t_{\text{dwell,dev}}$ is defined analogously for dwell time. $k_{\text{time}}$ is a global time-acceleration factor (1.0 in accelerated simulation mode, 10.0 in industrial-pace mode).

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Frequency Factor 1 | $A_1$ | $1.2 \times 10^4$ | $\text{s}^{-1}$ | Fernandes et al. (2018) |
| Frequency Factor 2 | $A_2$ | $5.5 \times 10^6$ | $\text{s}^{-1}$ | Fernandes et al. (2018) |
| Activation Energy 1 | $E_1$ | $58.2$ | $\text{kJ/mol}$ | Fernandes et al. (2018) |
| Activation Energy 2 | $E_2$ | $68.5$ | $\text{kJ/mol}$ | Fernandes et al. (2018) |
| Reaction Order $m$ | $m$ | $0.48$ | — | Experimental Fit |
| Reaction Order $n$ | $n$ | $1.52$ | — | Experimental Fit |
| Nominal Press Temp. | $T_{\text{press}}$ | $433.15$ ($160^\circ\text{C}$) | $\text{K}$ | Hot-Press Specification |
| Nominal Dwell Time | $t_{\text{dwell}}$ | $180.0$ | $\text{s}$ | Process Recipe |
| Min Bonding Cure | $\alpha_{\text{min}}$ | $0.85$ | — | Structural Adhesion Limit |
| Max Safe Cure | $\alpha_{\text{max}}$ | $0.98$ | — | Degradation Limit |
| Nominal Station Cycle Time | $t_{\text{base}}$ | $5.0$ | $\text{s}$ | `factory.jcm` process recipe |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station1_mea_preparation.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station1_mea_preparation.py)
