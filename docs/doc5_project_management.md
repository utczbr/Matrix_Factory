# Document 5: Project Management & Verification Milestones

## 1. Phase Milestones

### Phase 1: Physical Layer Validation **[COMPLETED]**
**Goal:** Verify the thermodynamics, stochastics, and Numba JIT logic independently of the MAS.
*(See Appendix for Verification Log)*

### Phase 2: Core MAS Integration & RPC Bridge **[COMPLETED]**
**Goal:** Integrate JaCaMo agents via the gRPC CArtAgO artifact.
*(See Appendix for Verification Log)*

### Phase 3: Organizational Flexibility (PROSA vs. ADACOR)
**Goal:** Prove the hybrid architecture shifts states cleanly.
*   **Success Criteria:**
    *   The `TimerArtifact` and `EnergyPriceArtifact` manage TTLs and updates strictly using the simulation clock (via TAG events and NER), eliminating wall-clock divergence.
    *   ADACOR transitions successfully freeze all intentions and transition the MoISE schema securely.
    *   Phase 0 transitions enforce a two-party abort mechanism utilizing the `reservation_registry` to free `provisional_lock` states across Resource and Order Holons simultaneously.
    *   Agents successfully detect schema modifications via the `schema_epoch` validation during `AdvanceTime` resynchronizations.

### Phase 4: Production Scale (Monte Carlo Simulation)
**Goal:** Complete thirty full Monte Carlo evaluations over 39 days without crashing.
*   **Success Criteria:**
    *   Numba runtime memory allocation inside `prange` loops is strictly forbidden to prevent NRT heap contention, requiring pre-allocated 2D scratchpad views.
    *   The `DatabaseArtifact` sustains burst telemetry during ADACOR transitions using a 300,000-record bounded queue with adaptive drain-to-occupancy micro-batching.
    *   SQLite PRAGMAs (`WAL`, `wal_autocheckpoint=100`, `synchronous=NORMAL`) prevent OOM signal buffer leaks and disk I/O lockups.
    *   Deployment successfully scales to a 1:30 (Single-JVM to 30 Python Daemons) topology, surviving CPU contention via explicit `taskset` JVM core pinning.
    *   Daemon thread limits are dynamically injected via `os.environ` before import using `multiprocessing.get_context('spawn')`, enforcing `threads = max(1, os.cpu_count() // 30)`.
    *   Both the JVM gRPC client and each Python daemon's gRPC server use an explicitly bounded executor; no component relies on gRPC's default cached thread pool under the 30-daemon fan-out.
    *   No `@njit` kernel combines `cache=True` with `get_thread_id()` under `parallel=True`; scratchpad indexing uses a deterministic `i % numba_threads` derivation instead.

## 2. Risk Management & Vulnerabilities

| Risk Description | Severity | Mitigation Strategy | Status |
| :--- | :--- | :--- | :--- |
| **Silent JIT Data Races** | Critical | Numba `@njit(nogil=True)` functions that mutate instance state arrays in-place silently bypass Python GIL locking. The overarching Python-level `with _physics_step_lock:` MUST wrap the Numba dispatch explicitly. | **Mitigated (Phase 1)** |
| **BDI Inference Overload** | High | Unbounded history querying in JaCaMo drastically slows cycle time. Historical telemetry is piped through the `DatabaseArtifact` with active `database_backpressure` and hysteresis mechanisms to throttle agents dynamically. | **Mitigated (Phase 2)** |
| **Incomplete Preemption** | High | Missing `cancelPendingRpc()` implementations strand Jason agents waiting on dead `CompletableFuture`s. The `TestBenchArtifact` must explicitly trap `RuntimeException` during cancellation to generate semantic failure signals. | **Mitigated (Phase 2)** |

## Appendix: Verification Log

### Phase 1 Verification Records
*   `AdvanceTime` correctly tracks numerical state and returns embedded state vectors synchronously.
*   `NUMBA_NUM_THREADS` is successfully constrained via `multiprocessing.Process(env={})` dict injection.
*   Newton-Raphson solver convergence at the stated operating point (j = 2.49 A/cm², ratio = 0.996) is empirically verified under `tol = 1e-4`, `max_iter = 50`.
*   `LUTManager` pre-generates caches cleanly avoiding race conditions via `fcntl.flock(LOCK_EX)` advisory locking.
*   The Station 5 stack internal-heat thermal submodel (Yonkist-number-validated, H1,1/H0,0 Hermite-resolved core/skin temperatures) is implemented and its output correctly feeds `chiller.py`'s external `Q_input` coupling.

### Phase 2 Verification Records
*   Python `server.py` daemon bootstraps deterministically using the background warmup thread.
*   The JVM `HealthCheck` polling loop receives immediate responses.
*   CArtAgO artifacts utilize explicit `resume()` signaling from Netty NIO callbacks to achieve sub-millisecond thread wakeup, completely bypassing the legacy polling loop.
*   `TestBenchArtifact` prevents orphaned streams across concurrent executions using correlation UUIDs.
*   The `TelemetryArtifact` decimates state vectors into a bounded queue (dropping on overflow), advances its decimation timestamp only on confirmed WebSocket delivery (not on queue-offer), and transmits telemetry to the dashboard using binary Protobuf over WebSockets, guaranteeing zero additional read-locks against the Python daemon. A `dropped_telemetry_frame_count` metric is exposed for observability.
*   The Time Management Coordinator (TMC) strictly enforces deterministic NER quorum/ACK synchronization to advance the clock, completely replacing wall-clock 50ms deadlines.
