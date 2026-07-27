# Station 3: Bipolar Plate Stamping (Reference)

This document details the continuum mechanics models, Archard tool wear rate, and Normalized Cockcroft–Latham ductile damage criterion for **Station 3: Bipolar Plate Stamping**.

---

## Physical Process Description

Station 3 models high-speed metal forming of metallic bipolar plate flow channels (stainless steel 316L / titanium foil). The process calculates stamping press force, channel springback, die wear, and micro-crack formation risk.

---

## Mathematical Formulation

### 1. Cockcroft–Latham Ductile Fracture Damage Criterion

Material fracture accumulation $C_{\text{crit,NCL}}$ during channel geometry forming is evaluated via the Normalized Cockcroft–Latham integral:

$$C_{\text{crit,NCL}} = \int_0^{\bar{\varepsilon}_f} \frac{\sigma^*}{\bar{\sigma}} d\bar{\varepsilon}$$

where:
* $\sigma^*$ is the maximum tensile principal stress ($\text{MPa}$).
* $\bar{\sigma}$ is the von Mises equivalent stress ($\text{MPa}$).
* $\bar{\varepsilon}$ is the equivalent plastic strain.

If $C_{\text{crit,NCL}} > C_{\text{threshold}} \approx 0.42$, micro-cracking initiates along flow channel ribs, inducing gas leakage risks.

### 2. Archard Die Tool Wear Model

Progressive stamping die volume wear $V_{\text{wear}}$ per stroke is calculated as:

$$V_{\text{wear}} = K_{\text{archard}} \frac{F_{\text{normal}} \cdot s_{\text{sliding}}}{H_{\text{die}}}$$

where:
* $K_{\text{archard}}$ is the dimensionless wear coefficient ($1.4 \times 10^{-4}$).
* $F_{\text{normal}}$ is the normal contact load ($\text{kN}$).
* $s_{\text{sliding}}$ is interface sliding distance ($\text{mm}$).
* $H_{\text{die}}$ is die material Vickers hardness ($\text{HV}$).

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Critical NCL Damage | $C_{\text{threshold}}$ | $0.42$ | — | Kleemann et al. (2021) |
| Archard Wear Coeff. | $K_{\text{archard}}$ | $1.4 \times 10^{-4}$ | — | Archard (1953) |
| Die Hardness | $H_{\text{die}}$ | $680$ | $\text{HV}$ | Tool Steel Specs |
| Sheet Thickness | $t_0$ | $0.10$ | $\text{mm}$ | SS316L Datasheet |
| Channel Pitch | $P_{\text{channel}}$ | $1.25$ | $\text{mm}$ | Flow Field Geometry |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station3_bipolar_plate_stamping.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station3_bipolar_plate_stamping.py)
* Calibration Script: [`physical_engine/scripts/calibrate_stamping_clamping.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/scripts/calibrate_stamping_clamping.py)
