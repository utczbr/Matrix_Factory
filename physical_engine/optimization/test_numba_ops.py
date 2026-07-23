import os
os.environ.setdefault("NUMBA_NUM_THREADS", "1")

import pytest
import numpy as np
from physical_engine.optimization._numba_ops_core_python import (
    calculate_pem_voltage_jit,
    calculate_compression_work,
)

def test_pem_voltage_jit():
    v = calculate_pem_voltage_jit(
        j=1.0, T=353.15, P_op=2.0e5, R=8.314, F=96485.0, z=2,
        alpha=0.5, j0=1e-4, j_lim=3.0, delta_mem=1.75e-4,
        sigma_base=0.1, P_ref=1.01325e5
    )
    assert isinstance(v, float)
    assert v > 1.0

def test_compression_work():
    w = calculate_compression_work(p1=1e5, p2=2e5, mass=1.0, temperature=300.0, efficiency=0.75, gamma=1.4, gas_constant=4124.0)
    assert isinstance(w, float)
    assert w > 0.0
