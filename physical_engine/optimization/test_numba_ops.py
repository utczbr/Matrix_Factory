import pytest
import numpy as np
from physical_engine.optimization._numba_ops_core_python import (
    calculate_nernst_voltage,
    calculate_activation_overpotential,
    calculate_ohmic_overpotential,
    calculate_concentration_overpotential,
)
try:
    from physical_engine.optimization._numba_ops_core import (
        calculate_nernst_voltage as cy_nernst,
        calculate_activation_overpotential as cy_act,
        calculate_ohmic_overpotential as cy_ohm,
        calculate_concentration_overpotential as cy_conc,
    )
except ImportError:
    cy_nernst = None

@pytest.mark.skipif(cy_nernst is None, reason="Cython module not built")
def test_cython_python_parity():
    # Test cases
    T = 353.15
    a_h2 = 3.0
    a_o2 = 1.0
    j = 1.0
    
    assert np.isclose(calculate_nernst_voltage(T, a_h2, a_o2), cy_nernst(T, a_h2, a_o2))
    assert np.isclose(calculate_activation_overpotential(j, T), cy_act(j, T))
    assert np.isclose(calculate_ohmic_overpotential(j, T), cy_ohm(j, T))
    assert np.isclose(calculate_concentration_overpotential(j, T), cy_conc(j, T))

