# Station 3: Bipolar Plate Stamping (Reference)

This document details the continuum mechanics models, Archard tool wear rate, and Normalized Cockcroft–Latham ductile damage criterion for **Station 3: Bipolar Plate Stamping**.

---

## Physical Process Description

Station 3 models high-speed metal forming of metallic bipolar plate flow channels (stainless steel 316L / titanium foil). The process calculates stamping press force, channel springback, die wear, and micro-crack formation risk.

---

## Mathematical Formulation

### 1. Cockcroft–Latham Ductile Fracture Damage Criterion

Material fracture accumulation $C_{\mathrm{crit,NCL}}$ during channel geometry forming is evaluated via the Normalized Cockcroft–Latham integral:

$$C_{\mathrm{crit,NCL}} = \int_0^{\bar{\varepsilon}_f} \frac{\sigma^*}{\bar{\sigma}} \, \mathrm{d}\bar{\varepsilon}$$

where:
* $\sigma^*$ is the maximum tensile principal stress ($\mathrm{MPa}$).
* $\bar{\sigma}$ is the von Mises equivalent stress ($\mathrm{MPa}$).
* $\bar{\varepsilon}$ is the equivalent plastic strain.

If $C_{\mathrm{crit,NCL}} > C_{\mathrm{threshold}} \approx 0.42$, micro-cracking initiates along flow channel ribs, inducing gas leakage risks.

### 2. Archard Die Tool Wear Model

Progressive stamping die volume wear $V_{\mathrm{wear}}$ per stroke is calculated as:

$$V_{\mathrm{wear}} = K_{\mathrm{archard}} \frac{F_{\mathrm{normal}} \cdot s_{\mathrm{sliding}}}{H_{\mathrm{die}}}$$

where:
* $K_{\mathrm{archard}}$ is the dimensionless wear coefficient ($1.4 \times 10^{-4}$).
* $F_{\mathrm{normal}}$ is the normal contact load ($\mathrm{kN}$).
* $s_{\mathrm{sliding}}$ is interface sliding distance ($\mathrm{mm}$).
* $H_{\mathrm{die}}$ is die material Vickers hardness ($\mathrm{HV}$).

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Critical NCL Damage | $C_{\mathrm{threshold}}$ | $0.42$ | — | Kleemann et al. (2021) |
| Archard Wear Coeff. | $K_{\mathrm{archard}}$ | $1.4 \times 10^{-4}$ | — | Archard (1953) |
| Die Hardness | $H_{\mathrm{die}}$ | $680$ | $\mathrm{HV}$ | Tool Steel Specs |
| Sheet Thickness | $t_0$ | $0.10$ | $\mathrm{mm}$ | SS316L Datasheet |
| Channel Pitch | $P_{\mathrm{channel}}$ | $1.25$ | $\mathrm{mm}$ | Flow Field Geometry |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station3_bipolar_plate_stamping.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station3_bipolar_plate_stamping.py)
* Calibration Script: [`physical_engine/scripts/calibrate_stamping_clamping.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/scripts/calibrate_stamping_clamping.py)
