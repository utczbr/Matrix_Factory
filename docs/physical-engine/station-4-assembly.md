# Station 4: Stack Assembly & Clamping (Reference)

This document details the mechanical bolt clamping relationships (VDI 2230), elastic interaction, and non-linear GDL compression models for **Station 4: Stack Clamping & Fastening**.

---

## Physical Process Description

Station 4 models the mechanical assembly of fuel cell stacks (repeating units of bipolar plates, GDLs, and MEAs). Tightening torque applied to tie-rods establishes interfacial clamping pressure $P_{\mathrm{clamp}}$ ($\mathrm{MPa}$), compressing the Gas Diffusion Layer (GDL) and altering contact electrical resistance $R_{\mathrm{contact}}$ and gas transport porosity $\varepsilon_{\mathrm{gdl}}$.

---

## Mathematical Formulation

### 1. VDI 2230 Fastener Torque-Tension Relationship

Applied tightening torque $M_A$ ($\mathrm{N}\cdot\mathrm{m}$) to 4 M8 tie-rods converts to axial bolt pre-load force $F_M$ ($\mathrm{N}$):

$$F_M = \frac{M_A}{\frac{p}{2\pi} + \frac{\mu_{\mathrm{threads}} d_2}{2 \cos\beta} + \mu_{\mathrm{head}} r_{\mathrm{head}}}$$

where $p = 1.25\mathrm{ mm}$, pitch diameter $d_2 = 7.188\mathrm{ mm}$, under-head radius $r_{\mathrm{head}} = 5.125\mathrm{ mm}$, and flank semi-angle $\beta = 30^\circ$.

Elastic interaction coupling reduces effective pre-load across adjacent bolts ($\alpha_{\mathrm{elastic}} = 0.18$):

$$F_{\mathrm{real}, i} = F_{\mathrm{nom}, i} - 0.18 F_{\mathrm{nom}, i-1}$$

Clamping pressure $P_{\mathrm{clamp}}$ over active stack area $A_{\mathrm{stack}} = 0.0225\mathrm{ m}^2$ ($150 \times 150\mathrm{ mm}$) is:

$$P_{\mathrm{clamp}} = \frac{\sum_{i=1}^4 \max(0, F_{\mathrm{real}, i})}{A_{\mathrm{stack}}}$$

### 2. Non-Linear GDL Compression & Porosity Derating

Compacted GDL thickness $t_{\mathrm{comp}}$ ($\mu\mathrm{m}$) follows non-linear strain stiffness ($E_0 = 2.80\mathrm{ MPa}$, $K_s = 28.5$; Kleemann et al. 2009; Norouzifard & Bahrami 2014):

$$t_{\mathrm{comp}} = t_0 \left( 1 - \frac{P_{\mathrm{clamp}}}{E_0 + K_s P_{\mathrm{clamp}}} \right)$$

Compacted GDL porosity $\varepsilon_{\mathrm{gdl}}$ is derated via mass conservation ($t_{\mathrm{solid}} = t_0 (1 - \varepsilon_0)$):

$$\varepsilon_{\mathrm{gdl}} = 1 - (1 - \varepsilon_0) \frac{t_0}{t_{\mathrm{comp}}}$$

Tangent elastic modulus $E_{\mathrm{tangent}}$ scales with pressure:

$$E_{\mathrm{tangent}} = E_0 \left( 1 + \frac{K_s}{E_0} P_{\mathrm{clamp}} \right)^2$$

### 3. Interfacial Contact Resistance Model (`microstructure.py`)

Microstructure contact resistance $R_{\mathrm{contact}}$ ($\Omega\cdot\mathrm{cm}^2$) decreases exponentially with clamping pressure ($R_{\mathrm{contact},0} = 0.0042\ \Omega\cdot\mathrm{cm}^2$; Mason et al. 2012):

$$R_{\mathrm{contact}}(P_{\mathrm{clamp}}) = R_{\mathrm{contact},0} \cdot \exp\left(-0.45 P_{\mathrm{clamp}}\right) + R_{\mathrm{min}}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Baseline Contact Resistance | $R_{\mathrm{contact},0}$ | $0.0042$ ($4.20\mathrm{ m}\Omega\cdot\mathrm{cm}^2$) | $\Omega\cdot\mathrm{cm}^2$ | Mason et al. (2012) |
| Nominal Bolt Torque | $M_A$ | $46.0$ | $\mathrm{N}\cdot\mathrm{m}$ | Target Torque ($\sim 4.22\mathrm{ MPa}$) |
| Initial GDL Elasticity | $E_0$ | $2.80$ | $\mathrm{MPa}$ | Kleemann et al. (2009) |
| Non-linear Stiffness Parameter | $K_s$ | $28.5$ | — | Norouzifard & Bahrami (2014) |
| Uncompressed Thickness | $t_0$ | $210.0$ | $\mu\mathrm{m}$ | Toray TGP-H-060 Datasheet |
| Initial GDL Porosity | $\varepsilon_0$ | $0.78$ | — | Toray TGP-H-060 Datasheet |
| Elastic Interaction Coeff. | $\alpha_{\mathrm{elastic}}$ | $0.18$ | — | Fastener Elastic Coupling |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station4_stack_clamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station4_stack_clamping.py)
* Microstructure Model: [`physical_engine/factory_simulation/microstructure.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/microstructure.py)
