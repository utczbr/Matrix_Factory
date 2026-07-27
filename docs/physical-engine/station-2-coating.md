# Station 2: Catalyst Coating & ECSA Models (Reference)

This document details the hydrodynamic coating non-uniformity equations and Electro-Chemical Surface Area ($\mathrm{ECSA}$) yield model for **Station 2: Catalyst Layer Deposition**.

---

## Physical Process Description

Station 2 models slot-die coating of Platinum/Carbon (Pt/C) catalyst ink onto polymer electrolyte membranes. Process deviations in coating line speed $v_{\mathrm{coat}}$ and ink slurry dynamic viscosity $\mu_{\mathrm{slurry}}$ alter ink film uniformity, establishing effective catalyst utilization $\mathrm{ECSA}_{\mathrm{ratio}}$.

---

## Mathematical Formulation

### 1. Process Deviations & Hydrodynamic Variance

Process parameter deviations relative to nominal setpoints $v_0 = 0.15\mathrm{ m/s}$ and $\mu_0 = 0.050\mathrm{ Pa}\cdot\mathrm{s}$ are evaluated as:

$$v_{\mathrm{dev}} = \frac{|v_{\mathrm{coat}} - v_0|}{v_0}$$

$$\mu_{\mathrm{dev}} = \frac{|\mu_{\mathrm{slurry}} - \mu_0|}{\mu_0}$$

Hydrodynamic catalyst loading variance index $\text{loading\_variance}$ combines quadratic and cross-coupling deviations:

$$\text{loading\_variance} = 0.35 v_{\mathrm{dev}}^2 + 0.25 \mu_{\mathrm{dev}}^2 + 0.15 v_{\mathrm{dev}} \mu_{\mathrm{dev}}$$

### 2. Effective ECSA Yield & Quality Criteria

Effective catalyst surface area yield $\mathrm{ECSA}_{\mathrm{ratio}} \in [0.10, 1.00]$ is computed as:

$$\mathrm{ECSA}_{\mathrm{ratio}} = \max\left(0.10, \min\left(1.00, 1.0 - 0.45 \cdot \text{loading\_variance} - 0.20 v_{\mathrm{dev}}\right)\right)$$

A component is flagged defective if $\mathrm{ECSA}_{\mathrm{ratio}} < 0.70$ or $\text{loading\_variance} > 0.30$.

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Nominal Line Speed | $v_0$ | $0.15$ ($15\mathrm{ cm/s}$) | $\mathrm{m/s}$ | Slot-Die Machine Specs |
| Nominal Ink Viscosity | $\mu_0$ | $0.050$ ($50\mathrm{ cP}$) | $\mathrm{Pa}\cdot\mathrm{s}$ | Rheometer Measurements |
| Surface Tension | $\sigma_{\mathrm{ink}}$ | $0.035$ | $\mathrm{N/m}$ | Pendant Drop Method |
| Min Acceptable ECSA | $\mathrm{ECSA}_{\mathrm{min}}$ | $0.70$ | — | Quality Threshold |
| Nominal Cycle Time | $t_{\mathrm{base}}$ | $12.0$ | $\mathrm{s}$ | Factory Schedule |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station2_catalyst_deposition.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station2_catalyst_deposition.py)
