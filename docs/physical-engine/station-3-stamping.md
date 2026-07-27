# Station 3: Bipolar Plate Stamping

This document details the continuum mechanics models, Archard tool wear rate, and Normalized Cockcroft–Latham ductile damage criterion for **Station 3: Bipolar Plate Stamping**.

---

## Physical Process Description

Station 3 models high-speed metal forming of metallic bipolar plate flow channels (stainless steel 316L). The process calculates stamping press force, plastic strain work, progressive tool wear, and Normalized Cockcroft–Latham ($C_{\text{crit,NCL}}$) micro-crack risk.

---

## Mathematical Formulation

### 1. Archard Die Tool Wear Model

Progressive stamping die wear volume $V_{\text{wear}}$ and normalized wear ratio $W_{\text{ratio}}$ per stroke are computed using Archard's wear law:

$$W_{\text{raw}} = W_0 + \frac{K_{\text{wear}} \cdot (F_{\text{nominal}} \times 10^3) \cdot s_{\text{slide}} \cdot N_{\text{stroke}}}{V_{\text{crit}}} \left( \frac{F_{\text{press}}}{F_{\text{nominal}}} \right)^{\gamma_{\text{archard}}}$$

$$W_{\text{ratio}} = \min(0.99999,\ \max(0,\ W_{\text{raw}}))$$

where:

* **$W_0$** — Initial die wear ratio (input).
* **$N_{\text{stroke}}$** — Cumulative die stroke count.
* **$s_{\text{slide}} = 0.002\text{ m}$ ($2.0\text{ mm}$)** — Sliding contact draw distance per stroke.
* **$V_{\text{crit}} = 0.05\text{ mm}^3$** — Critical allowable die wear volume threshold.
* **$\gamma_{\text{archard}} = 1.35$** — Pressure exponent.
* **$K_{\text{wear}}$** — Either $K_{\text{wear,duplex}} = 1.47 \times 10^{-10}\text{ mm}^3/(\text{N}\cdot\text{m})$ if the die uses a duplex PVD coating, or $K_{\text{wear,pvd}} = 3.50 \times 10^{-6}\text{ mm}^3/(\text{N}\cdot\text{m})$ for a standard PVD coating.

The force ratio $(F_{\text{press}}/F_{\text{nominal}})$, sliding distance $s_{\text{slide}}$, and critical wear volume $V_{\text{crit}}$ normalize Archard's volume loss $V_{\text{wear}}$ ($\text{mm}^3$) into a dimensionally consistent dimensionless wear fraction $W_{\text{raw}} \in [0, 1]$.

### 2. From Press Force to Local Stress State

The NCL criterion requires a local plastic strain $\varepsilon_p$ and local stress $\sigma_1$, which are derived from `press_force_kn` and the current wear state via a wear-coupled friction model.

**Wear-coupled local friction.** As the die wears, local friction at the flow-channel radius rises:

$$\mu_{\text{local}} = \mu_0 + \alpha_f \cdot W_{\text{ratio}}, \qquad \mu_0 = 0.12,\ \ \alpha_f = 0.45$$

**Plastic strain (empirical process proxy).** Plastic strain scales linearly with normalized press force:

$$\varepsilon_p = \varepsilon_{p,\text{scale}} \cdot \frac{F_{\text{press}}}{F_{\text{nominal}}}, \qquad \varepsilon_{p,\text{scale}} = 0.1456$$

**Local stress & Angular radian conversion.** Press force is spread over the total engaged micro-channel area ($A_{\text{total}} = 0.0012\ \text{m}^2$ across 60 channels, $1.0\text{ mm}$ wide $\times$ $20.0\text{ mm}$ engaged length each) to obtain a membrane/channel stress. Friction augmentation across die draft angle $\theta_{\text{die}} = 10.0^\circ$ is evaluated using explicit conversion to radians ($\theta_{\text{rad}} = \frac{\theta_{\text{die}}\pi}{180} = 0.17453\text{ rad}$):

$$\sigma_{\text{mem}} = \frac{F_{\text{press}} \times 10^3}{A_{\text{total}}} \times 10^{-6} \quad [\text{MPa}]$$

$$\sigma_{\text{flow}} = K_{\text{strength}} \cdot \varepsilon_p^{\,n_{\text{hardening}}}$$

$$\sigma_1 = \sigma_{\text{mem}} \cdot \exp\!\left(\mu_{\text{local}} \cdot \frac{\theta_{\text{die}}\pi}{180}\right) + \sigma_{\text{flow}}$$

where $K_{\text{strength}} = 1280.0\text{ MPa}$ and $n_{\text{hardening}} = 0.43$ (Blandford 2007; Mahabunphachai & Koc 2008).

### 3. Normalized Cockcroft–Latham (NCL) Ductile Fracture Damage Integral

The Normalized Cockcroft–Latham (NCL) ductile damage criterion evaluates normalized plastic work by integrating tensile stress $\sigma_1$ over flow stress $\sigma_{\text{flow}} = K_{\text{strength}}\varepsilon_p^n$:

$$C_{\text{NCL}} = \int_0^{\varepsilon_p} \frac{\sigma_1}{\sigma_{\text{flow}}} \, d\varepsilon_p = \int_0^{\varepsilon_p} \left( \frac{\sigma_{\text{mem}} e^{\mu_{\text{local}}\theta_{\text{rad}}}}{K_{\text{strength}}} \varepsilon_p^{-n_{\text{hardening}}} + 1 \right) d\varepsilon_p$$

Evaluating this integral yields the plastic work index $W_{\text{plastic}}$:

$$W_{\text{plastic}} = \frac{\sigma_{\text{mem}} \cdot \exp\!\left(\mu_{\text{local}} \cdot \frac{\theta_{\text{die}}\pi}{180}\right)}{K_{\text{strength}}\left(1 - n_{\text{hardening}}\right)} \cdot \varepsilon_p^{1 - n_{\text{hardening}}} + \varepsilon_p$$

$$\text{damage}_{\text{NCL}} = \min\left(2.0,\ \max\left(0,\ \frac{W_{\text{plastic}}}{C_{\text{crit,NCL}}}\right)\right)$$

A component is flagged defective if $\text{damage}_{\text{NCL}} > 1.0$ or $W_{\text{ratio}} \ge 0.75$. $\text{damage}_{\text{NCL}}$ propagates downstream to Station 4 to scale interfacial contact stress non-uniformity via $(1 + \beta_{\text{crack}} \cdot \text{damage}_{\text{NCL}})$.

### 4. Execution Pacing

$$t_{\text{proc}} = k_{\text{time}} \cdot t_{\text{base}} \left(1 + 0.12\, F_{\text{dev}} + 0.18\, W_{\text{ratio}}\right), \qquad t_{\text{base}} = 3.0\ \text{s}$$

$$\text{var\_ratio} = 1.0 + 0.40\, W_{\text{ratio}} + 0.30\, \text{damage}_{\text{NCL}}^2$$

where $F_{\text{dev}} = |F_{\text{press}} - F_{\text{nominal}}| / F_{\text{nominal}}$.

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Critical NCL Damage Threshold | $C_{\text{crit,NCL}}$ | $0.35$ | — | Modanloo et al. (2018) |
| Sliding Contact Distance | $s_{\text{slide}}$ | $0.002$ ($2.0\text{ mm}$) | $\text{m}$ | Die draw contact length |
| Critical Wear Volume | $V_{\text{crit}}$ | $0.05$ | $\text{mm}^3$ | Allowable die coating wear volume |
| Archard Pressure Exponent | $\gamma_{\text{archard}}$ | $1.35$ | — | Archard (1953), DOI `10.1063/1.1721448` |
| Duplex Wear Coeff. | $K_{\text{wear,duplex}}$ | $1.47 \times 10^{-10}$ | $\text{mm}^3/(\text{N}\cdot\text{m})$ | Bitay et al. (2021) |
| Standard PVD Wear Coeff. | $K_{\text{wear,pvd}}$ | $3.50 \times 10^{-6}$ | $\text{mm}^3/(\text{N}\cdot\text{m})$ | Fernandes et al. (2017) |
| Strength Coefficient 316L | $K_{\text{strength}}$ | $1280.0$ | $\text{MPa}$ | Blandford (2007) / Mahabunphachai & Koc (2008) |
| Strain Hardening Exponent 316L | $n_{\text{hardening}}$ | $0.43$ | — | Mahabunphachai & Koc (2008) |
| Nominal Press Force | $F_{\text{nominal}}$ | $120.0$ | $\text{kN}$ | Stamping Press Specs |
| Wear-Friction Baseline | $\mu_0$ | $0.12$ | — | Process Baseline |
| Wear-Friction Acceleration | $\alpha_f$ | $0.45$ | — | Process Baseline |
| Plastic Strain Scale | $\varepsilon_{p,\text{scale}}$ | $0.1456$ | — | Process Baseline |
| Die Draft Angle | $\theta_{\text{die}}$ | $10.0$ | $^\circ$ | Die Geometry Spec ($0.17453\text{ rad}$) |
| Critical Wear Ratio | $W_{\text{crit}}$ | $0.75$ | — | Defect threshold |
| Total Channel Area | $A_{\text{total}}$ | $0.0012$ | $\text{m}^2$ | 60 channels $\times$ 1.0mm $\times$ 20.0mm |
| Nominal Station Cycle Time | $t_{\text{base}}$ | $3.0$ | $\text{s}$ | `factory.jcm` process recipe |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station3_bipolar_plate_stamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station3_bipolar_plate_stamping.py)
* Calibration Script: [`physical_engine/scripts/calibrate_stamping_clamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/scripts/calibrate_stamping_clamping.py)
