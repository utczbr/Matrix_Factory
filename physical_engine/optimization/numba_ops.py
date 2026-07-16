"""
numba_ops.py — public API shim for physical_engine.optimization.numba_ops.

Import priority
---------------
1. Compiled Cython extension (_numba_ops_core) — always preferred.
   When available, all functions AND constants come from the compiled binary.
2. Python fallback (_numba_ops_core_python) — dev-only, never shipped to
   clients in a hardened distribution.

Hardened distribution gate
--------------------------
If H2PLANT_HARDENED=1 is set in the environment the fallback path is
disabled entirely. A missing compiled extension raises ImportError at
startup so the problem is immediately visible.

Do not add logic here. Add it to _numba_ops_core_python.py or
_numba_ops_core.pyx.
"""

import os

_compiled: bool = False
_compiled_core_path: str | None = None

# ── Try compiled extension first ──────────────────────────────────────────
try:
    from ._numba_ops_core import *          # noqa: F401, F403
    # Python's star-import excludes names starting with '_', so import
    # the private-but-public symbols explicitly.
    from ._numba_ops_core import (          # noqa: F401
        _antoine_psat_water,
        _compute_T_out_for_P_jit,
        _integral_cp,
    )
    from . import _numba_ops_core as _core
    _compiled = True
    _compiled_core_path = getattr(_core, "__file__", None)
except ImportError:
    _core = None

# ── Fallback to Python (dev-only, not shipped to clients) ─────────────────
if not _compiled:
    _H2PLANT_HARDENED: bool = os.environ.get("H2PLANT_HARDENED") == "1"
    if _H2PLANT_HARDENED:
        raise ImportError(
            "H2PLANT_HARDENED=1 is set but the compiled _numba_ops_core "
            "extension could not be imported. Cannot fall back to the "
            "Python implementation in a hardened wheel deployment. "
            "Possible causes: (1) the .so/.pyd was not installed, "
            "(2) the wheel was built without H2PLANT_BUILD_COMPILED_CORE=1, "
            "(3) a Python version or platform mismatch."
        )
    # Developer / CI fallback
    from ._numba_ops_core_python import *   # noqa: F401, F403
    from ._numba_ops_core_python import (
        _antoine_psat_water,
        _compute_T_out_for_P_jit,
        _integral_cp,
    )
    from ._numba_ops_core_python import __all__ as _python_all  # for __all__ below
else:
    _H2PLANT_HARDENED: bool = os.environ.get("H2PLANT_HARDENED") == "1"
    _python_all = None  # not needed when compiled core loaded


# ── __all__ ───────────────────────────────────────────────────────────────
# Hardcoded — no longer sourced from _numba_ops_core_python so the shim
# works without that file in hardened distributions.
__all__ = [
    # Constants
    "GAS_CP_COEFFS",
    "GAS_MW",
    "GAS_MW_KG_MOL",
    "HENRY_H2_C",
    "HENRY_H2_H298",
    "HENRY_H2_MW",
    "HENRY_O2_C",
    "HENRY_O2_H298",
    "HENRY_O2_MW",
    "LIQ_CP_COEFFS",
    "LIQ_MW",
    # Private helpers
    "_antoine_psat_water",
    "_compute_T_out_for_P_jit",
    "_integral_cp",
    # Public functions (alphabetical)
    "apply_heat_loss_batch",
    "batch_bilinear_interp_jit",
    "batch_pressure_update",
    "batch_pressure_update_vector_T",
    "bilinear_interp_jit",
    "bilinear_interp_liquid",
    "calc_boiler_batch_full",
    "calc_boiler_batch_scenario",
    "calc_boiler_flash_jit",
    "calc_boiler_outlet_enthalpy",
    "calculate_compression_realgas_jit",
    "calculate_compression_work",
    "calculate_dissolved_gas_mg_kg_jit",
    "calculate_dynamic_u_fouled",
    "calculate_h2_production_dynamic",
    "calculate_mixture_compression_jit",
    "calculate_mixture_cp",
    "calculate_mixture_density_jit",
    "calculate_mixture_enthalpy",
    "calculate_nusselt_crossflow",
    "calculate_nusselt_dittus_boelter",
    "calculate_pem_voltage_jit",
    "calculate_reynolds_flux",
    "calculate_storage_mpc_factor",
    "calculate_stream_enthalpy_jit",
    "calculate_total_mass_by_state",
    "calculate_water_psat_jit",
    "counter_flow_ntu_effectiveness",
    "distribute_mass_and_energy",
    "distribute_mass_to_tanks",
    "dry_cooler_ntu_effectiveness",
    "eval_cubic_spline",
    "fast_composition_properties",
    "find_available_tank",
    "find_fullest_tank",
    "get_interp_weights_jit",
    "get_mix_cp_jit",
    "get_mix_density_jit",
    "get_mix_enthalpy_fast_jit",
    "get_mix_entropy_fast_jit",
    "get_mixture_enthalpy_fast",
    "interp_from_weights_jit",
    "remap_canonical_to_lut",
    "simulate_filling_timestep",
    "simulate_soec_step_jit",
    "solve_cyclone_mechanics",
    "solve_deoxo_multizone_jit",
    "solve_deoxo_pfr_step",
    "solve_dry_cooler_thermal_jit",
    "solve_interchanger_flash_jit",
    "solve_pem_j_jit",
    "solve_ph_flash_jit",
    "solve_rachford_rice_single_condensable",
    "solve_temp_limited_pressure_jit",
    "solve_temperature_from_enthalpy_jit",
    "solve_uv_flash",
    "solve_water_T_from_H_jit",
    "warmup_jit_kernels",
    # Shim-only diagnostic
    "compiled_core_status",
]


def compiled_core_status() -> dict:
    """Return diagnostic information about the compiled extension state.

    Returns a dict with keys:
      compiled (bool): True if the compiled extension loaded successfully.
      core_path (str | None): Filesystem path of the loaded .so/.pyd, or None.

    Note: this value is process-local. In multiprocessing environments,
    call this function in each worker process independently.
    """
    return {
        "compiled": _compiled,
        "core_path": _compiled_core_path,
    }
