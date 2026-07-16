from __future__ import annotations
import threading
import numpy as np
from physical_engine.optimization.lut_manager import LUTManager

class TankArray:
    """Single-tank H2 reservoir feeding the Station 5 test bench.
    Tier 1 (LUTManager not yet ready / out of bounds): ideal gas.
    Tier 2 (default once warm): real-gas via LUTManager density inversion.
    """
    def __init__(self, lut_manager: LUTManager, capacity_kg: float = 5.0,
                 volume_m3: float = 0.5, initial_fill_fraction: float = 1.0,
                 temp_k: float = 298.15):
        self._lock = threading.Lock()
        self._lut = lut_manager
        self.capacity_kg = capacity_kg
        self.volume_m3 = volume_m3
        self.temperature_k = temp_k
        self.mass_kg = capacity_kg * initial_fill_fraction
        self.pressure_bar = self._pressure_from_mass()

    def _pressure_from_mass(self) -> float:
        rho = max(self.mass_kg, 1e-6) / self.volume_m3
        try:
            p_pa = self._lut.lookup_pressure_from_density('H2', rho, self.temperature_k)
            return p_pa / 1e5
        except Exception:
            from physical_engine.core.constants import GasConstants
            return rho * GasConstants.R_H2 * self.temperature_k / 1e5  # ideal-gas fallback

    def discharge(self, requested_kg: float) -> float:
        with self._lock:
            delivered = min(requested_kg, max(self.mass_kg, 0.0))
            self.mass_kg = np.clip(self.mass_kg - delivered, 0.0, self.capacity_kg)
            self.pressure_bar = self._pressure_from_mass()
            return float(delivered)

    def fill(self, offered_kg: float) -> float:
        with self._lock:
            accepted = min(offered_kg, max(self.capacity_kg - self.mass_kg, 0.0))
            self.mass_kg = np.clip(self.mass_kg + accepted, 0.0, self.capacity_kg)
            self.pressure_bar = self._pressure_from_mass()
            return float(accepted)

    @property
    def fill_fraction(self) -> float:
        return float(self.mass_kg / self.capacity_kg)
