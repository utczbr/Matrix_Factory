# Station 3: Bipolar Plate Stamping (Reference)

This document details the continuum mechanics models, Archard tool wear rate, and Normalized Cockcroft–Latham ductile damage criterion for **Station 3: Bipolar Plate Stamping**.

---

## Physical Process Description

Station 3 models high-speed metal forming of metallic bipolar plate flow channels (stainless steel 316L). The process calculates stamping press force, plastic strain work, progressive tool wear, and Normalized Cockcroft–Latham ($C_{\mathrm{crit,NCL}}$) micro-crack risk.

---

## Mathematical Formulation

### 1. Archard Die Tool Wear Model

Progressive stamping die wear ratio $W_{\mathrm{ratio}}$ per stroke is computed using Archard's wear law:

$$W_{\mathrm{raw}} = W_0 + K_{\mathrm{wear}} \cdot N_{\mathrm{stroke}} \cdot \left( \frac{F_{\mathrm{press}}}{F_{\mathrm{nominal}}} \right)^{\gamma_{\mathrm{archard}}}$$

where:
* **$W_0$** — Initial die wear ratio.
* **$N_{\mathrm{stroke}}$** — Cumulative die stroke count.
* **$\gamma_{\mathrm{archard}} = 1.35$** — Pressure exponent.
* **$K_{\mathrm{wear,duplex}} = 1.47 \times 10^{-10}\mathrm{mm}^3/(\mathrm{N}\cdot\mathrm{m})$** — Duplex PVD coating wear coefficient (Bitay et al. 2021).
* **$K_{\mathrm{wear,pvd}} = 3.50 \times 10^{-6}\mathrm{mm}^3/(\mathrm{N}\cdot\mathrm{m})$** — Standard PVD wear coefficient (Fernandes et al. 2017).

### 2. Normalized Cockcroft–Latham (NCL) Ductile Fracture Damage

Material plastic strain $\varepsilon_p$ and membrane stress $\sigma_1$ across 60 micro-channels ($A_{\mathrm{total}} = 0.0012\mathrm{ m}^2$) follow SS316L strain hardening:

$$\sigma_{\mathrm{flow}} = K_{\mathrm{strength}} \cdot \varepsilon_p^{n_{\mathrm{hardening}}}$$

where $K_{\mathrm{strength}} = 1280.0\mathrm{ MPa}$ and $n_{\mathrm{hardening}} = 0.43$ (Blandford 2007; Mahabunphachai & Koc 2008).

Plastic work done $W_{\mathrm{plastic}}$ is integrated and normalized against critical threshold $C_{\mathrm{crit,NCL}} = 0.35$ (Modanloo et al. 2018):

$$W_{\mathrm{plastic}} = \frac{\sigma_1 / K_{\mathrm{strength}}}{1 - n_{\mathrm{hardening}}} \cdot \frac{\varepsilon_p^{1 - n_{\mathrm{hardening}}}}{1 - n_{\mathrm{hardening}}}$$

$$\text{damage}_{\mathrm{NCL}} = \frac{W_{\mathrm{plastic}}}{C_{\mathrm{crit,NCL}}}$$

A defect is registered if $\text{damage}_{\mathrm{NCL}} > 1.0$ or wear ratio $W_{\mathrm{ratio}} \ge 0.75$.

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Critical NCL Damage Threshold | $C_{\mathrm{crit,NCL}}$ | $0.35$ | — | Modanloo et al. (2018) |
| Archard Pressure Exponent | $\gamma_{\mathrm{archard}}$ | $1.35$ | — | Archard (1953) |
| Duplex Wear Coeff. | $K_{\mathrm{wear,duplex}}$ | $1.47 \times 10^{-10}$ | $\mathrm{mm}^3/(\mathrm{N}\cdot\mathrm{m})$ | Bitay et al. (2021) |
| Standard PVD Wear Coeff. | $K_{\mathrm{wear,pvd}}$ | $3.50 \times 10^{-6}$ | $\mathrm{mm}^3/(\mathrm{N}\cdot\mathrm{m})$ | Fernandes et al. (2017) |
| Strength Coefficient 316L | $K_{\mathrm{strength}}$ | $1280.0$ | $\mathrm{MPa}$ | Blandford (2007) |
| Strain Hardening Exponent 316L | $n_{\mathrm{hardening}}$ | $0.43$ | — | Mahabunphachai & Koc (2008) |
| Nominal Press Force | $F_{\mathrm{nominal}}$ | $120.0$ | $\mathrm{kN}$ | Stamping Press Specs |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station3_bipolar_plate_stamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station3_bipolar_plate_stamping.py)
* Calibration Script: [`physical_engine/scripts/calibrate_stamping_clamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/scripts/calibrate_stamping_clamping.py)
