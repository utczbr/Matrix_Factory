# Document 2: Physical Layer & Thermodynamic Modeling Specification

## 1. Overview **[Status: Production-Verified (Phase 1 & 2)]**

The Python-based physical layer dictates the realistic operational behavior of the matrix factory. It differentiates the deterministic planning of the cognitive agents from the harsh realities of physical manufacturing by introducing stochastic variations, mechanical limits, and thermodynamic degradation.

## 2. Stochastic Manufacturing Cells (Stations 1 to 4) **[Status: Production-Verified (Phase 1 & 2)]**

Stations 1 through 4 handle the mechanical assembly and catalytic processes of the fuel cell. They are modeled as stochastic nodes with capacity-limited buffers. Each station dictates the true execution time of a CArtAgO operation through randomized sampling of processing times and defect rates.

*   **Station 1 (MEA Preparation):** Cuts and prepares the polymer membrane.
    *   *Processing Time:* $t_{proc} \sim \mathcal{N}(45, 5)$ seconds. 
    *   *Defect Rate:* $0.5\%$.
*   **Station 2 (Catalytic Deposition):** Applies Platinum/Carbon catalyst onto the MEA.
    *   *Processing Time:* $t_{proc} \sim \mathcal{N}(120, 15)$ seconds. 
    *   *Defect Rate:* $1.2\%$.
*   **Station 3 (Bipolar Plate Stamping):** Embosses flow channels onto metallic plates.
    *   *Processing Time:* $t_{proc} \sim \mathcal{N}(30, 2)$ seconds. 
    *   *Defect Rate:* $0.2\%$.
*   **Station 4 (Robotic Stack Assembly):** Compresses and bolts MEAs, Gas Diffusion Layers (GDLs), and bipolar plates into a complete $N$-cell stack.
    *   *Processing Time:* $t_{proc} \sim \mathcal{N}(240, 30)$ seconds. 
    *   *Defect Rate:* $0.8\%$.

## 3. End-of-Line Electrochemical Test Bench (Station 5) **[Status: Production-Verified (Phase 1 & 2)]**

Station 5 is a high-fidelity model that validates the assembled stack by executing a real-time electrochemical performance test. It utilizes the mathematical model of a Proton Exchange Membrane Fuel Cell (PEMFC).

The polarization curve of a fuel cell stack with $N_{cells}$ is mathematically represented by subtracting various thermodynamic overpotentials from the theoretical Nernst potential:
$$ V_{stack}(j) = N_{cells} \cdot \left( E_{ocv} - \eta_{act} - \eta_{ohm} - \eta_{conc} \right) $$

### 3.1 Sign Convention & Kinetic Parameters (PEMFC) **[Status: Production-Verified (Phase 1 & 2)]**

> **Critical Constraint:** All overpotentials ($\eta_{act}$, $\eta_{ohm}$, $\eta_{conc}$) are *subtracted* from the open-circuit voltage. This is the standard **fuel cell** convention. The function `calculate_pemfc_voltage()` returns:
> $$ V_{cell} = E_{ocv} - \eta_{act} - \eta_{ohm} - \eta_{conc} $$

To prevent cross-contamination from legacy electrolyzer code, `calculate_pemfc_voltage()` must reside in `factory_simulation/pemfc_model.py` utilizing a module-level `__all__ = ['calculate_pemfc_voltage', 'PEMFCConstants']` isolation. A runtime guard `if PEMFCConstants.z_pemfc != 4: raise RuntimeError("PEMFC constant contamination: z_pemfc != 4")` must enforce usage of the correct parameters, surviving `-O` execution flags.

- `j0_orr = 1e-9` (Exchange current density, A/cm²)
- `z_pemfc = 4` (4-electron pathway for ORR)
- `alpha_orr = 0.5`
- `j_lim_pemfc = 2.5` (Diffusion-limited O2 transport)
- `B_conc = 0.05` (Concentration loss coefficient)

### 3.2 Electrochemical Equations **[Status: Production-Verified (Phase 1 & 2)]**

1.  **Open Circuit Voltage (Nernst Potential):**
    $$ E_{ocv} = 1.229 - 0.85 \times 10^{-3} \cdot (T - 298.15) + \frac{R \cdot T}{2 \cdot F} \ln\left( a_{H_2} \cdot a_{O_2}^{0.5} \right) $$
    
    Where $a_{H_2}$ and $a_{O_2}$ are the **dimensionless activities** ($a_x = P_x / P_{ref}$, where $P_{ref} = 101325$ Pa). Because CPython strips `assert` statements under `-O` execution flags, the implementation must use explicit validation for reactant boundaries to prevent NaN propagation:
    `if not (0.5 <= a_h2 <= 10.0): raise ValueError("H2 activity out of bounds")`
    `if not (0.5 <= a_O2 <= 10.0): raise ValueError("O2 activity out of bounds")`

2.  **Activation Overpotential ($\eta_{act}$):**
    $$ \eta_{act} = \frac{R \cdot T}{\alpha \cdot z \cdot F} \ln\left( \frac{j}{j_{0\_orr}} \right) $$

3.  **Ohmic Overpotential ($\eta_{ohm}$):**
    $$ \eta_{ohm} = j \cdot R_{internal} = j \cdot \left( \frac{\delta_{mem}}{\sigma_{mem}} + R_{contact} \right) $$

4.  **Concentration Overpotential ($\eta_{conc}$):**
    $$ \eta_{conc} = -B_{conc} \cdot \ln\left( 1 - \frac{j}{j_{lim}} \right) $$

### 3.3 Analytic Jacobian and Singularity Guards **[Status: Production-Verified (Phase 1 & 2)]**

To maximize the performance of the Newton-Raphson solver, an analytic Jacobian is used. The calculation of the Jacobian derivative must include strict numerical guards to prevent singularities at zero current and zero reactant limits.

**Activation Singularity Guard ($j \to 0$):**
The derivative of the activation overpotential requires dividing by $j$, which diverges to infinity as current approaches zero.
```python
j_safe = max(j, 1e-10)
deta_act_dj = (R * T) / (alpha_orr * z_pemfc * F * j_safe)
```

**Concentration Singularity Guard ($j \to j_{lim}$) & $C^1$ Continuity:**
The derivative sign must correctly evaluate positive: `deta_conc_dj = B_conc / (j_lim - j)`. To prevent geometric tearing, the $C^1$ derivative transition must be perfectly continuous.
```python
ratio = j / j_lim
penalty_slope = B_conc / (j_lim * 0.01)  # Strict analytical C1 continuity
if ratio <= 0.99:
    eta_conc = -B_conc * np.log(1.0 - ratio)
    deta_conc_dj = B_conc / (j_lim - j)
else:
    # Asymptotic bound: bypass logarithm, inject controlled penalty
    eta_conc = -B_conc * np.log(0.01) + penalty_slope * (ratio - 0.99)
    deta_conc_dj = penalty_slope / j_lim
```
To further guarantee stability, apply a Newton step bracket after every iteration: `j_new = np.clip(j - f/fp, 1e-10, 0.999 * j_lim)`.

**Solver Convergence Criteria:**
The Newton-Raphson solver must enforce strict termination criteria: an absolute voltage tolerance of `tol = 1e-4` and a `max_iter = 50` iteration cap. If the solver fails to converge within 50 iterations, the operation must return with the `SOLVER_DID_NOT_CONVERGE` failure flag set in the response payload. The Newton-Raphson solver's convergence at the stated operating point (j = 2.49 A/cm², i.e. ratio = 0.996) must be empirically verified under the stated `tol = 1e-4`, `max_iter = 50` termination criteria. This point lies inside the C¹-only penalty-patched region of the Jacobian; convergence is not guaranteed by the C¹ continuity alone and must be confirmed by test, not assumed from the analytic derivative design. If convergence fails or is slow, replace the piecewise-linear penalty transition with a C²-continuous bridging function (e.g., a localized `tanh` smoothing spline) and/or add a backtracking line search (Armijo rule) to the Newton step in place of the simple `np.clip` bracket.

## 4. Coupling with Auxiliary Utility Components **[Status: Production-Verified (Phase 1 & 2)]**

### 4.1 Reactant Supply & Starvation **[Status: Production-Verified (Phase 1 & 2)]**
The supply of Hydrogen and Oxygen is handled by `TankArray` (`h2_tank.py`).

> **Internal Numba In-Place Mutation Protection:** `TankArray` utilizes Numba `@njit(nogil=True)` functions that mutate internal arrays (`self.temperatures`, `self.pressures`) entirely in-place with the Python GIL released. To prevent invisible torn reads by a concurrent `RunBatchTest` thread, the entirety of `fill()`, `discharge()`, and `step()` methods must be explicitly wrapped in a `with self._state_lock:` block.
> 
> **Global `_physics_step_lock` Sequence:** The server-level `_physics_step_lock` MUST be acquired by the Python handler BEFORE dispatching any component `step()` kernels (e.g., `with _physics_step_lock: tank.step()`). The lock ensures that the entire synchronous Numba kernel execution completes before any concurrent batch test can execute.

### 4.2 Compressor Equation of State (EOS) & LUT Generation **[Status: Production-Verified (Phase 1 & 2)]**

- The system uses the **NIST Leachman et al. (2009) EOS** natively supported via `CoolProp`.
- `CompressorStorage` component stage calculations must be finalized during `__init__` rather than deferred to `initialize()`. Exception handling around CoolProp lookups must be narrowed to `(ValueError, IndexError)`, raising a `ComponentInitializationError` to prevent silent corrupted state propagation.

**LUT Generation Contention:**
Because CoolProp is not safely multithreaded for concurrent single-fluid generation calls, the LUT matrices must be pre-generated in the parent process. A POSIX advisory lock `fcntl.flock(LOCK_EX)` guards the `_generate_lut()` routine, ensuring that if 30 daemons launch simultaneously without cache, 29 will wait on the lock while 1 generates the shared payload. Additionally, duplicate array declarations (e.g., `self.stacked_H = None`) in `LUTManager.__init__` must be deduplicated to ensure initialization integrity.

### 4.3 Thermal Management & Chiller Numerical Stability **[Status: Production-Verified (Phase 1 & 2)]**
The `ThermalInertiaModel` in `chiller.py` computes temperature derivatives utilizing a lumped capacitance method: $dT/dt = Q_{net} / C_{thermal}$. The temporal integration must use the **analytical Backward Euler solution** with an explicit ambient temperature reference: 
$$T_{new} = \frac{T_{old} + dt \cdot (Q_{input} + h_A \cdot T_{amb}) / C_{thermal}}{1 + dt \cdot (h_A / C_{thermal})}$$
This provides one-line, iteration-free resolution of stiff thermal transients, ensuring the model decays toward $T_{amb}$ rather than absolute zero.

### 4.4 Stack Internal Thermal Submodel **[Status: Production-Verified (Phase 1 & 2)]**
The Station 5 stack's internal heat generation (derived from the ohmic and activation overpotentials computed in §3.2) must be resolved with a dedicated thermal submodel, not folded directly into `chiller.py`'s lumped external model. Because the stack generates heat volumetrically within its own mass, the classical Biot number ceiling (`Bi < 0.1`) for lumped-capacitance validity does not apply unconditionally; validity must instead be assessed using the **Yonkist number** — a nondimensional group derived via Buckingham-Pi analysis specifically for systems with internal heat generation, which removes the upper Biot-number bound on lumped-capacitance validity provided the Yonkist number remains below the Biot number. The stack thermal submodel should be implemented using a **spatial-resolution lumped-capacitance method (H1,1/H0,0 Hermite approximation)**, which resolves separate core and skin temperatures rather than a single averaged temperature, and is specifically validated for high-Biot, internally-heat-generating bodies. The heat output of this submodel becomes the `Q_input` term supplied to `chiller.py`, rather than `chiller.py` being the sole thermal representation of the stack.
