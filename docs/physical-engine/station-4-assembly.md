# Station 4: Stack Assembly & Clamping

This document details the mechanical bolt clamping relationships (VDI 2230), elastic interaction, non-linear GDL compression, and interfacial contact resistance models for **Station 4: Stack Clamping & Fastening**.

---

## Physical Process Description

Station 4 models the mechanical assembly of fuel cell stacks (repeating units of bipolar plates, GDLs, and MEAs). Tightening torque applied to tie-rods establishes interfacial clamping pressure $P_{\text{clamp}}$ ($\text{MPa}$), compressing the Gas Diffusion Layer (GDL) and altering contact electrical resistance $R_{\text{contact}}$ and gas transport porosity $\varepsilon_{\text{gdl}}$.

---

## Mathematical Formulation

### 1. VDI 2230 Fastener Torque-Tension Relationship

Applied tightening torque $M_A$ ($\text{N}\cdot\text{m}$) to each of 4 M8 tie-rods converts to axial bolt pre-load force $F_M$ ($\text{N}$):

$$F_{M,i} = \frac{M_{A,i}}{\dfrac{p}{2\pi} + \dfrac{\mu_{\text{threads},i}\, d_2}{2 \cos\beta} + \mu_{\text{head},i}\, r_{\text{head}}}$$

where $p = 1.25\text{ mm}$, pitch diameter $d_2 = 7.188\text{ mm}$, under-head radius $r_{\text{head}} = 5.125\text{ mm}$, and flank semi-angle $\beta = 30^\circ$. $\mu_{\text{threads},i}$ and $\mu_{\text{head},i}$ are **per-bolt** friction coefficients (each defaults to $0.15$ if not supplied).

Elastic interaction coupling reduces effective pre-load across adjacent bolts in a ring ($\alpha_{\text{elastic}} = 0.18$; bolt indices are cyclic, i.e. bolt 1 is coupled to bolt 4):

$$F_{\text{real}, i} = F_{\text{nom}, i} - 0.18\, F_{\text{nom}, i-1 \bmod 4}$$

Clamping pressure $P_{\text{clamp}}$ over active stack area $A_{\text{stack}} = 0.0225\text{ m}^2$ ($150 \times 150\text{ mm}$) is:

$$P_{\text{clamp}} = \frac{\sum_{i=1}^4 \max(0, F_{\text{real}, i})}{A_{\text{stack}}}$$

### 2. Non-Linear GDL Compression & Porosity Derating

Compacted GDL thickness $t_{\text{comp}}$ ($\mu\text{m}$) follows non-linear strain stiffness ($E_0 = 2.80\text{ MPa}$, $K_s = 28.5$; Kleemann et al. 2009; Norouzifard & Bahrami 2014):

$$t_{\text{comp}} = \max\!\Big(t_{\text{solid}}+1,\ t_0 \left( 1 - \frac{P_{\text{clamp}}}{E_0 + K_s P_{\text{clamp}}} \right)\Big), \qquad t_{\text{solid}} = t_0(1-\varepsilon_0)$$

Compacted GDL porosity $\varepsilon_{\text{gdl}}$ is derated via mass conservation, then clamped to $[0.01, 0.95]$:

$$\varepsilon_{\text{gdl}} = \max\!\Big(0.01,\ \min\!\big(0.95,\ 1 - (1 - \varepsilon_0) \tfrac{t_0}{t_{\text{comp}}}\big)\Big)$$

Tangential elastic modulus $E_{\text{tangent}}$ scales with pressure:

$$E_{\text{tangent}} = E_0 \left( 1 + \frac{K_s}{E_0} P_{\text{clamp}} \right)^2$$

### 3. Interfacial Contact Resistance Model (`microstructure.py`)

Microstructure contact resistance $R_{\text{contact}}$ ($\Omega\cdot\text{cm}^2$) is a **U-shaped penalty centered on a nominal clamping setpoint** $P_{\text{nom}} = 4.25\text{ MPa}$ — both under-clamping (loss of micro-contact area) and over-clamping (channel intrusion/fiber crushing) increase resistance relative to the setpoint:

$$p_{\text{dev}} = \frac{\left|P_{\text{clamp}} - P_{\text{nom}}\right|}{P_{\text{nom}}}$$

$$R_{\text{contact}}(P_{\text{clamp}}) = R_{\text{contact},0} \left(1 + 0.35\, p_{\text{dev}} + 0.25\, p_{\text{dev}}^2\right)$$

with $P_{\text{clamp}}$ floored at $0.5\text{ MPa}$ before evaluation. Two calibrated reference points are used depending on plate surface treatment:

* $R_{\text{contact},0} = 0.0042\ \Omega\cdot\text{cm}^2$ ($4.20\ \text{m}\Omega\cdot\text{cm}^2$) — TiAlN/CrN-coated plate (default).
* $R_{\text{contact,uncoated}} = 0.0185\ \Omega\cdot\text{cm}^2$ ($18.50\ \text{m}\Omega\cdot\text{cm}^2$) — uncoated 316L reference.

Both constants trace to El-Kharouf, Mason, Brett & Pollet (2012).

**Bruggeman effective conductivity.** The same module implements the effective-medium relation:

$$\sigma_{\text{eff}} = \sigma_{\text{bulk}} \left(1 - \varepsilon_{\text{gdl}}\right)^{m}, \qquad m = 1.5 \ \text{(standard Bruggeman exponent, fibrous porous media)}$$

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
| Nominal Clamping Setpoint | $P_{\text{nom}}$ | $4.25$ | $\text{MPa}$ | Target clamping pressure |
| Bruggeman Exponent | $m$ | $1.5$ | — | Standard value for fibrous porous media |
| Nominal Bolt Torque | $M_A$ | $46.0$ | $\text{N}\cdot\text{m}$ | Target Torque (~4.25 MPa) |
| Initial GDL Elasticity | $E_0$ | $2.80$ | $\text{MPa}$ | Kleemann et al. (2009) |
| Non-linear Stiffness Parameter | $K_s$ | $28.5$ | — | Norouzifard & Bahrami (2014) |
| Uncompressed Thickness | $t_0$ | $210.0$ | $\mu\text{m}$ | Toray TGP-H-060 Datasheet |
| Initial GDL Porosity | $\varepsilon_0$ | $0.78$ | — | Toray TGP-H-060 Datasheet |
| Elastic Interaction Coeff. | $\alpha_{\text{elastic}}$ | $0.18$ | — | Fastener Elastic Coupling |
| Under-Clamp Threshold | — | $3.0$ | $\text{MPa}$ | Quality Threshold |
| Over-Clamp Threshold | — | $5.5$ | $\text{MPa}$ | Quality Threshold |
| Torque Imbalance Threshold | — | $1.2$ / $1.8$ | $\text{N}\cdot\text{m}$ | Quality Threshold (Station-4 / other) |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station4_stack_clamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station4_stack_clamping.py)
* Microstructure Model: [`physical_engine/factory_simulation/microstructure.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/microstructure.py)
