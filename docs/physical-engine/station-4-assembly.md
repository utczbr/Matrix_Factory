# Station 4: Stack Assembly & Clamping

This document details the mechanical bolt clamping relationships (VDI 2230), elastic interaction, non-linear GDL compression, and interfacial contact resistance models for **Station 4: Stack Clamping & Fastening**.

---

## Physical Process Description

Station 4 models the mechanical assembly of fuel cell stacks (repeating units of bipolar plates, GDLs, and MEAs). Tightening torque applied to tie-rods establishes interfacial clamping pressure $P_{\text{clamp}}$ ($\text{MPa}$), compressing the Gas Diffusion Layer (GDL) and altering contact electrical resistance $R_{\text{contact}}$, GDL bulk resistance $R_{\text{gdl}}$, and gas transport porosity $\varepsilon_{\text{gdl}}$.

---

## Mathematical Formulation

### 1. VDI 2230 Fastener Torque-Tension Relationship

Applied tightening torque $M_{A,i}$ ($\text{N}\cdot\text{m}$) to each of 4 M8 tie-rods ($i \in \{1, 2, 3, 4\}$) converts to nominal axial bolt pre-load force $F_{\text{nom},i}$ ($\text{N}$):

$$F_{\text{nom},i} = \frac{M_{A,i}}{\dfrac{p}{2\pi} + \dfrac{\mu_{\text{threads},i}\, d_2}{2 \cos\beta} + \mu_{\text{head},i}\, r_{\text{head}}}$$

where thread pitch $p = 1.25\text{ mm}$, pitch diameter $d_2 = 7.188\text{ mm}$, under-head radius $r_{\text{head}} = 5.125\text{ mm}$, and flank semi-angle $\beta = 30^\circ$. $\mu_{\text{threads},i}$ and $\mu_{\text{head},i}$ are **per-bolt** friction coefficients (each defaults to $0.15$ if not supplied).

Elastic interaction coupling reduces effective pre-load across adjacent bolts in a ring ($\alpha_{\text{elastic}} = 0.18$). For 1-indexed cyclic ring ordering ($i \in \{1, 2, 3, 4\}$):

$$F_{\text{real},1} = F_{\text{nom},1} - 0.18\, F_{\text{nom},4}$$

$$F_{\text{real},i} = F_{\text{nom},i} - 0.18\, F_{\text{nom},i-1} \quad \text{for } i \in \{2, 3, 4\}$$

Clamping pressure $P_{\text{clamp}}$ over active stack area $A_{\text{stack}} = 0.0225\text{ m}^2$ ($150 \times 150\text{ mm}$) is:

$$P_{\text{clamp}} = \frac{\sum_{i=1}^4 \max(0, F_{\text{real}, i})}{A_{\text{stack}}}$$

### 2. Non-Linear GDL Compression & Porosity Derating

Compacted GDL thickness $t_{\text{comp}}$ ($\mu\text{m}$) follows non-linear strain stiffness ($E_0 = 2.80\text{ MPa}$, $K_s = 28.5$; Kleemann et al. 2009; Norouzifard & Bahrami 2014):

$$t_{\text{comp}} = \max\!\Big(t_{\text{solid}} + 1.0\ \mu\text{m},\ t_0 \left( 1 - \frac{P_{\text{clamp}}}{E_0 + K_s P_{\text{clamp}}} \right)\Big), \qquad t_{\text{solid}} = t_0(1-\varepsilon_0)$$

where $1.0\ \mu\text{m}$ is a lower physical clearance bound added to solid fiber thickness $t_{\text{solid}} = t_0(1-\varepsilon_0) = 46.2\ \mu\text{m}$, preventing division-by-zero or non-physical zero-thickness collapse.

Compacted GDL porosity $\varepsilon_{\text{gdl}}$ is derated via mass conservation, then clamped to $[0.01, 0.95]$:

$$\varepsilon_{\text{gdl}} = \max\!\Big(0.01,\ \min\!\big(0.95,\ 1 - (1 - \varepsilon_0) \tfrac{t_0}{t_{\text{comp}}}\big)\Big)$$

Tangential elastic modulus $E_{\text{tangent}}$ scales with pressure:

$$E_{\text{tangent}} = E_0 \left( 1 + \frac{K_s}{E_0} P_{\text{clamp}} \right)^2$$

### 3. Interfacial Contact Resistance & Upstream Micro-Crack Propagation Model (`microstructure.py`)

Microstructure contact resistance $R_{\text{contact}}$ ($\Omega\cdot\text{cm}^2$) is a **U-shaped penalty centered on a nominal clamping setpoint** $P_{\text{nom}} = 4.25\text{ MPa}$, coupled to Station 3 ductile micro-crack damage ($\text{damage}_{\text{NCL}}$):

$$p_{\text{dev}} = \frac{\left|P_{\text{clamp}} - P_{\text{nom}}\right|}{P_{\text{nom}}}$$

$$R_{\text{contact}}(P_{\text{clamp}}, \text{damage}_{\text{NCL}}) = R_{\text{contact},0} \left(1 + 0.35\, p_{\text{dev}} + 0.25\, p_{\text{dev}}^2\right) \left(1 + \beta_{\text{crack}} \cdot \text{damage}_{\text{NCL}}\right)$$

with $P_{\text{clamp}}$ floored at $0.5\text{ MPa}$ before evaluation and micro-crack penalty coefficient $\beta_{\text{crack}} = 0.15$ accounting for contact stress non-uniformity caused by stamping springback and micro-cracks. Two calibrated reference points are used depending on plate surface treatment:

* $R_{\text{contact},0} = 0.0042\ \Omega\cdot\text{cm}^2$ ($4.20\ \text{m}\Omega\cdot\text{cm}^2$) — TiAlN/CrN-coated plate (default).
* $R_{\text{contact,uncoated}} = 0.0185\ \Omega\cdot\text{cm}^2$ ($18.50\ \text{m}\Omega\cdot\text{cm}^2$) — uncoated 316L reference.

Both constants trace to El-Kharouf, Mason, Brett & Pollet (2012).

**Bruggeman effective conductivity & Bulk GDL Resistance.** The effective bulk electrical conductivity $\sigma_{\text{eff}}$ ($\text{S/cm}$) and bulk GDL resistance $R_{\text{gdl}}$ ($\Omega\cdot\text{cm}^2$) are calculated via:

$$\sigma_{\text{eff}} = \sigma_{\text{bulk}} \left(1 - \varepsilon_{\text{gdl}}\right)^{m}, \qquad m = 1.5 \ \text{(standard Bruggeman exponent, fibrous porous media)}$$

$$R_{\text{gdl}}(t_{\text{comp}}, \varepsilon_{\text{gdl}}) = \frac{t_{\text{comp}} \times 10^{-4}\text{ cm}}{\sigma_{\text{eff}}}$$

where $\sigma_{\text{bulk}} = 220.0\text{ S/cm}$ (carbon fiber paper bulk electrical conductivity). $R_{\text{gdl}}$ feeds directly into Station 5's effective internal resistance equation.

### 4. Defect Criteria

A component/assembly is flagged defective if any of the following hold:

* **Under-clamped:** $P_{\text{clamp}} < 3.0\text{ MPa}$
* **Over-clamped:** $P_{\text{clamp}} > 5.5\text{ MPa}$
* **Torque imbalance:** the unbiased sample standard deviation of the four applied torques exceeds $1.2\text{ N}\cdot\text{m}$ (Station 4 accelerated timing) or $1.8\text{ N}\cdot\text{m}$ (otherwise)

### 5. Execution Pacing

$$t_{\text{proc}} = k_{\text{time}} \cdot t_{\text{base}} \left(1 + 0.08\, \tau_{\text{std}}\right), \qquad t_{\text{base}} = 24.0\text{ s (Station 4)} \text{ or } 3.0\text{ s (otherwise)}$$

$$\text{var\_ratio} = 1.0 + 0.35\, p_{\text{dev}} + 0.25\, \tau_{\text{std}}$$

where $\tau_{\text{std}}$ is the unbiased torque standard deviation, and $p_{\text{dev}}$ is measured against the $4.25\text{ MPa}$ setpoint.

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Baseline Contact Resistance (coated) | $R_{\text{contact},0}$ | $0.0042$ ($4.20\text{ m}\Omega\cdot\text{cm}^2$) | $\Omega\cdot\text{cm}^2$ | El-Kharouf, Mason, Brett & Pollet (2012) |
| Baseline Contact Resistance (uncoated 316L) | $R_{\text{contact,uncoated}}$ | $0.0185$ ($18.50\text{ m}\Omega\cdot\text{cm}^2$) | $\Omega\cdot\text{cm}^2$ | El-Kharouf, Mason, Brett & Pollet (2012) |
| Micro-Crack Contact Penalty Coeff. | $\beta_{\text{crack}}$ | $0.15$ | — | Micro-crack stress non-uniformity factor |
| Nominal Clamping Setpoint | $P_{\text{nom}}$ | $4.25$ | $\text{MPa}$ | Target clamping pressure |
| Carbon Fiber Bulk Conductivity | $\sigma_{\text{bulk}}$ | $220.0$ | $\text{S/cm}$ | Toray TGP-H-060 Datasheet |
| Bruggeman Exponent | $m$ | $1.5$ | — | Standard value for fibrous porous media |
| Nominal Bolt Torque | $M_A$ | $46.0$ | $\text{N}\cdot\text{m}$ | Target Torque (~4.25 MPa) |
| Initial GDL Elasticity | $E_0$ | $2.80$ | $\text{MPa}$ | Kleemann et al. (2009) |
| Non-linear Stiffness Parameter | $K_s$ | $28.5$ | — | Norouzifard & Bahrami (2014) |
| Uncompressed Thickness | $t_0$ | $210.0$ | $\mu\text{m}$ | Toray TGP-H-060 Datasheet |
| Initial GDL Porosity | $\varepsilon_0$ | $0.78$ | — | Toray TGP-H-060 Datasheet |
| Lower Compaction Clearance Bound | — | $1.0$ | $\mu\text{m}$ | Physical minimum clearance bound |
| Elastic Interaction Coeff. | $\alpha_{\text{elastic}}$ | $0.18$ | — | Fastener Elastic Coupling |
| Under-Clamp Threshold | — | $3.0$ | $\text{MPa}$ | Quality Threshold |
| Over-Clamp Threshold | — | $5.5$ | $\text{MPa}$ | Quality Threshold |
| Torque Imbalance Threshold | — | $1.2$ / $1.8$ | $\text{N}\cdot\text{m}$ | Quality Threshold (Station-4 / other) |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station4_stack_clamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station4_stack_clamping.py)
* Microstructure Model: [`physical_engine/factory_simulation/microstructure.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/microstructure.py)
