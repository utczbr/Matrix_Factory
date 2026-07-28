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
      ``AdvanceTime`` calls. No two ``AdvanceTime`` RPCs may execute
      concurrently, and ``RunBatchTest`` also takes it briefly (per sweep
      point) when mirroring in-progress current/voltage into ``_state`` so
      telemetry can observe a live test instead of only ever seeing 0
      before/after it.
    - ``RunBatchTest``'s actual electrochemistry computation
      (``batch_polarization_sweep``) is read-only and can run concurrently
      with other ``RunBatchTest`` calls (Numba prange handles internal
      parallelism) — only the telemetry-mirroring writes are serialised.
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
    batch_polarization_sweep_thermal,
    PEMFCConstants,
    OHMIC_DEGRADATION,
    MASS_TRANSPORT_STARVATION,
    THERMAL_SHUTDOWN,
    LOW_ACTIVATION,
    SOLVER_DID_NOT_CONVERGE,
)
from physical_engine.factory_simulation.cathode_air_bop import (
    calculate_cathode_air_flow_rate,
    calculate_compressor_power,
    calculate_net_stack_power,
)
from physical_engine.factory_simulation.stack_thermal_model import (
    StackThermalModel,
)
from physical_engine.optimization.lut_manager import LUTManager, MATRIX_FACTORY_LUT_CONFIG, real_gas_activity
from physical_engine.factory_simulation.h2_tank import TankArray
from physical_engine.factory_simulation.compressor import CompressorStage
import physical_engine.factory_simulation.microstructure as microstructure

from physical_engine.factory_simulation import station1_mea_preparation as st1
from physical_engine.factory_simulation import station2_catalyst_deposition as st2
from physical_engine.factory_simulation import station3_bipolar_plate_stamping as st3
from physical_engine.factory_simulation import station4_stack_clamping as st4


# ---------------------------------------------------------------------------
# Failure flags bitmask (matches BatchTestResponse.failure_flags in .proto).
# All flag values are imported from pemfc_model.py, which is now the single
# source of truth (see that module's docstring).
# ---------------------------------------------------------------------------


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
        
        self._lut = LUTManager(config=MATRIX_FACTORY_LUT_CONFIG)
        self._lut.initialize()
        self._tank = TankArray(self._lut, temp_k=T_initial)
        self._compressor = CompressorStage()

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
        self._step_counter = 0
        
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
        """Unary RPC endpoint for synchronized time stepping."""
        with self._physics_step_lock:
            try:
                dt = request.dt
                t = request.current_time

                # --- Stack temperature for Nernst ---
                T = self._state[ThermoStateIndex.STACK_CORE_TEMP_K]
                T_coolant = self._state[ThermoStateIndex.CHILLER_TEMP_K]

                # --- Activities from pressures & real-gas fugacity ---
                # --- Cathode Air BOP Subsystem (R7) ---
                j_curr = self._state[ThermoStateIndex.STACK_CURRENT_A_CM2]
                m_dot_air = calculate_cathode_air_flow_rate(j_curr * 300.0, self._num_cells, lambda_air=2.0)
                W_comp = calculate_compressor_power(m_dot_air, P_in_pa=101325.0, P_out_pa=202650.0)
                a_o2 = float(np.clip(1.0 + (m_dot_air * 10.0), 0.5, 10.0))

                # --- Current density from state ---
                j = self._state[ThermoStateIndex.STACK_CURRENT_A_CM2]
                if j < 1e-10:
                    j = 0.0  # Default operating point
                    self._state[ThermoStateIndex.STACK_CURRENT_A_CM2] = j

                # --- Electrochemistry ---
                a_h2 = float(np.clip(self._state[ThermoStateIndex.H2_TANK_PRESSURE_BAR], 0.5, 10.0))
                V_stack, eta_act, eta_ohm, eta_conc, E_ocv = (
                    calculate_pemfc_voltage(
                        j, T, a_h2, a_o2,
                        self._R_internal, self._num_cells,
                        ecsa_ratio=1.0, lambda_mem=14.0,
                    )
                )

                # --- Thermal model ---
                # Q_gen = I * (η_act + η_ohm)   [Watts]
                I_total = j  # A/cm² × active_area would give Amps
                Q_gen = I_total * (eta_act + eta_ohm)
                
                # Test Bench Heater: maintain 80°C (353.15 K) standby temperature
                if T < 353.15:
                    Q_heater = min(5000.0, (353.15 - T) * 1000.0)
                    Q_gen += Q_heater

                Q_output = self._thermal.step(dt, Q_gen, T_coolant)
                self._state[ThermoStateIndex.STACK_CORE_TEMP_K] = self._thermal.T_core
                self._state[ThermoStateIndex.STACK_SKIN_TEMP_K] = self._thermal.T_skin
                self._state[ThermoStateIndex.STACK_TEMP_K] = self._thermal.T_core
                self._state[ThermoStateIndex.COMPRESSOR_POWER_KW] = W_comp / 1000.0

                self._step_counter += 1

                return sim_bridge_pb2.StepReady(
                    target_time=t + dt,
                    success=True,
                    state_vector=list(self._state),
                )

            except Exception as exc:
                logger.error("AdvanceTime error at t=%.2f: %s", request.current_time, exc, exc_info=True)
                return sim_bridge_pb2.StepReady(
                    target_time=request.current_time,
                    success=False,
                    state_vector=list(self._state),
                )

    # ------------------------------------------------------------------
    # RPC: RunBatchTest
    # ------------------------------------------------------------------
    def RunBatchTest(self, request, context):
        """Execute a polarization curve sweep on the PEMFC stack.

        The polarization sweep itself (``batch_polarization_sweep``) is
        computed read-only and does not touch ``_physics_step_lock`` - it
        can run concurrently with other ``RunBatchTest`` calls. Only the
        brief per-point telemetry-visibility writes below (mirroring the
        in-progress current/voltage into ``_state`` for ``AdvanceTime`` to
        observe) take the lock, and only for the instant of each write.

        Args:
            request: ``BatchTestRequest`` with operating conditions.

        Returns:
            ``BatchTestResponse`` with measured voltages and failure flags.
        """
        try:
            T = request.operating_temp_k or 353.15
            N_cells = request.num_cells or self._num_cells

            # Convert bar → real-gas fugacity activity (with anode RH subtraction)
            P_ref = 1e5
            rh_anode = getattr(request, "rh_anode", 0.0)
            a_h2_raw, _ = real_gas_activity(
                request.inlet_pressure_h2_bar * P_ref, T, fluid="H2", rh=rh_anode, lut_manager=self._lut
            )
            a_o2_raw, _ = real_gas_activity(
                request.inlet_pressure_o2_bar * P_ref, T, fluid="O2", rh=0.0, lut_manager=self._lut
            )
            a_h2 = float(np.clip(a_h2_raw, 0.5, 10.0))
            a_o2 = float(np.clip(a_o2_raw, 0.5, 10.0))

            # --- Manufacturing-quality bridge -----------------------------
            r_internal_penalty = max(0.0, request.r_internal_penalty_ohm_cm2)
            derate = float(np.clip(request.activity_derate_fraction, 0.0, 0.95))

            # Clamping pressure & GDL contact resistance (R1 Milestone 2)
            p_clamp_mpa = getattr(request, "p_clamp_mpa", 4.25)
            if p_clamp_mpa <= 0.0:
                p_clamp_mpa = 4.25
            gdl_porosity = getattr(request, "gdl_porosity", 0.78)
            if gdl_porosity <= 0.0:
                gdl_porosity = 0.78
            r_contact = microstructure.compute_contact_resistance(p_clamp_mpa, gdl_porosity)

            R_internal_effective = self._R_internal + r_internal_penalty + r_contact
            a_h2 = np.clip(a_h2 * (1.0 - derate), 0.5, 10.0)
            a_o2 = np.clip(a_o2 * (1.0 - derate), 0.5, 10.0)

            j_lim_derate = float(np.clip(getattr(request, "j_lim_derate_fraction", 0.0), 0.0, 0.90))
            j_lim_effective = max(0.2, 2.5 * (1.0 - j_lim_derate))

            if r_internal_penalty > 0.0 or derate > 0.0 or abs(p_clamp_mpa - 4.25) > 0.1 or j_lim_derate > 0.0:
                logger.info(
                    "RunBatchTest stack_id=%s quality penalty applied: "
                    "R_internal %.4f -> %.4f Ohm*cm^2 (+%.4f penalty, +%.4f R_contact), activity derate=%.3f, j_lim=%.3f",
                    request.stack_id, self._R_internal, R_internal_effective,
                    r_internal_penalty, r_contact, derate, j_lim_effective,
                )

            # Current densities
            if request.current_densities:
                j_values = np.array(
                    list(request.current_densities), dtype=np.float64
                )
            else:
                # Default 12-point diagnostic sweep
                j_values = np.linspace(0.05, min(2.4, 0.95 * j_lim_effective), 12)

            ecsa_ratio = getattr(request, "ecsa_ratio", 1.0)
            if ecsa_ratio <= 0.0:
                ecsa_ratio = 1.0

            lambda_mem = getattr(request, "lambda_mem", 14.0)
            if lambda_mem <= 0.0:
                lambda_mem = 14.0

            T_coolant = self._state[ThermoStateIndex.CHILLER_TEMP_K]
            T_init = self._thermal.T_core

            # Vectorized electro-thermal coupled polarization sweep
            voltages, failure_flags, T_core_arr, T_skin_arr = batch_polarization_sweep_thermal(
                j_values, T_init, a_h2, a_o2,
                R_internal_effective, N_cells,
                ecsa_ratio=ecsa_ratio,
                lambda_mem=lambda_mem,
                dt=0.5,
                C_core=self._thermal.C_core,
                C_skin=self._thermal.C_skin,
                hA_int=self._thermal.hA_internal,
                hA_ext=self._thermal.hA_external,
                T_coolant=T_coolant,
                j_lim=j_lim_effective,
            )

            # Update thermal model state to post-sweep thermal condition
            self._thermal.T_core = T_core_arr[-1]
            self._thermal.T_skin = T_skin_arr[-1]

            # Exact Yonkist stability validation check at peak sweep overpotential
            j_max = float(np.max(j_values))
            _, eta_act_max, eta_ohm_max, *_ = calculate_pemfc_voltage(
                j_max, T_core_arr[-1], a_h2, a_o2, R_internal_effective, N_cells, ecsa_ratio, lambda_mem
            )
            Q_gen_max = (j_max * N_cells) * (eta_act_max + eta_ohm_max)
            vol_stack_m3 = self._thermal.A_external * self._thermal.L_char
            Yo, Bi, is_yonkist_valid = self._thermal.validate_yonkist(
                Q_gen_max / vol_stack_m3,
                max(0.1, abs(T_core_arr[-1] - T_skin_arr[-1]))
            )
            if not is_yonkist_valid:
                logger.warning("RunBatchTest Yonkist criterion invalidated: Yo=%.4f Bi=%.4f", Yo, Bi)

            # Pacing loop to stream telemetry during diagnostic sweep
            for j_val, v_val, t_core_val, t_skin_val in zip(j_values, voltages, T_core_arr, T_skin_arr):
                m_dot_air = calculate_cathode_air_flow_rate(j_val * 300.0, N_cells, lambda_air=2.0)
                W_comp = calculate_compressor_power(m_dot_air, P_in_pa=101325.0, P_out_pa=202650.0)

                with self._physics_step_lock:
                    self._state[ThermoStateIndex.STACK_CURRENT_A_CM2] = j_val
                    self._state[ThermoStateIndex.STACK_VOLTAGE_V] = v_val
                    self._state[ThermoStateIndex.STACK_CORE_TEMP_K] = t_core_val
                    self._state[ThermoStateIndex.STACK_SKIN_TEMP_K] = t_skin_val
                    self._state[ThermoStateIndex.STACK_TEMP_K] = 0.5 * (t_core_val + t_skin_val)
                time.sleep(0.5)
            with self._physics_step_lock:
                self._state[ThermoStateIndex.STACK_CURRENT_A_CM2] = 0.0

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

    def SimulateStationProcess(self, request, context=None):
        if not _PB2_AVAILABLE:
            raise RuntimeError("Proto stubs not compiled.")
        kind = request.WhichOneof("params")
        if request.station_id == "S1" and kind == "station1":
            p = request.station1
            t_press = p.t_press_k if p.HasField("t_press_k") else st1.T_PRESS_NOMINAL_K
            dwell_time = p.dwell_time_s if p.HasField("dwell_time_s") else st1.DWELL_TIME_NOMINAL_S
            proc_time_s, is_def, var_ratio, alpha, delam, pinhole = st1.simulate_stage1_mea_prep_safe(
                t_press,
                dwell_time,
                request.k_time or st1.K_TIME_ACCELERATED,
            )
            return sim_bridge_pb2.StationProcessResponse(
                proc_time_s=proc_time_s, is_defective=is_def, var_ratio=var_ratio,
                alpha_final=alpha, delamination_risk=delam, pinhole_risk=pinhole,
            )
        if request.station_id == "S2" and kind == "station2":
            p = request.station2
            v_coat = p.v_coat_m_s if p.HasField("v_coat_m_s") else st2.V_COAT_NOMINAL_M_S
            mu_slurry = p.mu_slurry_pa_s if p.HasField("mu_slurry_pa_s") else st2.MU_SLURRY_NOMINAL_PA_S
            proc_time_s, is_def, var_ratio, ecsa = st2.simulate_stage2_catalyst_deposition_safe(
                v_coat,
                mu_slurry,
                request.k_time or st2.K_TIME_ACCELERATED,
            )
            return sim_bridge_pb2.StationProcessResponse(
                proc_time_s=proc_time_s, is_defective=is_def, var_ratio=var_ratio, ecsa_ratio=ecsa,
            )
        if request.station_id == "S3" and kind == "station3":
            p = request.station3
            press_force = p.press_force_kn if p.HasField("press_force_kn") else st3.F_NOM_S3
            die_stroke = p.die_stroke_count if p.HasField("die_stroke_count") else 0
            w0 = p.w0_initial_wear if p.HasField("w0_initial_wear") else 0.0
            use_duplex = p.use_duplex_coating if p.HasField("use_duplex_coating") else False
            proc_time_s, is_def, var_ratio, damage = st3.simulate_stage1_stamping_safe(
                press_force, die_stroke, w0, use_duplex, request.k_time or st3.K_TIME_ACCELERATED,
            )
            return sim_bridge_pb2.StationProcessResponse(
                proc_time_s=proc_time_s, is_defective=is_def, var_ratio=var_ratio, damage_index=damage,
            )
        if request.station_id == "S4" and kind == "station4":
            p = request.station4
            torques = list(p.applied_torques_nm) if len(p.applied_torques_nm) == 4 else [st4.TORQUE_NOMINAL_NM] * 4
            frictions = list(p.friction_coefficients) if len(p.friction_coefficients) == 8 else [0.15] * 8
            proc_time_s, is_def, var_ratio, porosity, e_tan, p_clamp = st4.simulate_stage2_clamping_safe(
                torques, frictions, True, request.k_time or st4.K_TIME_ACCELERATED,
            )
            return sim_bridge_pb2.StationProcessResponse(
                proc_time_s=proc_time_s, is_defective=is_def, var_ratio=var_ratio,
                gdl_porosity=porosity, e_tangent_mpa=e_tan, p_clamp_mpa=p_clamp,
            )
        msg = f"unsupported station_id/params combination: {request.station_id}/{kind}"
        if context is not None:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, msg)
        else:
            raise ValueError(msg)


def serve(

    port: int = 50051,
    max_workers: int | None = None,
    num_cells: int = 200,
    R_internal: float = 0.06,
    T_initial: float = 353.15,
    run_id: int = 0,
) -> None:
    """Start the gRPC SimBridge server.

    Args:
        port: TCP port to bind.
        max_workers: Thread pool size for concurrent RPCs.
        num_cells: Number of cells in the PEMFC stack.
        R_internal: Area-specific resistance [Ohm*cm^2] (default 0.06).
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
        # BUG FIX: this used to default to `_NUMBA_THREADS`, which is the
        # per-daemon Numba *compute* thread count (usually 1 in the
        # standard 30-daemon Phase-4 topology — see daemon_launcher.py,
        # `num_threads = max(1, total_cores // run_count)`). Reusing that
        # value for the gRPC server's ThreadPoolExecutor meant the server
        # could only service ONE RPC at a time. RunBatchTest holds its
        # worker thread for several seconds (12-point sweep, 0.5s/point);
        # with max_workers=1, AdvanceTime queued behind it and could never
        # execute until RunBatchTest returned — so the tick loop never
        # observed a non-zero STACK_CURRENT_A_CM2 mid-sweep, and telemetry
        # always showed 0.000 A/cm² by the time it could run again.
        #
        # gRPC RPC-concurrency and Numba compute-parallelism are unrelated
        # knobs: keep at least 2 gRPC workers (headroom for AdvanceTime +
        # one in-flight RunBatchTest) independent of _NUMBA_THREADS.
        max_workers = max(2, _NUMBA_THREADS + 1)

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
    secure_mode = os.environ.get("GRPC_SECURE_MODE", "false").lower() == "true"
    if secure_mode:
        cert_dir = os.environ.get("GRPC_CERT_DIR", "certs")
        ca_cert_path = os.path.join(cert_dir, "ca.crt")
        server_cert_path = os.path.join(cert_dir, "server.crt")
        server_key_path = os.path.join(cert_dir, "server.key")

        with open(ca_cert_path, "rb") as f:
            ca_cert = f.read()
        with open(server_cert_path, "rb") as f:
            server_cert = f.read()
        with open(server_key_path, "rb") as f:
            server_key = f.read()

        server_credentials = grpc.ssl_server_credentials(
            [(server_key, server_cert)],
            root_certificates=ca_cert,
            require_client_auth=True,
        )
        server.add_secure_port(bind_addr, server_credentials)
        logger.info(f"SimBridge server listening on {bind_addr} with mTLS (secure mode)")
    else:
        server.add_insecure_port(bind_addr)
        logger.info(f"SimBridge server listening on {bind_addr} (insecure mode)")

    server.start()

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
