# Document 1: System Architecture & Integration Strategy

## 1. System Overview **[Status: Production-Verified (Phase 1 & 2)]**

The **Digital Twin of a Matrix Fuel Cell Factory** employs a distinct, dual-layer architecture designed to satisfy two mutually exclusive computational requirements: high-level cognitive reasoning and low-level, high-performance physical simulation.

1. **The Cognitive & Organizational Layer (JaCaMo - JVM):** This layer is responsible for the decentralized logic of the factory. It hosts the intelligent agents (Jason), manages the interaction environment and operational tools (CArtAgO), and enforces structural and functional rules (MoISE). It is highly abstract and event-driven.
2. **The Physical Layer (Python):** This layer is the mathematical engine of the digital twin. It resolves complex thermodynamic states, executes vector math using NumPy, performs JIT compilation via Numba for speed, and uses CoolProp for real-gas property lookups.

## 2. Integration Strategy: Asynchronous gRPC Co-Simulation Bridge **[Status: Production-Verified (Phase 1 & 2)]**

The core architectural challenge is seamlessly coupling the event-driven Java environment with the continuous-time Python physics engine.

### Why gRPC over Process Spawning?
Traditional co-simulation architectures often rely on the primary framework (e.g., Java) spawning Python subprocesses via the shell for each calculation step. In a continuous simulation with millisecond-level ticks, the overhead of JVM-to-OS process spawning, context switching, and script initialization introduces unacceptable latency, destroying real-time performance capabilities.

Instead, this architecture utilizes an **asynchronous gRPC-based physical co-simulation bridge** operating over a local TCP socket.
- A persistent Python background daemon hosts the physical models in memory, pre-warming Numba JIT kernels upon startup.
- The CArtAgO artifacts act as **non-blocking** gRPC client stubs (using the low-level `ClientCall` API and `CompletableFuture`), decoupling the JVM execution thread from RPC network latency.
- Interaction between the cognitive and physical layers occurs via highly optimized Protobuf binary serialization with packed repeated fields and Arena allocation.

### 2.1 Asynchronous Artifact Suspension Protocol **[Status: Production-Verified (Phase 1 & 2)]**

To decouple the JVM execution thread from RPC latency, the CArtAgO artifacts employ the `IBlockingCmd` interface combined with the `await()` suspension primitive. To eliminate the 10–50ms overhead associated with CArtAgO's default passive polling loop, the architecture utilizes explicit signaling:

1. **Request Dispatch:** When an `@OPERATION` is initiated, the artifact submits the gRPC network request to the Netty NIO event loop. A unique `callId` correlates the execution.
2. **Thread Suspension:** Immediately after dispatch, the artifact suspends the current operation with a strict timeout via `await(callId, 30_000L)`. The 30-second deadline acts as a watchdog, preventing indefinite suspension and JVM stalling if the Python daemon crashes or drops TCP RST frames.
3. **Active Wakeup Callback:** Upon receiving the asynchronous response, the Netty NIO thread actively invokes CArtAgO's `resume(callId)` API. This forces the CArtAgO scheduler to re-awaken the specific operation thread with microsecond-precision, completely bypassing the polling loop.
4. **Operation Resumption:** CArtAgO seamlessly resumes the suspended operation. The method wraps the `.get()` evaluation in a `try-catch(RuntimeException)` block. If an ADACOR Phase 1 preemption previously cancelled the active RPC, the thrown exception is safely trapped and mapped to an `OpFeedbackParam`, averting stranded intentions in Jason.

### 2.2 Unary Synchronization Barrier with Embedded State **[Status: Production-Verified (Phase 1 & 2)]**

To eliminate ambiguity between time advancement and physical state retrieval, the integration bridge utilizes a strict **Unary Synchronization Barrier**:

```protobuf
rpc AdvanceTime (TimeStep) returns (StepReady);
```

For a factory co-simulation with a fixed clock tick rate, a purely unary request-response pattern per tick provides causal determinism. 
1. The JVM sends a single `AdvanceTime(TimeStep(t, dt))` request and blocks its internal clock.
2. The Python server integrates the physical model forward by `dt`, bundles the entire factory state vector into the response, and returns `StepReady(target_time, success, state_vector)`.
3. The JVM processes the state update and only then unblocks the clock.

This architecture prevents the JVM from ever holding a state that is decoupled from its internal clock, eliminating temporal ambiguity.

### 2.3 Time Synchronization Protocol (DCP-Inspired) **[Status: Production-Verified (Phase 1 & 2)]**

The system implements a formal time-synchronization protocol modeled on the **Distributed Co-simulation Protocol (DCP)** standard.

The Java `MainSimulator` application is promoted to the role of **Time Management Coordinator (TMC)**. BDI agents must not execute arbitrary time steps; instead, they register a **NextEventRequest (NER)**. The Python server acts as a **federate**, buffering physical manipulations without advancing numerical integration until receiving a **TimeAdvanceGrant (TAG)**.

**NER Aggregation Quorum (Tick-Count Deadline):**
The TMC collects NextEventRequests from all BDI agents using a deterministic quorum/ACK model. The TMC advances the simulation only after receiving explicit `NER_submitted` or `NER_timeout_acknowledged` signals from every registered agent for the current tick, completely eliminating wall-clock dependencies. To provide visibility into BDI overload, the system logs a `dropped_NER_count` metric, ensuring scheduling jitter is observable rather than silently baked into the physics.

**Schema Epoch Verification:**
The `AdvanceTime` TAG embeds a monotonic `schema_epoch` (AtomicInteger). When agents resume from an `await()`, they compare this epoch to detect if a `force_commit` organizational transition occurred while they were suspended.

### 2.4 JIT Warmup & Startup Sequence **[Status: Production-Verified (Phase 1 & 2)]**

When the Python physical daemon initializes, Numba's `@njit` functions defer LLVM Intermediate Representation (IR) compilation to the exact moment of their first execution, introducing a 1.5–3.0 second latency spike.

**Deterministic Bootstrapping:**
- `server.py` must start the gRPC port *before* initiating warmup, allowing immediate connection from the JVM. The server initializes an internal `_is_ready = False` flag.
- The `warmup_jit_kernels()` harness executes in a background `threading.Thread`. Upon completion, it sets `_is_ready = True`.
- The JVM `MainSimulator` polls the `HealthCheck` RPC at a fixed, deterministic **500ms interval**. The `HealthCheck` RPC responds immediately with `HealthStatus(ready=False)` until the background warmup completes, eliminating the need for exponential backoff during startup.

### 2.5 Station 1–4 Fast-Path Architecture **[Status: Production-Verified (Phase 1 & 2)]**

The stochastic domain logic governing Stations 1, 2, 3, and 4 relies strictly on statistical probability sampling (e.g., $t_{proc} \sim \mathcal{N}(45, 5)$ seconds).

**Architecture Decision:** Station 1–4 stochastics are computed **locally inside the Java CArtAgO artifacts** using a per-station, per-run-seeded `java.util.SplittableRandom(seed)` where `seed` is derived identically to the Python-side formula (e.g., `stationId.hashCode() ^ run_id`). This guarantees Monte Carlo reproducibility, which would be broken if drawn from a thread-local entropy pool. The gRPC bridge is **exclusively reserved** for Station 5's high-fidelity thermodynamic/electrochemical solvers and the utility Balance-of-Plant (BoP) systems (tanks, compressor, chiller).

### 2.6 Visualization Telemetry Pipeline **[Status: Production-Verified (Phase 3)]**

To route physical state data to a browser dashboard without introducing new read-locks on the Python physics daemon or stalling the MAS reasoning cycle, the system employs a lock-free telemetry pipeline:

**Lock-Free JVM Publish Pattern:** 
When `MainSimulator` receives the `StepReady` response from Python, it wraps the embedded Protobuf `state_vector` and the current `schema_epoch` inside an immutable snapshot object. This snapshot is published using an `AtomicReference.set()` operation. This provides a wait-free memory barrier where the writer never blocks, and any number of readers (like the visualization system) can call `.get()` concurrently without lock contention. This prevents TLAB/GC churn by avoiding deep copies of the `double[] state_vector`.

**WebSocket Serialization Standard:** 
The telemetry is forwarded to the frontend using **binary Protobuf over WebSockets**. Because the `StepReady` message already packs the `state_vector` as an optimized Protobuf repeated double field, the JVM simply forwards this binary payload directly to the browser. Decoding this array into Java objects only to re-encode it as a massive JSON string is strictly forbidden, as it would generate immense GC churn and burn CPU cycles.

## 3. Directory Structure Breakdown **[Status: Planned / Proposed (Phase 4)]**

For Monte Carlo runs (thirty 8760-hour simulated years), the Phase 4 deployment utilizes a **1:30 Single-JVM Fan-Out** topology. A single JaCaMo JVM instance routes RPCs across 30 isolated Python daemons listening on ports 50051–50080. 

> **Topology Mitigation (JVM Affinity):** To survive this density, the single JVM process must be explicitly pinned to an isolated set of high-priority physical cores via `taskset` to prevent the MAS reasoning cycle from being preempted or starved by the Numba JIT-heavy operations of the Python daemons.
>
> **Critical Constraint (Python Multiprocessing):** To prevent Linux CPU scheduler thrashing, the number of Numba threads per daemon must be dynamically constrained. Because `NUMBA_NUM_THREADS` assignment inside the Python script after `import numba` is a silent no-op, the parameter **must** be set *before* the import in a freshly spawned interpreter. Use `multiprocessing.get_context('spawn')` and set the environment variable inside the child's target function:
> ```python
> def _daemon_entry(port, n_threads):
>     os.environ['NUMBA_NUM_THREADS'] = str(n_threads)
>     import numba  # Env var now takes effect
>     run_server(port)
> 
> ctx = multiprocessing.get_context('spawn')
> n_threads = max(1, os.cpu_count() // 30)
> ctx.Process(target=_daemon_entry, args=(50051+i, n_threads)).start()
> ```
> Additionally, pin each daemon to a disjoint CPU set via `os.sched_setaffinity()` to prevent cross-NUMA migration.
>
> The same bounded-resource discipline must apply to gRPC. Neither the JVM channel nor any Python daemon's gRPC server may rely on gRPC's default cached thread pool executor under this topology — see `doc4_interface_control.md` §4.6 for the required explicit executor configuration.

```text
matrix_factory_twin/
│
├── build.gradle
├── settings.gradle
│
├── src/
│   ├── env/                     # CArtAgO Artifacts (Java)
│   │   └── factory/
│   │       ├── BaseStationArtifact.java      
│   │       ├── TestBenchArtifact.java        # Station 5 async artifact
│   │       ├── AMRArtifact.java              
│   │       ├── UtilitySystemArtifact.java    
│   │       ├── DatabaseArtifact.java         
│   │       ├── TimerArtifact.java            
│   │       └── EnergyPriceArtifact.java      
│   │
│   ├── ag/                      # Jason BDI Agents (ASL)
│   │
│   ├── org/                     # MoISE Specifications (XML)
│   │
│   └── java/                    # gRPC Client & Core Helpers (Java)
│       └── factory/
│           ├── GrpcClientBridge.java       
│           └── MainSimulator.java          
│
├── physical_engine/            # Python Simulation Core
│   ├── server.py                
│   ├── protos/
│   │   ├── sim_bridge.proto     
│   │
│   ├── h2_plant/                # Reusable physical simulation libraries
│   │
│   └── factory_simulation/      
│       └── stack_thermal_model.py
│
└── visualization/               # Web Interface
```
