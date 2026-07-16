"""
ThermoStateIndex — Canonical state vector field mapping.

Defines the positional indices for the factory state vector used in
gRPC StepReady messages. Both the Python physical engine and the
Java TMC must agree on this mapping.

Vector Layout (9 elements):
    [0] H2_TANK_PRESSURE_BAR   H2 supply pressure (bar)
    [1] H2_TANK_FILL_FRACTION  H2 tank fill fraction (0.0 to 1.0)
    [2] CHILLER_TEMP_K         Coolant temperature (K)
    [3] COMPRESSOR_POWER_KW    Compressor power (kW)
    [4] STACK_VOLTAGE_V        Stack voltage (V)
    [5] STACK_CURRENT_A_CM2    Stack current (A/cm^2)
    [6] STACK_TEMP_K           Stack average temperature (K)
    [7] STACK_CORE_TEMP_K      Stack core temperature (K)
    [8] STACK_SKIN_TEMP_K      Stack skin temperature (K)

Reference: doc6 §3.3
"""

import numpy as np


class ThermoStateIndex:
    """Canonical indices for the factory state vector.

    Usage::

        vec = np.zeros(ThermoStateIndex._VECTOR_LENGTH)
        vec[ThermoStateIndex.STACK_TEMP_K] = 353.15
        vec[ThermoStateIndex.H2_TANK_PRESSURE_BAR] = 30.0
        ThermoStateIndex.validate_vector(vec)
    """

    H2_TANK_PRESSURE_BAR: int = 0
    H2_TANK_FILL_FRACTION: int = 1
    CHILLER_TEMP_K: int = 2
    COMPRESSOR_POWER_KW: int = 3
    STACK_VOLTAGE_V: int = 4
    STACK_CURRENT_A_CM2: int = 5
    STACK_TEMP_K: int = 6
    STACK_CORE_TEMP_K: int = 7
    STACK_SKIN_TEMP_K: int = 8

    _VECTOR_LENGTH: int = 9

    @classmethod
    def validate_vector(cls, vec: np.ndarray) -> bool:
        """Validate that a state vector has the correct length.

        Args:
            vec: NumPy array to validate.

        Returns:
            True if valid.

        Raises:
            TypeError: If *vec* is not a NumPy array.
            ValueError: If *vec* has wrong shape.
        """
        if not isinstance(vec, np.ndarray):
            raise TypeError(f"Expected np.ndarray, got {type(vec).__name__}")
        if vec.shape != (cls._VECTOR_LENGTH,):
            raise ValueError(
                f"State vector must have shape ({cls._VECTOR_LENGTH},), "
                f"got {vec.shape}"
            )
        return True
