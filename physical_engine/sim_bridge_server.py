"""
gRPC SimBridge Server — Physical-Layer Daemon Entry Point.

Implements the ``SimBridge`` gRPC service defined in
``protos/sim_bridge.proto``.  This server is the single entry point
for JaCaMo cognitive agents to drive the Python physical engine.

Topology (doc1 §3.2):
    1 JVM  →  30 Python daemons (via ``concurrent.futures.ThreadPoolExecutor``).
    Each daemon hosts one ``SimBridgeServicer`` instance.

Thread Safety:
    - ``_physics_step_lock``: Global ``threading.Lock`` serialising
      ``AdvanceTime`` calls.  No two ``AdvanceTime`` RPCs may execute
      concurrently.
    - ``RunBatchTest`` acquires the PEMFC model read-only and can run
      concurrently with other ``RunBatchTest`` calls (Numba prange
      handles internal parallelism).
    - Per-component ``_state_lock`` (e.g. ``TankArray._state_lock``)
      protects Numba nogil in-place mutations.

Lifecycle:
    1. ``serve()`` → create server, add ``SimBridgeServicer``, bind port.
    2. ``HealthCheck`` → clients poll until ``ready = True`` (JIT warmup).
    3. ``AdvanceTime`` → step all components, return embedded state vector.
    4. ``RunBatchTest`` → delegate to ``batch_polarization_sweep``.
    5. ``SIGTERM`` / ``SIGINT`` → graceful 5-second shutdown.

Reference: doc4 §2, doc6 §3.1
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from concurrent import futures
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread pinning — must precede ANY Numba import (doc4 §4.2)
# ---------------------------------------------------------------------------
def _derive_numba_threads() -> int:
    env_value = os.environ.get("NUMBA_NUM_THREADS")
    if env_value is not None:
        return max(1, int(env_value))

    derived = max(1, (os.cpu_count() or 1) // 30)
    os.environ["NUMBA_NUM_THREADS"] = str(derived)
    logger.warning(
        "NUMBA_NUM_THREADS was unset; defaulting to %s for standalone runs.",
        derived,
    )
    return derived


_NUMBA_THREADS = _derive_numba_threads()

# ---------------------------------------------------------------------------
# Conditional imports — proto stubs may not be compiled yet
# ---------------------------------------------------------------------------
try:
    import grpc
    GRPC_AVAILABLE = True
except ImportError:
    grpc = None  # type: ignore[assignment]
    GRPC_AVAILABLE = False

# gRPC generated stubs (will be available after protoc compilation)
_PB2_AVAILABLE = False
try:
    from physical_engine.protos import sim_bridge_pb2
    from physical_engine.protos import sim_bridge_pb2_grpc
    _PB2_AVAILABLE = True
except ImportError:
    sim_bridge_pb2 = None       # type: ignore[assignment]
    sim_bridge_pb2_grpc = None  # type: ignore[assignment]

# Physical engine components
from physical_engine.proto_index import ThermoStateIndex
from physical_engine.factory_simulation.pemfc_model import (
    calculate_pemfc_voltage,
    newton_raphson_solver,
    batch_polarization_sweep,
    PEMFCConstants,
    SOLVER_DID_NOT_CONVERGE,
)
from physical_engine.factory_simulation.stack_thermal_model import (
    StackThermalModel,
)

# ---------------------------------------------------------------------------
# Failure flags bitmask (matches BatchTestResponse.failure_flags in .proto)
# ---------------------------------------------------------------------------
OHMIC_DEGRADATION: int = 0x01          # bit 0
MASS_TRANSPORT_STARVATION: int = 0x02  # bit 1
THERMAL_SHUTDOWN: int = 0x04           # bit 2
LOW_ACTIVATION: int = 0x08            # bit 3
# SOLVER_DID_NOT_CONVERGE = 0x10       # bit 4 (imported from pemfc_model)


def derive_seed(stack_id: str, run_id: int) -> int:
    return int.from_bytes(stack_id.encode("utf-8")[:8], "little") ^ run_id

class SimBridgeServicer:
    """gRPC ``SimBridge`` service implementation.

    Encapsulates the factory's physical state and provides the three
    RPC endpoints: ``AdvanceTime``, ``RunBatchTest``, ``HealthCheck``.

    Args:
        num_cells: Number of cells in the PEMFC stack.
        R_internal: Area-specific resistance [Ω·cm²].
        T_initial: Initial stack temperature [K].
        run_id: Phase 4 instance ID.
        stack_id: Phase 4 configuration identifier.
    """

    def __init__(
        self,
        num_cells: int = 200,
        R_internal: float = 0.1,
        T_initial: float = 353.15,
        run_id: int = 0,
        stack_id: str = "S5",
    ) -> None:
        # Stack parameters
        self._num_cells = num_cells
        self._R_internal = R_internal

        # Thermal model
        self._thermal = StackThermalModel(T_initial=T_initial)

        # State vector
        self._state = np.zeros(ThermoStateIndex._VECTOR_LENGTH, dtype=np.float64)
        self._state[ThermoStateIndex.STACK_TEMP_K] = T_initial
        self._state[ThermoStateIndex.STACK_CORE_TEMP_K] = T_initial
        self._state[ThermoStateIndex.STACK_SKIN_TEMP_K] = T_initial
        self._state[ThermoStateIndex.CHILLER_TEMP_K] = 298.15
        self._state[ThermoStateIndex.H2_TANK_PRESSURE_BAR] = 3.0     # 3 bar default
        self._state[ThermoStateIndex.H2_TANK_FILL_FRACTION] = 1.0    # 100% full
        self._state[ThermoStateIndex.COMPRESSOR_POWER_KW] = 0.0

        # Concurrency
        self._physics_step_lock = threading.Lock()
        self._ready = False
        
        self._run_id = run_id
        seed = derive_seed(stack_id, run_id)
        self._rng = np.random.default_rng(seed)
        logger.info(f"[run={run_id}] seeded RNG with seed={seed} (stack_id={stack_id!r})")

        # JIT warmup
        self._warmup_jit()
        self._ready = True
        logger.info("SimBridgeServicer ready (JIT warmup complete).")

    # ------------------------------------------------------------------
    # JIT warmup
    # ------------------------------------------------------------------
    def _warmup_jit(self) -> None:
        """Force-compile all Numba kernels so first real call is fast."""
        logger.info("Warming up JIT kernels...")
        try:
            # Trigger @njit compilation
            _ = calculate_pemfc_voltage(1.0, 353.15, 1.0, 1.0, 0.1, 1)
            _ = newton_raphson_solver(0.5, 353.15, 1.0, 1.0, 0.1, 1)
            warmup_j = np.array([0.1, 0.5, 1.0], dtype=np.float64)
            _ = batch_polarization_sweep(warmup_j, 353.15, 1.0, 1.0, 0.1, 1, _NUMBA_THREADS)
            logger.info("JIT warmup complete.")
        except Exception as e:
            logger.warning(f"JIT warmup had issues (non-fatal): {e}")

    # ------------------------------------------------------------------
    # RPC: HealthCheck
    # ------------------------------------------------------------------
    def HealthCheck(self, request, context):
        """Return server readiness (JIT warmup status)."""
        return sim_bridge_pb2.HealthStatus(ready=self._ready)

    # ------------------------------------------------------------------
    # RPC: AdvanceTime
    # ------------------------------------------------------------------
    def AdvanceTime(self, request, context):
        """Advance the physical simulation by one timestep.

        Acquires ``_physics_step_lock`` to serialise time steps.

        Args:
            request: ``TimeStep`` message with current_time and dt.

        Returns:
            ``StepReady`` message with success flag and embedded state vector.
        """
        with self._physics_step_lock:
            try:
                dt = request.dt
                t = request.current_time

                # --- Stack temperature for Nernst ---
                T = self._state[ThermoStateIndex.STACK_CORE_TEMP_K]
                T_coolant = self._state[ThermoStateIndex.CHILLER_TEMP_K]

                # --- Activities from pressures ---
                # H2_TANK_PRESSURE_BAR is in bar. 1 bar = 1e5 Pa. P_ref is 1e5 Pa.
                a_h2 = np.clip(
                    self._state[ThermoStateIndex.H2_TANK_PRESSURE_BAR], 0.5, 10.0
                )
                a_o2 = 1.0  # Constant 1 bar (O2 supply from atmosphere)

                # --- Current density from state ---
                j = self._state[ThermoStateIndex.STACK_CURRENT_A_CM2]
                if j < 1e-10:
                    j = 1.0  # Default operating point

                # --- Electrochemistry ---
                V_stack, eta_act, eta_ohm, eta_conc, E_ocv = (
                    calculate_pemfc_voltage(
                        j, T, a_h2, a_o2,
                        self._R_internal, self._num_cells,
                    )
                )

                # --- Thermal model ---
                # Q_gen = I * (η_act + η_ohm)   [Watts]
                I_total = j  # A/cm² × active_area would give Amps
                Q_gen = I_total * (eta_act + eta_ohm)
                Q_output = self._thermal.step(dt, Q_gen, T_coolant)

                # --- Update state vector ---
                self._state[ThermoStateIndex.STACK_VOLTAGE_V] = V_stack
                self._state[ThermoStateIndex.STACK_CORE_TEMP_K] = self._thermal.T_core
                self._state[ThermoStateIndex.STACK_SKIN_TEMP_K] = self._thermal.T_skin
                self._state[ThermoStateIndex.STACK_TEMP_K] = (
                    0.5 * (self._thermal.T_core + self._thermal.T_skin)
                )

                return sim_bridge_pb2.StepReady(
                    target_time=t + dt,
                    success=True,
                    state_vector=self._state.tolist(),
                )

            except Exception as e:
                logger.error(f"AdvanceTime failed: {e}", exc_info=True)
                return sim_bridge_pb2.StepReady(
                    target_time=request.current_time,
                    success=False,
                    state_vector=self._state.tolist(),
                )

    # ------------------------------------------------------------------
    # RPC: RunBatchTest
    # ------------------------------------------------------------------
    def RunBatchTest(self, request, context):
        """Execute a polarization curve sweep on the PEMFC stack.

        This RPC does NOT acquire ``_physics_step_lock`` — it runs
        read-only against the PEMFC model and can execute concurrently
        with other ``RunBatchTest`` calls.

        Args:
            request: ``BatchTestRequest`` with operating conditions.

        Returns:
            ``BatchTestResponse`` with measured voltages and failure flags.
        """
        try:
            T = request.operating_temp_k or 353.15
            N_cells = request.num_cells or self._num_cells

            # Convert bar → activity
            P_ref = 1e5
            a_h2 = np.clip(request.inlet_pressure_h2_bar * 1e5 / P_ref, 0.5, 10.0)
            a_o2 = np.clip(request.inlet_pressure_o2_bar * 1e5 / P_ref, 0.5, 10.0)

            # Current densities
            if request.current_densities:
                j_values = np.array(
                    list(request.current_densities), dtype=np.float64
                )
            else:
                # Default 12-point diagnostic sweep
                j_values = np.linspace(0.05, 2.4, 12)

            # Vectorized computation
            voltages, failure_flags = batch_polarization_sweep(
                j_values, T, a_h2, a_o2,
                self._R_internal, N_cells, _NUMBA_THREADS,
            )

            # Diagnostic checks
            flags = int(failure_flags)

            # Check voltage monotonicity (mass transport starvation)
            for i in range(1, len(voltages)):
                if voltages[i] > voltages[i - 1] + 1e-6:
                    flags |= MASS_TRANSPORT_STARVATION
                    break

            return sim_bridge_pb2.BatchTestResponse(
                passed=(flags == 0),
                measured_voltages=voltages.tolist(),
                failure_flags=flags,
            )

        except Exception as e:
            logger.error(f"RunBatchTest failed: {e}", exc_info=True)
            return sim_bridge_pb2.BatchTestResponse(
                passed=False,
                measured_voltages=[],
                failure_flags=SOLVER_DID_NOT_CONVERGE,
            )


def serve(
    port: int = 50051,
    max_workers: int | None = None,
    num_cells: int = 200,
    R_internal: float = 0.1,
    T_initial: float = 353.15,
    run_id: int = 0,
) -> None:
    """Start the gRPC SimBridge server.

    Args:
        port: TCP port to bind.
        max_workers: Thread pool size for concurrent RPCs.
        num_cells: Number of cells in the PEMFC stack.
        R_internal: Area-specific resistance [Ω·cm²].
        T_initial: Initial stack temperature [K].
    """
    if not GRPC_AVAILABLE:
        logger.error("grpc package not installed.  Run: pip install grpcio")
        sys.exit(1)
    if not _PB2_AVAILABLE:
        logger.error(
            "Proto stubs not compiled.  Run: "
            "python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. "
            "physical_engine/protos/sim_bridge.proto"
        )
        sys.exit(1)

    if max_workers is None:
        max_workers = _NUMBA_THREADS or max(1, (os.cpu_count() or 1) // 30)

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers)
    )

    servicer = SimBridgeServicer(
        num_cells=num_cells,
        R_internal=R_internal,
        T_initial=T_initial,
        run_id=run_id,
    )
    sim_bridge_pb2_grpc.add_SimBridgeServicer_to_server(servicer, server)

    bind_addr = f"127.0.0.1:{port}"
    server.add_insecure_port(bind_addr)
    server.start()
    logger.info(f"SimBridge server listening on {bind_addr}")

    # Graceful shutdown on SIGTERM / SIGINT
    shutdown_event = threading.Event()

    def _signal_handler(signum, frame):
        logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    shutdown_event.wait()
    server.stop(grace=5).wait()
    logger.info("SimBridge server stopped.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--run-id", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    serve(port=args.port, run_id=args.run_id)
