# Station 4: Stack Assembly & Clamping

This document details the mechanical bolt clamping relationships (VDI 2230), elastic interaction, and non-linear GDL compression models for **Station 4: Stack Clamping & Fastening**.

---

## Physical Process Description

Station 4 models the mechanical assembly of fuel cell stacks (repeating units of bipolar plates, GDLs, and MEAs). Tightening torque applied to tie-rods establishes interfacial clamping pressure $P_{\text{clamp}}$ ($\text{MPa}$), compressing the Gas Diffusion Layer (GDL) and altering contact electrical resistance $R_{\text{contact}}$ and gas transport porosity $\varepsilon_{\text{gdl}}$.

---

## Mathematical Formulation

### 1. VDI 2230 Fastener Torque-Tension Relationship

Applied tightening torque $M_A$ ($\text{N}\cdot\text{m}$) to 4 M8 tie-rods converts to axial bolt pre-load force $F_M$ ($\text{N}$):

$$F_M = \frac{M_A}{\frac{p}{2\pi} + \frac{\mu_{\text{threads}} d_2}{2 \cos\beta} + \mu_{\text{head}} r_{\text{head}}}$$

where $p = 1.25\text{ mm}$, pitch diameter $d_2 = 7.188\text{ mm}$, under-head radius $r_{\text{head}} = 5.125\text{ mm}$, and flank semi-angle $\beta = 30^\circ$.

Elastic interaction coupling reduces effective pre-load across adjacent bolts ($\alpha_{\text{elastic}} = 0.18$):

$$F_{\text{real}, i} = F_{\text{nom}, i} - 0.18 F_{\text{nom}, i-1}$$

Clamping pressure $P_{\text{clamp}}$ over active stack area $A_{\text{stack}} = 0.0225\text{ m}^2$ ($150 \times 150\text{ mm}$) is:

$$P_{\text{clamp}} = \frac{\sum_{i=1}^4 \max(0, F_{\text{real}, i})}{A_{\text{stack}}}$$

### 2. Non-Linear GDL Compression & Porosity Derating

Compacted GDL thickness $t_{\text{comp}}$ ($\mu\text{m}$) follows non-linear strain stiffness ($E_0 = 2.80\text{ MPa}$, $K_s = 28.5$; Kleemann et al. 2009; Norouzifard & Bahrami 2014):

$$t_{\text{comp}} = t_0 \left( 1 - \frac{P_{\text{clamp}}}{E_0 + K_s P_{\text{clamp}}} \right)$$

Compacted GDL porosity $\varepsilon_{\text{gdl}}$ is derated via mass conservation ($t_{\text{solid}} = t_0 (1 - \varepsilon_0)$):

$$\varepsilon_{\text{gdl}} = 1 - (1 - \varepsilon_0) \frac{t_0}{t_{\text{comp}}}$$

Tangent elastic modulus $E_{\text{tangent}}$ scales with pressure:

$$E_{\text{tangent}} = E_0 \left( 1 + \frac{K_s}{E_0} P_{\text{clamp}} \right)^2$$

### 3. Interfacial Contact Resistance Model (`microstructure.py`)

Microstructure contact resistance $R_{\text{contact}}$ ($\Omega\cdot\text{cm}^2$) decreases exponentially with clamping pressure ($R_{\text{contact},0} = 0.0042\ \Omega\cdot\text{cm}^2$; Mason et al. 2012):

$$R_{\text{contact}}(P_{\text{clamp}}) = R_{\text{contact},0} \cdot \exp\left(-0.45 P_{\text{clamp}}\right) + R_{\text{min}}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Baseline Contact Resistance | $R_{\text{contact},0}$ | $0.0042$ ($4.20\text{ m}\Omega\cdot\text{cm}^2$) | $\Omega\cdot\text{cm}^2$ | Mason et al. (2012) |
| Nominal Bolt Torque | $M_A$ | $46.0$ | $\text{N}\cdot\text{m}$ | Target Torque ($\sim 4.22\text{ MPa}$) |
| Initial GDL Elasticity | $E_0$ | $2.80$ | $\text{MPa}$ | Kleemann et al. (2009) |
| Non-linear Stiffness Parameter | $K_s$ | $28.5$ | — | Norouzifard & Bahrami (2014) |
| Uncompressed Thickness | $t_0$ | $210.0$ | $\mu\text{m}$ | Toray TGP-H-060 Datasheet |
| Initial GDL Porosity | $\varepsilon_0$ | $0.78$ | — | Toray TGP-H-060 Datasheet |
| Elastic Interaction Coeff. | $\alpha_{\text{elastic}}$ | $0.18$ | — | Fastener Elastic Coupling |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station4_stack_clamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station4_stack_clamping.py)
* Microstructure Model: [`physical_engine/factory_simulation/microstructure.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/microstructure.py)
