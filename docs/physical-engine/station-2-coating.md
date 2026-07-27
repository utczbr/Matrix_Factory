# Station 2: Catalyst Layer Deposition

This document details the coating non-uniformity equations and Electro-Chemical Surface Area ($\text{ECSA}$) yield model for **Station 2: Catalyst Layer Deposition**.

---

## Physical Process Description

Station 2 models slot-die coating of Platinum/Carbon (Pt/C) catalyst ink onto polymer electrolyte membranes. Process deviations in coating line speed $v_{\text{coat}}$ and ink slurry dynamic viscosity $\mu_{\text{slurry}}$ alter ink film uniformity, establishing effective catalyst utilization $\text{ECSA}_{\text{ratio}}$.

---

## Mathematical Formulation

### 1. Process Deviations & Non-Uniformity

Process parameter deviations relative to nominal setpoints $v_0 = 0.15\text{ m/s}$ and $\mu_0 = 0.050\text{ Pa}\cdot\text{s}$ are evaluated as:

$$v_{\text{dev}} = \frac{|v_{\text{coat}} - v_0|}{v_0}$$

$$\mu_{\text{dev}} = \frac{|\mu_{\text{slurry}} - \mu_0|}{\mu_0}$$

Catalyst loading variance index $\text{loading\_variance}$ combines quadratic and cross-coupling deviations:

$$\text{loading\_variance} = 0.35 v_{\text{dev}}^2 + 0.25 \mu_{\text{dev}}^2 + 0.15 v_{\text{dev}} \mu_{\text{dev}}$$

### 2. Effective ECSA Yield & Quality Criteria

Effective catalyst surface area yield $\text{ECSA}_{\text{ratio}} \in [0.10, 1.00]$ is computed as:

$$\text{ECSA}_{\text{ratio}} = \max\left(0.10, \min\left(1.00, 1.0 - 0.45 \cdot \text{loading\_variance} - 0.20 v_{\text{dev}}\right)\right)$$

A component is flagged defective if $\text{ECSA}_{\text{ratio}} < 0.70$ or $\text{loading\_variance} > 0.30$.

### 3. Execution Pacing

$$t_{\text{proc}} = k_{\text{time}} \cdot t_{\text{base}} \left(1 + 0.12\, v_{\text{dev}} + 0.10\, \mu_{\text{dev}}\right)$$

$$\text{var\_ratio} = 1.0 + 0.40 \cdot \text{loading\_variance}$$

with $t_{\text{base}} = 12.0\ \text{s}$.

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Nominal Line Speed | $v_0$ | $0.15$ ($15\text{ cm/s}$) | $\text{m/s}$ | Slot-Die Machine Specs |
| Nominal Ink Viscosity | $\mu_0$ | $0.050$ ($50\text{ cP}$) | $\text{Pa}\cdot\text{s}$ | Rheometer Measurements |
| Surface Tension *(declared constant)* | $\sigma_{\text{ink}}$ | $0.035$ | $\text{N/m}$ | Ink formulation constant |
| Min Acceptable ECSA | $\text{ECSA}_{\text{min}}$ | $0.70$ | — | Quality Threshold |
| Nominal Cycle Time | $t_{\text{base}}$ | $12.0$ | $\text{s}$ | Factory Schedule |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station2_catalyst_deposition.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station2_catalyst_deposition.py)
