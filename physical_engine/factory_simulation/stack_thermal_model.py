"""
Stack Thermal Submodel — Yonkist-Validated Hermite H1,1/H0,0.

Resolves the internal heat generation of a PEMFC stack using a
spatial-resolution lumped-capacitance method that tracks separate
**core** and **skin** temperatures (H1,1/H0,0 Hermite approximation).

Why not a single lumped temperature?
    The classical Biot ceiling (Bi < 0.1) for single-node lumped models
    does not hold when heat is generated *volumetrically* inside the
    body.  Validity is instead assessed using the **Yonkist number**
    (Yo = q_gen·L²/(k·ΔT)), which removes the upper Bi bound provided
    Yo < Bi.

Coupling:
    - Input:  ``Q_gen = I × (η_act + η_ohm)``  from ``pemfc_model.py``
    - Output: ``Q_output = h_ext·A·(T_skin − T_coolant)``  → ``chiller.py``

Reference: doc2 §4.4, doc5 Phase 1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class StackThermalModel:
    """Dual-temperature lumped-capacitance stack thermal model.

    Tracks ``T_core`` (stack interior) and ``T_skin`` (stack surface)
    separately using a forward-Euler integration of the coupled ODEs:

    .. math::

        \\frac{dT_{core}}{dt} = \\frac{Q_{gen} - hA_{int}(T_{core} - T_{skin})}{C_{core}}

        \\frac{dT_{skin}}{dt} = \\frac{hA_{int}(T_{core} - T_{skin}) - hA_{ext}(T_{skin} - T_{cool})}{C_{skin}}

    Args:
        mass_core_kg: Core thermal mass [kg].
        mass_skin_kg: Skin thermal mass [kg].
        cp_core: Core specific heat [J/(kg·K)].
        cp_skin: Skin specific heat [J/(kg·K)].
        h_internal: Internal (core→skin) heat transfer coefficient [W/(m²·K)].
        h_external: External (skin→coolant) heat transfer coefficient [W/(m²·K)].
        A_internal: Internal interface area [m²].
        A_external: External cooling surface area [m²].
        k_stack: Stack thermal conductivity [W/(m·K)].
        L_char: Characteristic length for Yonkist/Biot calculation [m].
        T_initial: Initial temperature for both core and skin [K].
    """

    # Thermal masses
    mass_core_kg: float = 25.0
    mass_skin_kg: float = 25.0
    cp_core: float = 500.0       # J/(kg·K)  — stainless steel approximate
    cp_skin: float = 500.0       # J/(kg·K)

    # Heat transfer coefficients
    h_internal: float = 500.0    # W/(m²·K)  core-to-skin
    h_external: float = 25.0     # W/(m²·K)  skin-to-coolant

    # Surface areas
    A_internal: float = 1.0      # m²
    A_external: float = 2.0      # m²

    # Conductivity and geometry (for Yonkist/Biot)
    k_stack: float = 20.0        # W/(m·K)
    L_char: float = 0.05         # m

    # Initial temperature
    T_initial: float = 298.15    # K

    # --- Derived state (set in __post_init__) ---
    C_core: float = field(init=False)
    C_skin: float = field(init=False)
    hA_internal: float = field(init=False)
    hA_external: float = field(init=False)
    T_core: float = field(init=False)
    T_skin: float = field(init=False)

    # Last-computed diagnostics
    _last_Yo: float = field(init=False, default=0.0)
    _last_Bi: float = field(init=False, default=0.0)
    _last_valid: bool = field(init=False, default=True)
    _last_Q_output: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        """Compute derived thermal capacitances and conductances."""
        self.C_core = self.mass_core_kg * self.cp_core        # J/K
        self.C_skin = self.mass_skin_kg * self.cp_skin        # J/K
        self.hA_internal = self.h_internal * self.A_internal   # W/K
        self.hA_external = self.h_external * self.A_external   # W/K
        self.T_core = self.T_initial
        self.T_skin = self.T_initial

        logger.info(
            f"StackThermalModel: C_core={self.C_core:.0f} J/K, "
            f"C_skin={self.C_skin:.0f} J/K, "
            f"hA_int={self.hA_internal:.0f} W/K, "
            f"hA_ext={self.hA_external:.0f} W/K"
        )

    def validate_yonkist(
        self, q_gen_volumetric: float, delta_T: float
    ) -> tuple:
        """Validate lumped-capacitance applicability via the Yonkist number.

        The Yonkist number (Yo) is a dimensionless group derived via
        Buckingham-Pi for systems with internal heat generation:

        .. math::

            Yo = \\frac{q_{gen} \\, L^2}{k \\, \\Delta T}

        Lumped-capacitance is valid when ``Yo < Bi``.

        Args:
            q_gen_volumetric: Volumetric heat generation rate [W/m³].
            delta_T: Temperature difference driving heat removal [K].

        Returns:
            Tuple ``(Yo, Bi, is_valid)`` where *is_valid* is True when
            the Yonkist criterion is satisfied.
        """
        Bi = self.h_external * self.L_char / self.k_stack

        if delta_T > 1e-6:
            Yo = q_gen_volumetric * self.L_char ** 2 / (self.k_stack * delta_T)
        else:
            Yo = 0.0

        is_valid = Yo < Bi or Yo == 0.0

        if not is_valid:
            logger.warning(
                f"Yonkist criterion violated: Yo={Yo:.4f} >= Bi={Bi:.4f}. "
                f"Lumped-capacitance assumption may be inaccurate."
            )

        return (Yo, Bi, is_valid)

    def step(self, dt: float, Q_gen: float, T_coolant: float) -> float:
        """Advance the thermal model by one timestep.

        Args:
            dt: Timestep [seconds].
            Q_gen: Total heat generated by PEMFC losses [W].
                   Typically ``I × (η_act + η_ohm)``.
            T_coolant: Coolant temperature from chiller [K].

        Returns:
            Q_output [W] — heat transferred from skin to coolant.
            This value feeds the chiller's ``Q_input`` coupling.
        """
        # --- Coupled ODE integration (forward Euler) ---
        dT_core_dt = (
            Q_gen - self.hA_internal * (self.T_core - self.T_skin)
        ) / self.C_core

        dT_skin_dt = (
            self.hA_internal * (self.T_core - self.T_skin)
            - self.hA_external * (self.T_skin - T_coolant)
        ) / self.C_skin

        self.T_core += dt * dT_core_dt
        self.T_skin += dt * dT_skin_dt

        # --- Yonkist validation ---
        # Volume approximation: A_external × L_char
        # L_char is standardly defined as V / A_external for lumped capacitance
        volume = self.A_external * self.L_char
        q_gen_volumetric = Q_gen / volume if volume > 0 else 0.0
        delta_T = max(self.T_core - T_coolant, 1e-6)

        Yo, Bi, is_valid = self.validate_yonkist(q_gen_volumetric, delta_T)
        self._last_Yo = Yo
        self._last_Bi = Bi
        self._last_valid = is_valid

        # --- Output heat to chiller ---
        Q_output = self.hA_external * (self.T_skin - T_coolant)
        self._last_Q_output = Q_output

        return Q_output

    def get_state(self) -> Dict[str, Any]:
        """Return the current thermal state.

        Returns:
            Dictionary with core/skin temperatures, heat output,
            and Yonkist diagnostics.
        """
        return {
            "T_core_K": self.T_core,
            "T_skin_K": self.T_skin,
            "Q_output_W": self._last_Q_output,
            "Yonkist_number": self._last_Yo,
            "Biot_number": self._last_Bi,
            "yonkist_valid": self._last_valid,
        }

    def reset(self) -> None:
        """Reset temperatures to initial conditions."""
        self.T_core = self.T_initial
        self.T_skin = self.T_initial
        self._last_Yo = 0.0
        self._last_Bi = 0.0
        self._last_valid = True
        self._last_Q_output = 0.0
