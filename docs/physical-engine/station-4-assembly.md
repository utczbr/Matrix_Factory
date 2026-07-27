# Station 4: Stack Assembly & Clamping (Reference)

This document details the mechanical bolt clamping relationships (VDI 2230), contact stress distribution, and GDL porosity derating models for **Station 4: Stack Clamping & Fastening**.

---

## Physical Process Description

Station 4 models the mechanical assembly of fuel cell stacks (repeating units of bipolar plates, GDLs, and MEAs). Tightening torque applied to tie-rods establishes interfacial clamping pressure $P_{\text{clamp}}$ ($\text{MPa}$), compressing the Gas Diffusion Layer (GDL) and altering contact electrical resistance $R_{\text{contact}}$ and gas transport porosity $\varepsilon_{\text{gdl}}$.

---

## Mathematical Formulation

### 1. VDI 2230 Bolt Torque-Tension Friction Equation

The relationship between applied bolt torque $M_A$ ($\text{N}\cdot\text{m}$) and axial clamping force $F_M$ ($\text{kN}$) follows standard VDI 2230 guidelines:

$$M_A = F_M \left( \frac{p}{2\pi} + 0.577 d_2 \mu_threads + d_b \mu_head \right)$$

where:
* $p$ is bolt thread pitch ($\text{mm}$).
* $d_2$ is pitch diameter ($\text{mm}$).
* $\mu_threads$ and $\mu_head$ are thread and head friction coefficients.

### 2. Interfacial Contact Resistance & Bruggeman Porosity Derating

Interfacial contact resistance $R_{\text{contact}}$ decreases exponentially with clamping pressure $P_{\text{clamp}}$:

$$R_{\text{contact}}(P_{\text{clamp}}) = R_{\text{contact},0} \cdot \exp\left( -k_{\text{press}} P_{\text{clamp}} \right) + R_{\text{min}}$$

where $R_{\text{contact},0} = 4.20\text{ m}\Omega\cdot\text{cm}^2$.

Compacted GDL porosity $\varepsilon_{\text{gdl}}$ decreases under mechanical strain $\varepsilon_{\text{mech}}$:

$$\varepsilon_{\text{gdl}}(P_{\text{clamp}}) = 1 - (1 - \varepsilon_0) \cdot \left( 1 + \frac{P_{\text{clamp}}}{E_{\text{gdl}}} \right)$$

Effective gas diffusivity $D_{\text{eff}}$ is derated via Bruggeman's relation:

$$D_{\text{eff}} = D_0 \cdot \left( \varepsilon_{\text{gdl}}(P_{\text{clamp}}) \right)^{1.5}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Initial Contact Resistance | $R_{\text{contact},0}$ | $4.20$ | $\text{m}\Omega\cdot\text{cm}^2$ | Kleemann et al. (2021) |
| Nominal Clamping Pressure | $P_{\text{clamp}}$ | $1.25$ | $\text{MPa}$ | Assembly Specs |
| Uncompressed GDL Porosity | $\varepsilon_0$ | $0.78$ | — | Toray TGP-H-060 Datasheet |
| GDL Compressibility Modulus | $E_{\text{gdl}}$ | $8.50$ | $\text{MPa}$ | Mechanical Testing |
| Tie-rod Thread Friction | $\mu_threads$ | $0.12$ | — | VDI 2230 Standard |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station4_stack_clamping.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station4_stack_clamping.py)
