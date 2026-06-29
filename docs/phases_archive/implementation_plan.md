# Digital Twin Matrix Fuel Cell Factory — Implementation Plan

## Background

The project is a dual-layer co-simulation of a matrix PEMFC factory:
- **Cognitive Layer (JaCaMo/JVM):** BDI agents negotiate manufacturing tasks via CNP, structured by MoISE organizational schemas (PROSA/ADACOR/Centralized).
- **Physical Layer (Python/Numba):** High-fidelity electrochemical and thermodynamic models solve continuous-time physics via a gRPC bridge.
- **Visualization (Browser):** Real-time Canvas 2D + optional WebGL dashboard at 60fps with 15-20 Hz server updates.

### Current State

The existing codebase is a **hydrogen electrolysis plant** simulation (electrolyzer sign convention, OER/HER kinetics) with reusable BoP components (H2 tank, compressor, chiller, heat exchanger) and Numba/CoolProp optimization infrastructure. **None** of the following exist:
- PEMFC electrochemical model (subtractive sign convention)
- Factory station models (Stations 1-5)
- gRPC bridge (`.proto`, server, client)
- JaCaMo MAS layer (agents, artifacts, organizational specs)
- Visualization dashboard
- Stack thermal submodel (Yonkist/Hermite)

---

## Proposed Changes

The implementation follows the 4-phase milestone structure from doc5.

---

### Phase 1: Physical Layer Validation (CONPLETE)

This is the foundational layer — all Python code for the physics engine, independently testable without JaCaMo.

---

#### Physical Engine Core

##### [NEW] [sim_bridge.proto](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/protos/sim_bridge.proto)
Protobuf service definition per doc4 §2 + doc6 §3.1 amendments:
- `SimBridge` service: `AdvanceTime`, `RunBatchTest`, `HealthCheck`
- Messages: `TimeStep`, `StepReady`, `BatchTestRequest`, `BatchTestResponse`
- Enums: `AMRStatusEnum`, `StationStateEnum`
- New messages: `AMRState`, `StationState`, `TelemetryFrame`
- `TelemetryFrame` with all 20 fields (sequence_number through run_id)

##### [NEW] [proto_index.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/proto_index.py)
`ThermoStateIndex` constant class per doc6 §3.3:
- Indices 0-8 mapping state vector positions to named physical quantities
- `_VECTOR_LENGTH = 9` validation constant

##### [NEW] [server.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/server.py)
gRPC server daemon per doc1 §2.4, doc4 §4:
- `SimBridgeServicer` implementing `AdvanceTime`, `RunBatchTest`, `HealthCheck`
- Background `threading.Thread` for JIT warmup (`warmup_jit_kernels()`)
- `_is_ready = False` flag pattern with `HealthCheck` returning immediate status
- Global `_physics_step_lock = threading.Lock()` per doc4 §4.4
- Lock-snapshot-release-solve-reacquire pattern for `RunBatchTest` (avoids priority inversion)
- Bounded `ThreadPoolExecutor(max_workers=threads)` where `threads = max(1, os.cpu_count() // 30)` per doc4 §4.6
- `NUMBA_NUM_THREADS` injection before import per doc1 §3
- Deterministic seeding: `seed = int.from_bytes(stack_id.encode('utf-8')[:8], 'little') ^ run_id`

##### [NEW] [daemon_launcher.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/daemon_launcher.py)
Monte Carlo fan-out launcher per doc1 §3:
- `multiprocessing.get_context('spawn')` 
- `_daemon_entry(port, n_threads)` setting `os.environ['NUMBA_NUM_THREADS']` before import
- `os.sched_setaffinity()` for CPU pinning
- Ports 50051-50080 for 30 daemons

---

#### PEMFC Electrochemical Model

##### [NEW] [pemfc_model.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/pemfc_model.py)
Complete PEMFC model per doc2 §3:
- `PEMFCConstants` dataclass with `__all__` isolation:
  - `j0_orr = 1e-9`, `z_pemfc = 4`, `alpha_orr = 0.5`, `j_lim_pemfc = 2.5`, `B_conc = 0.05`
  - Runtime guard: `if PEMFCConstants.z_pemfc != 4: raise RuntimeError(...)` (survives `-O`)
- `calculate_nernst_potential(T, a_h2, a_o2)`:
  - E_ocv = 1.229 − 0.85e-3*(T−298.15) + (R*T)/(2*F) * ln(a_H2 * a_O2^0.5)
  - Explicit `if not (0.5 <= a_h2 <= 10.0): raise ValueError(...)` (no `assert`)
- `calculate_pemfc_voltage(j, T, a_h2, a_o2, R_internal, N_cells)`:
  - Subtractive convention: V = N_cells * (E_ocv − η_act − η_ohm − η_conc)
  - C¹ continuity patch at j/j_lim > 0.99 per doc2 §3.3
- `newton_raphson_solver(V_target, T, a_h2, a_o2, R_internal, N_cells)`:
  - Analytic Jacobian with singularity guards
  - `j_safe = max(j, 1e-10)` for activation
  - `np.clip(j_new, 1e-10, 0.999 * j_lim)` bracket
  - `tol = 1e-4`, `max_iter = 50`
  - Returns `SOLVER_DID_NOT_CONVERGE` failure flag on non-convergence
- All core functions decorated with `@njit(nogil=True, cache=True)`
- Vectorized batch test via `numba.prange` with 2D scratchpad pre-allocation
- Scratchpad indexed by `i % numba_threads` (NOT `get_thread_id()` — doc4 §4.2 Numba defect)

##### [NEW] [pemfc_test.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/pemfc_test.py)
Empirical convergence verification per doc5 Phase 1:
- Test Newton-Raphson at j = 2.49 A/cm² (ratio = 0.996, inside C¹ penalty region)
- Verify convergence under tol=1e-4, max_iter=50
- If fails: implement C²-continuous `tanh` smoothing + Armijo backtracking

---

#### Stack Thermal Submodel

##### [NEW] [stack_thermal_model.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/stack_thermal_model.py)
Per doc2 §4.4:
- Yonkist number validation: compute `Yo = q_gen * L² / (k * ΔT)` and verify `Yo < Bi`
- H1,1/H0,0 Hermite spatial-resolution lumped-capacitance method:
  - Separate `T_core` and `T_skin` temperatures
  - Core: `dT_core/dt = (q_gen - h_internal*(T_core - T_skin)) / C_core`
  - Skin: `dT_skin/dt = (h_internal*(T_core - T_skin) - h_ext*(T_skin - T_coolant)) / C_skin`
- Output `Q_input = h_ext * A * (T_skin - T_coolant)` feeds chiller.py
- Heat generation from ohmic + activation losses: `Q_gen = I * (η_act + η_ohm)`

---

#### BoP Component Modifications

##### [MODIFY] [h2_tank.py](file:///home/stuart/Documentos/components/storage/h2_tank.py)
- Add `self._state_lock = threading.Lock()` to `__init__`
- Wrap `fill()`, `discharge()`, `step()` in `with self._state_lock:`
- Ensure compatibility with server-level `_physics_step_lock`

##### [MODIFY] [chiller.py](file:///home/stuart/Documentos/components/thermal/chiller.py)
- Verify backward Euler formula: `T_new = (T_old + dt*(Q_input + hA*T_amb)/C) / (1 + dt*(hA/C))`
- Add `Q_input` coupling interface from stack thermal submodel
- Ensure `T_amb` reference is explicit (decay toward ambient, not absolute zero)

##### [MODIFY] [lut_manager.py](file:///home/stuart/Documentos/optimization/lut_manager.py)
- Add `fcntl.flock(LOCK_EX)` to `_generate_lut()` for 30-daemon contention safety
- Deduplicate array declarations in `__init__`

##### [MODIFY] [compressor.py](file:///home/stuart/Documentos/components/compression/compressor.py)
- Move stage calculations to `__init__()` (not deferred to `initialize()`)
- Narrow CoolProp exception handling to `(ValueError, IndexError)`
- Raise `ComponentInitializationError` on failure

---

#### Factory Simulation Infrastructure

##### [NEW] [factory_state.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/factory_state.py)
Central state manager for the physical engine:
- Pre-allocated state vector `np.zeros(ThermoStateIndex._VECTOR_LENGTH)`
- Component instances (TankArray, CompressorStorage, Chiller, StackThermalModel, PEMFCModel)
- `advance_time(dt)` method orchestrating physics integration in correct order
- State vector population at indices defined by `ThermoStateIndex`

##### [NEW] [station_stochastics.py](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station_stochastics.py)
Station 1-4 stochastic parameter definitions per doc2 §2:
- Processing time distributions (N(45,5), N(120,15), N(30,2), N(240,30))
- Defect rates (0.5%, 1.2%, 0.2%, 0.8%)
- Note: Actual stochastic sampling occurs on JVM side (doc1 §2.5) — this file provides reference constants for validation

---

### Phase 2: Core MAS Integration & RPC Bridge (JVM Side)

> [!WARNING]
> Phase 2 requires JaCaMo framework, Gradle, and Java 17+. Implementation depends on your JVM environment.

##### [NEW] [build.gradle](file:///home/stuart/Documentos/matrix_factory_twin/build.gradle)
Gradle build with JaCaMo, gRPC-Java, Netty, Protobuf plugins.

##### [NEW] [GrpcClientBridge.java](file:///home/stuart/Documentos/matrix_factory_twin/src/java/factory/GrpcClientBridge.java)
- Managed gRPC channel with bounded executor per doc4 §4.6
- `HealthCheck` polling at 500ms fixed interval per doc1 §2.4
- `AdvanceTime` synchronous call with schema_epoch embedding

##### [NEW] [MainSimulator.java](file:///home/stuart/Documentos/matrix_factory_twin/src/java/factory/MainSimulator.java)
Time Management Coordinator (TMC) per doc1 §2.3:
- NER aggregation quorum with deterministic tick-count deadline
- `dropped_NER_count` metric
- `schema_epoch` AtomicInteger
- TelemetryFrame assembly (§3.2 of doc6): volatile reads of AMR/Station state + zero-copy state_vector passthrough
- `AtomicReference<TelemetryFrameSnapshot>.set()` publish

##### [NEW] [ProtoIndex.java](file:///home/stuart/Documentos/matrix_factory_twin/src/java/factory/ProtoIndex.java)
Mirror of `proto_index.py` per doc6 §3.3 with startup validation.

##### [NEW] CArtAgO Artifacts (src/env/factory/):
- `BaseStationArtifact.java` — Station 1-4 fast-path with `SplittableRandom(seed)`, volatile `StationSummary`
- `TestBenchArtifact.java` — Station 5 async gRPC with `IBlockingCmd`/`resume()`, `ConcurrentHashMap<corrId>`, `cancelPendingRpc()`
- `AMRArtifact.java` — 4D reservation matrix, `OpFeedbackParam`, volatile `AMRSnapshot[]`, grid utilization guard
- `UtilitySystemArtifact.java` — BoP monitoring
- `DatabaseArtifact.java` — SQLite historian with `ArrayBlockingQueue<>(300_000)`, adaptive drain batching, WAL PRAGMAs, backpressure/hysteresis signals
- `TimerArtifact.java` — NER-based TTL management (no wall-clock timers)
- `EnergyPriceArtifact.java` — `updatePrice(simTime)` driven by TMC, reads `price_series.csv`
- `TelemetryArtifact.java` — Lossy observer: AtomicReference read → sim-time decimation gate → bounded queue → non-blocking WebSocket binary send → `lastPublishedSimTimeS` only on confirmed delivery

##### [NEW] Jason BDI Agents (src/ag/):
- `order_holon.asl` — CNP initiator, transport requests
- `resource_holon.asl` — CNP responder with `provisional_lock` state machine, `startTimer()`, catch-all rejection
- `amr_agent.asl` — Transport assignment, collision-free paths

##### [NEW] MoISE Specs (src/org/):
- `centralized_org.xml`, `prosa_org.xml`, `adacor_org.xml`

---

### Phase 3: Organizational Flexibility (PROSA vs. ADACOR)

- Two-phase commit protocol in supervisor agent
- Phase 0 drain with `TTL_phase0 = 15s`, `reservation_registry` abort
- Phase 1 suspend with `TTL_phase1 = 10s`, `force_commit`
- Schema epoch validation on agent resume
- EnergyPriceArtifact integration with ADACOR transitions

---

### Phase 4: Visualization Dashboard

##### [NEW] [index.html](file:///home/stuart/Documentos/matrix_factory_twin/visualization/index.html)
Dashboard structure: `<div id="factory-viewport">` with stacked canvases.

##### [NEW] [dashboard.js](file:///home/stuart/Documentos/matrix_factory_twin/visualization/dashboard.js)
Per doc6 §2:
- WebSocket binary receiver → `protobufjs` decode → `VisualStateBuffer.write()`
- `requestAnimationFrame` loop: offscreen canvas cache → station fills → AMR interpolation → KPI panel
- AMR extrapolation per §2.4 with gap-recovery rebasing
- Station state color map (§2.3): IDLE=#1B5E20, LOCK=#F57F17, BUSY=#0D47A1, DEFECT=#B71C1C, OFFLINE=#424242
- Organizational schema HUD label with 400ms color transition
- Gap detection via BigInt sequence_number arithmetic
- 500ms telemetry interruption handling (freeze, banner, dim, blank KPIs)

##### [NEW] [factory_layout.json](file:///home/stuart/Documentos/matrix_factory_twin/visualization/factory_layout.json)
Static layout per doc6 §2.2: grid 20×12, 48px cells, station bounding boxes, AMR docks, conveyor paths.

##### [NEW] [dashboard.css](file:///home/stuart/Documentos/matrix_factory_twin/visualization/dashboard.css)
Styling: dark theme, glassmorphism KPI panels, animation keyframes.

##### [NEW] [protobuf_decoder.js](file:///home/stuart/Documentos/matrix_factory_twin/visualization/protobuf_decoder.js)
Lightweight `TelemetryFrame` Protobuf decoder using `protobufjs`.

---

## Verification Plan

### Phase 1 — Automated Tests
```bash
# Newton-Raphson convergence at j=2.49 (penalty region)
python -m pytest matrix_factory_twin/physical_engine/factory_simulation/pemfc_test.py -v

# Stack thermal submodel Yonkist validation
python -m pytest matrix_factory_twin/physical_engine/factory_simulation/test_stack_thermal.py -v

# gRPC server startup + HealthCheck polling
python matrix_factory_twin/physical_engine/server.py &
python -c "import grpc; ch=grpc.insecure_channel('localhost:50051'); ..."

# State vector length validation
python -c "from physical_engine.proto_index import ThermoStateIndex; assert ThermoStateIndex._VECTOR_LENGTH == 9"
```

### Phase 2-4 — Manual Verification
- JaCaMo agent negotiation logging
- WebSocket binary frame inspection in browser DevTools
- Canvas 2D 60fps via `PerformanceObserver`
- Monte Carlo 1:30 fan-out survival test
