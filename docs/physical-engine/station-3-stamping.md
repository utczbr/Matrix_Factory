# Station 3: Bipolar Plate Stamping

This document details the continuum mechanics models, Archard tool wear rate, and Normalized Cockcroft–Latham ductile damage criterion for **Station 3: Bipolar Plate Stamping**.

---

## Physical Process Description

Station 3 models high-speed metal forming of metallic bipolar plate flow channels (stainless steel 316L). The process calculates stamping press force, plastic strain work, progressive tool wear, and Normalized Cockcroft–Latham ($C_{\text{crit,NCL}}$) micro-crack risk.

---

## Mathematical Formulation

### 1. Archard Die Tool Wear Model

Progressive stamping die wear ratio $W_{\text{ratio}}$ per stroke is computed using Archard's wear law:

$$W_{\text{raw}} = W_0 + K_{\text{wear}} \cdot N_{\text{stroke}} \cdot \left( \frac{F_{\text{press}}}{F_{\text{nominal}}} \right)^{\gamma_{\text{archard}}}$$

where:
* **$W_0$** — Initial die wear ratio.
* **$N_{\text{stroke}}$** — Cumulative die stroke count.
* **$\gamma_{\text{archard}} = 1.35$** — Pressure exponent.
* **$K_{\text{wear,duplex}} = 1.47 \times 10^{-10}\text{ mm}^3/(\text{N}\cdot\text{m})$** — Duplex PVD coating wear coefficient (Bitay et al. 2021).
* **$K_{\text{wear,pvd}} = 3.50 \times 10^{-6}\text{ mm}^3/(\text{N}\cdot\text{m})$** — Standard PVD wear coefficient (Fernandes et al. 2017).

### 2. Normalized Cockcroft–Latham (NCL) Ductile Fracture Damage

Material plastic strain $\varepsilon_p$ and membrane stress $\sigma_1$ across 60 micro-channels ($A_{\text{total}} = 0.0012\text{ m}^2$) follow SS316L strain hardening:

$$\sigma_{\text{flow}} = K_{\text{strength}} \cdot \varepsilon_p^{n_{\text{hardening}}}$$

where $K_{\text{strength}} = 1280.0\text{ MPa}$ and $n_{\text{hardening}} = 0.43$ (Blandford 2007; Mahabunphachai & Koc 2008).

Plastic work done $W_{\text{plastic}}$ is integrated and normalized against critical threshold $C_{\text{crit,NCL}} = 0.35$ (Modanloo et al. 2018):

$$W_{\text{plastic}} = \frac{\sigma_1 / K_{\text{strength}}}{1 - n_{\text{hardening}}} \cdot \frac{\varepsilon_p^{1 - n_{\text{hardening}}}}{1 - n_{\text{hardening}}}$$

$$\text{damage}_{\text{NCL}} = \frac{W_{\text{plastic}}}{C_{\text{crit,NCL}}}$$

A defect is registered if $\text{damage}_{\text{NCL}} > 1.0$ or wear ratio $W_{\text{ratio}} \ge 0.75$.

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Critical NCL Damage Threshold | $C_{\text{crit,NCL}}$ | $0.35$ | — | Modanloo et al. (2018) |
| Archard Pressure Exponent | $\gamma_{\text{archard}}$ | $1.35$ | — | Archard (1953) |
| Duplex Wear Coeff. | $K_{\text{wear,duplex}}$ | $1.47 \times 10^{-10}$ | $\text{mm}^3/(\text{N}\cdot\text{m})$ | Bitay et al. (2021) |
| Standard PVD Wear Coeff. | $K_{\text{wear,pvd}}$ | $3.50 \times 10^{-6}$ | $\text{mm}^3/(\text{N}\cdot\text{m})$ | Fernandes et al. (2017) |
| Strength Coefficient 316L | $K_{\text{strength}}$ | $1280.0$ | $\text{MPa}$ | Blandford (2007) |
| Strain Hardening Exponent 316L | $n_{\text{hardening}}$ | $0.43$ | — | Mahabunphachai & Koc (2008) |
| Nominal Press Force | $F_{\text{nominal}}$ | $120.0$ | $\text{kN}$ | Stamping Press Specs |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station3_bipolar_plate_stamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station3_bipolar_plate_stamping.py)
* Calibration Script: [`physical_engine/scripts/calibrate_stamping_clamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/scripts/calibrate_stamping_clamping.py)
