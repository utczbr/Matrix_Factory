# Station 1: MEA Resin Cure Kinetics (Reference)

This document details the mathematical formulations, kinetic equations, and calibration parameters for **Station 1: MEA Preparation & Resin Curing**.

---

## Physical Process Description

Station 1 models the thermal curing of thermosetting resin frames encapsulating the Membrane Electrode Assembly (MEA). The reaction rate is governed by an autocatalytic phenomenological model that accounts for thermal activation energy and vitrification phenomena.

---

## Mathematical Formulation

### 1. Kamal–Sourour Autocatalytic Curing Kinetics

The rate of cure conversion $\alpha \in [0, 1]$ over time is expressed as:

$$\frac{d\alpha}{dt} = \left( k_1 + k_2 \alpha^m \right) (1 - \alpha)^n$$

where $k_1$ and $k_2$ follow Arrhenius temperature dependencies:

$$k_1(T) = A_1 \exp\left( -\frac{E_1}{R T} \right)$$

$$k_2(T) = A_2 \exp\left( -\frac{E_2}{R T} \right)$$

### 2. Glass Transition & Vitrification Derating

As curing progresses, the glass transition temperature $T_g(\alpha)$ increases according to DiBenedetto's equation:

$$\frac{T_g - T_{g0}}{T_{g\infty} - T_{g0}} = \frac{\lambda \alpha}{1 - (1 - \lambda)\alpha}$$

If $T < T_g(\alpha)$, diffusion control reduces the reaction rate by factor $f_d(\alpha)$:

$$f_d(\alpha) = \frac{1}{1 + \exp\left( C_d (\alpha - \alpha_c) \right)}$$

$$\left.\frac{d\alpha}{dt}\right|_{\text{effective}} = \frac{d\alpha}{dt} \cdot f_d(\alpha)$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Frequency Factor 1 | $A_1$ | $2.4 \times 10^4$ | $\text{s}^{-1}$ | Fernandes et al. (2018) |
| Frequency Factor 2 | $A_2$ | $1.8 \times 10^7$ | $\text{s}^{-1}$ | Fernandes et al. (2018) |
| Activation Energy 1 | $E_1$ | $54.2$ | $\text{kJ/mol}$ | Fernandes et al. (2018) |
| Activation Energy 2 | $E_2$ | $46.8$ | $\text{kJ/mol}$ | Fernandes et al. (2018) |
| Reaction Order $m$ | $m$ | $0.42$ | — | Experimental Fit |
| Reaction Order $n$ | $n$ | $1.58$ | — | Experimental Fit |
| DiBenedetto Parameter | $\lambda$ | $0.45$ | — | Material Specs |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station1_mea_preparation.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station1_mea_preparation.py)
