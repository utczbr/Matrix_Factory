# Station 4: Stack Assembly & Clamping (Reference)

This document details the mechanical bolt clamping relationships (VDI 2230), contact stress distribution, and GDL porosity derating models for **Station 4: Stack Clamping & Fastening**.

---

## Physical Process Description

Station 4 models the mechanical assembly of fuel cell stacks (repeating units of bipolar plates, GDLs, and MEAs). Tightening torque applied to tie-rods establishes interfacial clamping pressure $P_{\mathrm{clamp}}$ ($\mathrm{MPa}$), compressing the Gas Diffusion Layer (GDL) and altering contact electrical resistance $R_{\mathrm{contact}}$ and gas transport porosity $\varepsilon_{\mathrm{gdl}}$.

---

## Mathematical Formulation

### 1. VDI 2230 Bolt Torque-Tension Friction Equation

The relationship between applied bolt torque $M_A$ ($\mathrm{N}\cdot\mathrm{m}$) and axial clamping force $F_M$ ($\mathrm{kN}$) follows standard VDI 2230 guidelines:

$$M_A = F_M \left( \frac{p}{2\pi} + 0.577 d_2 \mu_{\mathrm{threads}} + d_b \mu_{\mathrm{head}} \right)$$

where:
* **$p$** — Bolt thread pitch ($\mathrm{mm}$).
* **$d_2$** — Pitch diameter ($\mathrm{mm}$).
* **$\mu_{\mathrm{threads}}$**, **$\mu_{\mathrm{head}}$** — Thread and head friction coefficients.

### 2. Interfacial Contact Resistance & Bruggeman Porosity Derating

Interfacial contact resistance $R_{\mathrm{contact}}$ decreases exponentially with clamping pressure $P_{\mathrm{clamp}}$:

$$R_{\mathrm{contact}}(P_{\mathrm{clamp}}) = R_{\mathrm{contact},0} \cdot \exp\left( -k_{\mathrm{press}} P_{\mathrm{clamp}} \right) + R_{\mathrm{min}}$$

where $R_{\mathrm{contact},0} = 4.20\mathrm{m}\Omega\cdot\mathrm{cm}^2$.

Compacted GDL porosity $\varepsilon_{\mathrm{gdl}}$ decreases under mechanical strain $\varepsilon_{\mathrm{mech}}$:

$$\varepsilon_{\mathrm{gdl}}(P_{\mathrm{clamp}}) = 1 - (1 - \varepsilon_0) \cdot \left( 1 + \frac{P_{\mathrm{clamp}}}{E_{\mathrm{gdl}}} \right)$$

Effective gas diffusivity $D_{\mathrm{eff}}$ is derated via Bruggeman's relation:

$$D_{\mathrm{eff}} = D_0 \cdot \left( \varepsilon_{\mathrm{gdl}}(P_{\mathrm{clamp}}) \right)^{1.5}$$

---

## Calibration Parameters & Variables

| Parameter / Variable | Symbol | Nominal Value | Unit | Calibration Source / DOI |
| --- | --- | --- | --- | --- |
| Initial Contact Resistance | $R_{\mathrm{contact},0}$ | $4.20$ | $\mathrm{m}\Omega\cdot\mathrm{cm}^2$ | Kleemann et al. (2021) |
| Nominal Clamping Pressure | $P_{\mathrm{clamp}}$ | $1.25$ | $\mathrm{MPa}$ | Assembly Specs |
| Uncompressed GDL Porosity | $\varepsilon_0$ | $0.78$ | — | Toray TGP-H-060 Datasheet |
| GDL Compressibility Modulus | $E_{\mathrm{gdl}}$ | $8.50$ | $\mathrm{MPa}$ | Mechanical Testing |
| Tie-rod Thread Friction | $\mu_{\mathrm{threads}}$ | $0.12$ | — | VDI 2230 Standard |

---

## Code Reference

* Python Kernel: [`physical_engine/factory_simulation/station4_stack_clamping.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station4_stack_clamping.py)
