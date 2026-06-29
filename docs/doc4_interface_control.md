# Document 4: Interface Control Document (ICD)

## 1. Overview **[Status: Production-Verified (Phase 1 & 2)]**

This Interface Control Document defines the asynchronous gRPC bridge integrating the JVM-based CArtAgO artifacts with the Python-based physical models. It maps high-level agent intentions to vectorized numerical executions via non-blocking Unary RPCs and packed Protobuf payloads.

**Crucially, the visualization layer is strictly forbidden from initiating direct RPCs (e.g., polling `RunBatchTest` or direct state reads) against the Python daemon.** All telemetry must flow unilaterally through the JVM via the `TelemetryArtifact` to avoid creating parallel read-locks on `_physics_step_lock` or racing against the integration loop.

## 2. Protobuf Service Definition (`sim_bridge.proto`) **[Status: Production-Verified (Phase 1 & 2)]**

The `SimBridge` service dictates the strict contract for advancing time and executing tests.

```protobuf
syntax = "proto3";

package factory;

// Use Netty direct memory buffers (ByteBuf) on the Java client 
// for Zero-Copy deserialization, bypassing the JVM heap.

service SimBridge {
  // Time Synchronization Barrier (Unary RPC)
  rpc AdvanceTime (TimeStep) returns (StepReady);
  
  // Batch testing interface for polarization curve sweeping
  rpc RunBatchTest (BatchTestRequest) returns (BatchTestResponse);
  
  // Warmup validation
  rpc HealthCheck (Empty) returns (HealthStatus);
}

// Time synchronization barrier messages
message TimeStep {
  double current_time = 1;
  double dt = 2;
  int32 schema_epoch = 3; // Enforces MoISE normative consensus
}

message StepReady {
  double target_time = 1;
  bool success = 2;
  // Embedded state vector prevents out-of-sync tearing between clock and physical state
  repeated double state_vector = 3 [packed = true];
}

message BatchTestRequest {
  string stack_id = 1;
  int32 num_cells = 2;
  double operating_temp_k = 3;
  double inlet_pressure_h2_bar = 4;
  double inlet_pressure_o2_bar = 5;
  // Optional client-side specification for advanced diagnostics (Phase 1)
  // If empty, the server computes a 12-point fixed curve autonomously.
  repeated double current_densities = 6 [packed = true];
}

message BatchTestResponse {
  bool passed = 1;
  repeated double measured_voltages = 2 [packed = true];
  
  // Compound Failure Flags (Bitmask)
  // bit 0 = OHMIC_DEGRADATION
  // bit 1 = MASS_TRANSPORT_STARVATION
  // bit 2 = THERMAL_SHUTDOWN
  // bit 3 = LOW_ACTIVATION
  // bit 4 = SOLVER_DID_NOT_CONVERGE
  uint32 failure_flags = 3;
}
```

## 3. CArtAgO Artifact Wrapper (Java) — Asynchronous Architecture **[Status: Production-Verified (Phase 1 & 2)]**

The Java artifact serves as the JaCaMo-facing API. It employs the CArtAgO `IBlockingCmd` + `resume(callId)` suspension protocol to decouple the JVM execution thread from RPC network latency. 

To ensure thread-safety during highly concurrent PROSA simulations, the artifact avoids shared mutable instance state. Furthermore, it explicitly manages the low-level `ClientCall` API to guarantee robust cancellation.

```java
package factory;

import cartago.*;
import io.grpc.ClientCall;
import io.grpc.CallOptions;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.UUID;

public class TestBenchArtifact extends Artifact {
    // Prevent orphaned streams by keying ClientCalls to a correlation UUID
    private final ConcurrentHashMap<String, ClientCall<BatchTestRequest, BatchTestResponse>> activeCalls = new ConcurrentHashMap<>();
    // Enforce exactly-once resumption to prevent TOCTOU races between network callbacks and ADACOR cancellation
    private final ConcurrentHashMap<String, AtomicBoolean> completedCalls = new ConcurrentHashMap<>();

    @OPERATION
    void executeTest(String stackId, ...) {
        BatchTestRequest request = BatchTestRequest.newBuilder()...build();
        String corrId = UUID.randomUUID().toString();
        
        ClientCall<BatchTestRequest, BatchTestResponse> call = channel.newCall(SimBridgeGrpc.getRunBatchTestMethod(), CallOptions.DEFAULT);
        this.activeCalls.put(corrId, call);
        this.completedCalls.put(corrId, new AtomicBoolean(false));
        
        call.start(new ClientCall.Listener<BatchTestResponse>() {
            @Override
            public void onMessage(BatchTestResponse message) {
                if (completedCalls.get(corrId).compareAndSet(false, true)) {
                    // Thread-safe signal to CArtAgO scheduler bypassing the polling await loop
                    signal("grpc_complete_" + corrId, message);
                    resume(corrId); 
                }
            }
            @Override
            public void onClose(Status status, Metadata trailers) {
                activeCalls.remove(corrId);
                if (!status.isOk() && !context.isCancelled()) {
                    if (completedCalls.get(corrId).compareAndSet(false, true)) {
                        // Propagate timeout/crash to Jason
                        signal("grpc_complete_" + corrId, new RuntimeException(status.toString()));
                        resume(corrId);
                    }
                }
            }
        }, new Metadata());
        
        call.sendMessage(request);
        call.halfClose();
        call.request(1);

        // Suspend operation with a 30s timeout
        await(corrId, 30_000L);

        // ... process signal response via OpFeedbackParam ...
    }
    
    /**
     * Prevent orphaned callbacks and CArtAgO signal buffer leaks when 
     * the ADACOR supervisor issues a drop_intention() command.
     * Note: CArtAgO does not call this automatically. The artifact MUST override 
     * CArtAgO's interruption listener to explicitly wire .drop_intention() to this method.
     */
    public void cancelPendingRpc() {
        this.activeCalls.forEach((corrId, c) -> {
            c.cancel("ADACOR suspend", null);
            if (this.completedCalls.get(corrId).compareAndSet(false, true)) {
                resume(corrId); // Safely release the await if cancelled mid-flight
            }
        });
        this.activeCalls.clear();
        this.completedCalls.clear();
    }
}
```

### AMR Artifact `OpFeedbackParam` Requirement **[Status: Production-Verified (Phase 1 & 2)]**
In `AMRArtifact.java`, the route reservation method must explicitly use a `OpFeedbackParam` so Jason can unify the result natively:
```java
@OPERATION void reserveTrajectory(Object[] trajectory, OpFeedbackParam result) { 
    boolean granted = collisionTable.validate(trajectory); 
    result.set(granted ? "granted" : "rejected"); 
}
```

## 4. Python Server Implementation (`server.py`) **[Status: Production-Verified (Phase 1 & 2)]**

The physical daemon acts as the gRPC server. The code utilizes `@njit(nogil=True, cache=True)` for true multi-core execution via `ThreadPoolExecutor`, which necessitates strict concurrency management.

### Key Implementation Requirements: **[Status: Production-Verified (Phase 1 & 2)]**

1.  **Analytic Jacobian Implementation:**
    The Newton-Raphson solver must substitute finite-difference derivatives with the closed-form analytic Jacobian.

2.  **Vectorized Polarization Curves & Scratchpad Isolation:**
    The `BatchTestRequest` processes the full V(j) curve using `numba.prange`. 
    - Explicit input validation must be added BEFORE the loop to protect the logarithm function domain: `if np.any(current_densities >= j_lim_pemfc): raise ValueError("current_densities must be strictly less than j_lim_pemfc")`.
    - Calling `np.empty()` inside a `prange` loop invokes the Numba Runtime (NRT) heap allocator, causing severe memory contention across multiprocess daemons.
    - Pre-allocate a global 2D scratchpad array immediately prior to the loop: `scratch = np.empty((numba_threads, buffer_size), np.float64)`. Pass this matrix into the JIT parallel kernel and index the isolation boundaries using a deterministic index derived from the `prange` loop variable (`idx = i % numba_threads`). **Do not use `numba.extending.get_thread_id()` in combination with `cache=True` under `parallel=True`** — this combination is a documented Numba defect that causes the kernel to hang on cache-loaded execution. If `get_thread_id()` is required for any reason, the enclosing function must not be decorated with `cache=True`.

3.  **Deterministic `nogil` Random Number Generation:**
    `PYTHONHASHSEED` randomizes `hash()` across the 30 multiprocessing daemon runs.
    - Use deterministic integer derivation for seeding: `seed = int.from_bytes(stack_id.encode('utf-8')[:8], 'little') ^ run_id`. Pass `run_id` as a server configuration parameter at daemon startup.

4.  **`AdvanceTime` and `RunBatchTest` Concurrency Synchronization:**
    A global `_physics_step_lock = threading.Lock()` must serialize state reads and writes. To prevent `RunBatchTest` from stalling `AdvanceTime` (priority inversion), `_physics_step_lock` must NOT wrap the iterative solver. Acquire the lock only to snapshot the required state (e.g., `h2_pressure`, `o2_pressure`, `T`), release it, run the Newton-Raphson solver lock-free on the private copy, and re-acquire only to commit `BatchTestResponse` flags if mutating shared state.

### 4.6 gRPC Executor Configuration **[Status: Production-Verified (Phase 1 & 2)]**
Both the JVM client channel (`GrpcClientBridge.java`) and the Python `server.py` gRPC server must explicitly configure a bounded, fixed-size executor rather than relying on gRPC's default cached thread pool. Size this executor consistently with the per-daemon thread budget already established for Numba (`threads = max(1, os.cpu_count() // 30)`), to avoid uncontrolled thread growth or contention under the 30-daemon Phase 4 deployment.
