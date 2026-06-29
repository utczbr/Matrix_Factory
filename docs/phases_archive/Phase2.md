# Phase 2: Core MAS Integration & RPC Bridge — Implementation Plan

## Background

Phase 1 delivered a fully verified Python physical engine: the `SimBridge` gRPC server, `pemfc_model.py` with analytic Newton-Raphson solver, the Yonkist-validated `StackThermalModel`, thread-safe `TankArray`, POSIX-locked `LUTManager`, Backward-Euler `Chiller`, and `factory_state.py` populating the canonical 9-element `ThermoStateIndex` state vector. All 28 pytest tests pass.

Phase 2 introduces the **JVM cognitive layer**. The goal is to couple the Java JaCaMo orchestrator to the running Python daemon via the gRPC bridge, prove the CNP negotiation protocol, and emit live telemetry frames to the browser WebSocket endpoint.

### Strategic Constraints (Carried from Phase 1 + New for Phase 2)

| # | Constraint | Impact |
|---|-----------|--------|
| 1 | **Java 17+, Gradle 8.x** — use the toolchain DSL | `java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }` |
| 2 | **JaCaMo 1.2** from Maven Central | `implementation 'org.jacamo:jacamo:1.2'` |
| 3 | **No gRPC cached thread pool** — explicit bounded executor only | `ThreadPoolExecutor(max(1, cpuCount/30))` per doc4 §4.6 |
| 4 | **No wall-clock timers in artifacts** — all TTLs via `TimerArtifact` NER queue | Applies to `EnergyPriceArtifact`, `TimerArtifact`, all reservation TTLs |
| 5 | **Station 1–4 stochastics on JVM only** — `SplittableRandom`, no Python call | seed = `stationId.hashCode() ^ run_id` per doc1 §2.5 |
| 6 | **`lastPublishedSimTimeS` advances only on WebSocket onSuccess** | Never on queue-offer per doc3 §4.2, doc6 §5.2 |
| 7 | **`volatile` atomic publish for AMR/Station state** — never contend CArtAgO belief-base lock | Volatile record fields; MainSimulator reads without lock acquisition |
| 8 | **Phase 2 uses `centralized_org.xml` only** — PROSA and ADACOR deferred to Phase 3 | One factory schema; agent roles: `order_manager`, `station_operator`, `transport_coordinator` |
| 9 | **Python daemon on port 50051 must be running** before JVM starts | `HealthCheck` polling loop handles startup sequencing |

---

## Proposed Changes

The work is organized into six components, ordered by dependency (infrastructure first, agents last).

---

### Component A: Gradle Project Setup & Protobuf Codegen

Zero runtime logic — establishes the build environment and generates all Java gRPC stubs from the proto already written in Phase 1.

#### [NEW] `settings.gradle`

```groovy
rootProject.name = 'matrix_factory_twin'
```

#### [NEW] `build.gradle`

Full dependency configuration:

```groovy
plugins {
    id 'java'
    id 'application'
    id 'com.google.protobuf' version '0.9.4'
    id 'org.jacamo' version '1.2'            // JaCaMo Gradle plugin
}

java {
    toolchain { languageVersion = JavaLanguageVersion.of(17) }
}

application {
    mainClass = 'factory.MainSimulator'
}

repositories {
    mavenCentral()
}

dependencies {
    // JaCaMo: Jason BDI + CArtAgO + MoISE
    implementation 'org.jacamo:jacamo:1.2'

    // gRPC + Protobuf (Netty transport)
    implementation 'io.grpc:grpc-netty-shaded:1.63.0'
    implementation 'io.grpc:grpc-protobuf:1.63.0'
    implementation 'io.grpc:grpc-stub:1.63.0'
    compileOnly     'org.apache.tomcat:annotations-api:6.0.53'  // @Generated

    // Protobuf runtime
    implementation 'com.google.protobuf:protobuf-java:3.25.3'

    // WebSocket server (Tyrus standalone — no servlet container needed)
    implementation 'org.glassfish.tyrus.bundles:tyrus-standalone-client:2.1.5'
    implementation 'jakarta.websocket:jakarta.websocket-api:2.1.0'

    // SQLite JDBC (DatabaseArtifact historian)
    implementation 'org.xerial:sqlite-jdbc:3.45.3.0'

    // Logging
    implementation 'org.slf4j:slf4j-api:2.0.12'
    runtimeOnly     'ch.qos.logback:logback-classic:1.5.6'

    // Test
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}

protobuf {
    protoc { artifact = 'com.google.protobuf:protoc:3.25.3' }
    plugins {
        grpc { artifact = 'io.grpc:protoc-gen-grpc-java:1.63.0' }
    }
    generateProtoTasks {
        all()*.plugins { grpc {} }
    }
}

// Tell the JaCaMo plugin where our JCM entry point lives
jacamo {
    jcmFile = file('factory.jcm')
}

sourceSets.main.java.srcDirs += 'build/generated/source/proto/main/java'
sourceSets.main.java.srcDirs += 'build/generated/source/proto/main/grpc'
```

**Proto source bridge:** The `sim_bridge.proto` written in Phase 1 lives at
`physical_engine/protos/sim_bridge.proto`. The Gradle protobuf plugin must resolve it:

```groovy
sourceSets.main.proto.srcDirs = ['physical_engine/protos']
```

> [!NOTE]
> After the first `./gradlew generateProto`, the generated classes appear at
> `build/generated/source/proto/main/java/factory/` and
> `build/generated/source/proto/main/grpc/factory/`.
> The Java package is `factory` because the proto declares `package factory;`.
> Verify `SimBridgeGrpc`, `TimeStep`, `StepReady`, `BatchTestRequest`,
> `BatchTestResponse`, `TelemetryFrame`, `AMRState`, `StationState` are all generated
> before writing any Java that imports them.

#### [NEW] `factory.jcm`

JaCaMo main configuration — the entry point for the cognitive layer:

```jacamo
mas factory_twin {

    agent order_manager : order_holon.asl {
        focus: factory_ws.base_station_1,
                factory_ws.base_station_2,
                factory_ws.base_station_3,
                factory_ws.base_station_4,
                factory_ws.test_bench,
                factory_ws.amr_artifact,
                factory_ws.timer_artifact,
                factory_ws.utility_system
        parameters: run_id(0)
    }

    // One resource holon per station (S1–S5)
    agent station_1 : resource_holon.asl {
        focus: factory_ws.base_station_1, factory_ws.timer_artifact
        parameters: station_id(1)
    }
    agent station_2 : resource_holon.asl {
        focus: factory_ws.base_station_2, factory_ws.timer_artifact
        parameters: station_id(2)
    }
    agent station_3 : resource_holon.asl {
        focus: factory_ws.base_station_3, factory_ws.timer_artifact
        parameters: station_id(3)
    }
    agent station_4 : resource_holon.asl {
        focus: factory_ws.base_station_4, factory_ws.timer_artifact
        parameters: station_id(4)
    }
    agent station_5 : resource_holon.asl {
        focus: factory_ws.test_bench, factory_ws.timer_artifact
        parameters: station_id(5)
    }

    // Two AMR transport agents
    agent amr_1 : amr_agent.asl {
        focus: factory_ws.amr_artifact
        parameters: amr_id("AMR-1")
    }
    agent amr_2 : amr_agent.asl {
        focus: factory_ws.amr_artifact
        parameters: amr_id("AMR-2")
    }

    workspace factory_ws {
        artifact base_station_1  : factory.BaseStationArtifact("S1", 1, 45.0, 5.0, 0.005, 0)
        artifact base_station_2  : factory.BaseStationArtifact("S2", 2, 120.0, 15.0, 0.012, 0)
        artifact base_station_3  : factory.BaseStationArtifact("S3", 3, 30.0, 2.0, 0.002, 0)
        artifact base_station_4  : factory.BaseStationArtifact("S4", 4, 240.0, 30.0, 0.008, 0)
        artifact test_bench      : factory.TestBenchArtifact("S5", 0)
        artifact amr_artifact    : factory.AMRArtifact(20, 12, 2)
        artifact utility_system  : factory.UtilitySystemArtifact()
        artifact timer_artifact  : factory.TimerArtifact()
        artifact energy_price    : factory.EnergyPriceArtifact("price_series.csv")
        artifact database        : factory.DatabaseArtifact("factory_history.db")
        artifact telemetry       : factory.TelemetryArtifact(8080)
    }

    org factory_org {
        org-file: "src/org/centralized_org.xml"
        group factory_line  : production_line {
            players: order_manager order_manager,
                     station_1    station_operator,
                     station_2    station_operator,
                     station_3    station_operator,
                     station_4    station_operator,
                     station_5    station_operator,
                     amr_1        transport_coordinator,
                     amr_2        transport_coordinator
        }
    }
}
```

---

### Component B: Core Java Infrastructure

These three classes form the backbone of the JVM side. They have no CArtAgO or Jason dependencies — they wrap the gRPC channel and drive the simulation clock.

#### [NEW] `src/java/factory/TelemetryFrameSnapshot.java`

Immutable value type for lock-free publish pattern (doc1 §2.6, doc6 §3.2). Defined first because `MainSimulator` and `TelemetryArtifact` both reference it.

```java
package factory;

/**
 * Immutable snapshot of one simulation tick's telemetry payload.
 * Published via AtomicReference.set() in MainSimulator; read by TelemetryArtifact.
 * The byte[] is the result of TelemetryFrame.toByteArray() — Protobuf binary.
 * Treating it as opaque bytes avoids a second serialization pass in TelemetryArtifact.
 */
public record TelemetryFrameSnapshot(byte[] payload, double simTimeS, long sequenceNumber) {}
```

#### [NEW] `src/java/factory/NEREntry.java`

Simulated-time priority queue entry for the TMC quorum collector (doc1 §2.3):

```java
package factory;

public record NEREntry(String agentId, double requestedNextTime) 
    implements Comparable<NEREntry> {
    @Override
    public int compareTo(NEREntry o) {
        return Double.compare(this.requestedNextTime, o.requestedNextTime);
    }
}
```

#### [NEW] `src/java/factory/StationSummary.java`

Volatile-publish value type for each station artifact:

```java
package factory;

// Import the generated Protobuf enum
import factory.SimBridgeProto.StationStateEnum;

public record StationSummary(
    StationStateEnum state,
    String activeOrderId,
    float processingProgress   // [0.0, 1.0], meaningful only when BUSY_PROCESSING
) {
    public static final StationSummary IDLE = 
        new StationSummary(StationStateEnum.STATION_IDLE, "", 0.0f);
}
```

#### [NEW] `src/java/factory/AMRSnapshot.java`

Value type for the volatile AMR position array (doc6 §3.2):

```java
package factory;

import factory.SimBridgeProto.AMRStatusEnum;

public record AMRSnapshot(
    String amrId,
    int gridX,
    int gridY,
    int nextGridX,
    int nextGridY,
    float movementProgress,    // [0.0, 1.0]
    AMRStatusEnum status,
    String carryingOrderId
) {}
```

#### [NEW] `src/java/factory/ProtoIndex.java`

Exact Java mirror of `physical_engine/proto_index.py` per doc6 §3.3. Used by `MainSimulator` to extract summary fields from the `state_vector` and to validate the vector length on first tick.

```java
package factory;

/**
 * Canonical index map for thermo_state_vector in StepReady / TelemetryFrame.
 * MUST stay byte-for-byte synchronized with physical_engine/proto_index.py.
 * Any addition requires bumping both files simultaneously and redeploying all daemons.
 */
public final class ProtoIndex {
    public static final int H2_TANK_PRESSURE_BAR    = 0;
    public static final int H2_TANK_FILL_FRACTION   = 1;
    public static final int CHILLER_TEMP_K          = 2;
    public static final int COMPRESSOR_POWER_KW     = 3;
    public static final int STACK_VOLTAGE_V         = 4;
    public static final int STACK_CURRENT_A_CM2     = 5;
    public static final int STACK_TEMP_K            = 6;
    public static final int STACK_CORE_TEMP_K       = 7;
    public static final int STACK_SKIN_TEMP_K       = 8;

    /** Sentinel: must equal ThermoStateIndex._VECTOR_LENGTH in proto_index.py. */
    public static final int VECTOR_LENGTH = 9;

    private ProtoIndex() {}

    /**
     * Called once on first StepReady receipt. Throws immediately if the Python
     * daemon was built against a different proto_index.py version.
     */
    public static void validateVectorLength(int actualLength) {
        if (actualLength != VECTOR_LENGTH) {
            throw new IllegalStateException(
                "thermo_state_vector length mismatch: expected "
                + VECTOR_LENGTH + ", got " + actualLength
                + ". Sync proto_index.py with ProtoIndex.java and redeploy all daemons."
            );
        }
    }
}
```

#### [NEW] `src/java/factory/GrpcClientBridge.java`

Owns the gRPC `ManagedChannel` and provides typed stubs to `MainSimulator`. Never touches CArtAgO or Jason directly.

**Key implementation requirements (doc1 §2.4, doc4 §4.6):**

- Use a **bounded, fixed-size executor** — never `Executors.newCachedThreadPool()`:

```java
int threads = Math.max(1, Runtime.getRuntime().availableProcessors() / 30);
ExecutorService executor = new ThreadPoolExecutor(
    threads, threads, 0L, TimeUnit.MILLISECONDS,
    new LinkedBlockingQueue<>(256),
    new ThreadPoolExecutor.CallerRunsPolicy()
);
ManagedChannel channel = NettyChannelBuilder.forAddress("localhost", port)
    .usePlaintext()
    .executor(executor)
    .build();
```

- Provide a **blocking stub** for `AdvanceTime` (called synchronously by the TMC tick loop)
  and an **async stub** for `RunBatchTest` (used by `TestBenchArtifact` via its own `ClientCall`).
- Expose `pollUntilReady()`: loops `HealthCheck` at exactly **500 ms** fixed intervals
  (`Thread.sleep(500)`, not exponential backoff) until `HealthStatus.ready == true`.
- Expose `advanceTime(double t, double dt, int schemaEpoch)` returning `StepReady`.
- Expose `getChannel()` so `TestBenchArtifact` can call `channel.newCall(...)` directly
  (required for low-level `ClientCall` cancellation per doc4 §3).
- Expose `shutdown()` for graceful teardown on `SIGTERM`.

> [!WARNING]
> Do not use `ManagedChannelBuilder.forAddress()` without `.executor(executor)`.
> The default cached thread pool grows unboundedly under 30-daemon Phase 4 fan-out
> and will exhaust system threads. Sized executor only.

#### [NEW] `src/java/factory/MainSimulator.java`

The **Time Management Coordinator (TMC)** — the central orchestrator per doc1 §2.3. Drives the simulation clock, assembles `TelemetryFrame`, and provides hooks for all artifacts.

**Startup sequence:**

```
main()
  → GrpcClientBridge.pollUntilReady()         // 500ms fixed-interval HealthCheck
  → initialize all artifact references        // via CArtAgO workspace lookup
  → EnergyPriceArtifact.updatePrice(0.0)     // initial price
  → schemaEpoch.set(0)
  → start simulation tick loop thread
```

**Tick loop (runs in dedicated thread, separated from CArtAgO event loop):**

```
while (!shutdown) {
    // 1. Wait for NER quorum from all registered agents
    awaitNERQuorum(currentTickTimeout)      // deterministic, not wall-clock

    // 2. Compute next sim time: min of all NERs, bounded by dt
    double nextTime = currentTime + computedDt

    // 3. Send AdvanceTime gRPC call (blocking)
    StepReady ready = grpcBridge.advanceTime(currentTime, computedDt, schemaEpoch.get())

    // 4. Validate state vector on first tick
    if (firstTick) {
        ProtoIndex.validateVectorLength(ready.getStateVectorCount())
        firstTick = false
    }

    currentTime = ready.getTargetTime()

    // 5. Drive TimerArtifact and EnergyPriceArtifact with sim time
    timerArtifact.evaluateTTLs(currentTime)
    energyPriceArtifact.updatePrice(currentTime)

    // 6. Assemble TelemetryFrame (volatile reads, no locks)
    TelemetryFrame frame = assembleTelemetryFrame(ready)

    // 7. Publish snapshot wait-free
    telemetryRef.set(new TelemetryFrameSnapshot(
        frame.toByteArray(), currentTime, sequenceNumber.getAndIncrement()
    ))

    // 8. Issue TimeAdvanceGrant to all agents
    issueTimeAdvanceGrant(currentTime, schemaEpoch.get())
}
```

**NER quorum mechanism (doc1 §2.3):**

- `ConcurrentHashMap<String, NEREntry> nerRegistry` — keyed by `agentId`.
- `CountDownLatch nerLatch` — reset to `registeredAgentCount` at each tick start.
- Agents call `submitNER(agentId, requestedNextTime)` → populates registry, calls `latch.countDown()`.
- `awaitNERQuorum()` calls `latch.await(TICK_QUORUM_TIMEOUT_MS, MILLISECONDS)`.
- If latch not reached (agent overloaded), logs `dropped_NER_count++` and proceeds anyway.
- `computedDt` = `min(all NEREntries.requestedNextTime) − currentTime`, clamped to `[MIN_DT, MAX_DT]`.

**TelemetryFrame assembly (doc6 §3.2):**

```java
private TelemetryFrame assembleTelemetryFrame(StepReady ready) {
    TelemetryFrame.Builder b = TelemetryFrame.newBuilder();

    // Frame identity
    b.setSequenceNumber(sequenceNumber.get())
     .setSimTimeS(currentTime)
     .setSchemaEpoch(schemaEpoch.get())
     .setActiveOrgSchema("centralized");    // Phase 3: dynamic

    // ── AMR state (volatile read, zero lock) ──────────────────────
    AMRSnapshot[] amrPositions = amrArtifact.currentPositions;  // volatile field
    for (AMRSnapshot snap : amrPositions) {
        b.addAmrStates(AMRState.newBuilder()
            .setAmrId(snap.amrId())
            .setGridX(snap.gridX())       .setGridY(snap.gridY())
            .setNextGridX(snap.nextGridX()).setNextGridY(snap.nextGridY())
            .setMovementProgress(snap.movementProgress())
            .setStatus(snap.status())
            .setCarryingOrderId(snap.carryingOrderId())
            .build());
    }

    // ── Station state (volatile read, zero lock) ──────────────────
    for (BaseStationArtifact sta : stationArtifacts) {
        StationSummary sum = sta.currentSummary;  // volatile field
        b.addStationStates(StationState.newBuilder()
            .setStationId(sta.stationId)
            .setState(sum.state())
            .setActiveOrderId(sum.activeOrderId())
            .setProcessingProgress(sum.processingProgress())
            .build());
    }

    // ── Thermodynamic state (zero-copy bytes passthrough) ─────────
    // Do NOT deserialize to double[] and re-serialize. Copy raw bytes.
    b.setThermoStateVectorBytes(ready.getStateVectorBytes());

    // ── Pre-extracted summary fields for browser convenience ───────
    List<Double> sv = ready.getStateVectorList();
    b.setStation5StackVoltageV(sv.get(ProtoIndex.STACK_VOLTAGE_V))
     .setStation5CurrentDensityACm2(sv.get(ProtoIndex.STACK_CURRENT_A_CM2))
     .setStation5StackTempK(sv.get(ProtoIndex.STACK_TEMP_K))
     .setStation5StackCoreTempK(sv.get(ProtoIndex.STACK_CORE_TEMP_K))
     .setStation5StackSkinTempK(sv.get(ProtoIndex.STACK_SKIN_TEMP_K))
     .setH2TankPressureBar(sv.get(ProtoIndex.H2_TANK_PRESSURE_BAR))
     .setH2TankFillFraction(sv.get(ProtoIndex.H2_TANK_FILL_FRACTION))
     .setChillerTempK(sv.get(ProtoIndex.CHILLER_TEMP_K))
     .setCompressorPowerKw(sv.get(ProtoIndex.COMPRESSOR_POWER_KW))
     .setDroppedTelemetryFrameCount(telemetryArtifact.droppedTelemetryFrameCount.intValue())
     .setDroppedNerCount((int) droppedNerCount.get())
     .setRunId(runId);

    return b.build();
}
```

> [!IMPORTANT]
> **`b.setThermoStateVectorBytes(ready.getStateVectorBytes())`** — this is a zero-copy
> raw-byte passthrough. Never call `ready.getStateVectorList()` for the TelemetryFrame
> population itself; only use the deserialized list for the pre-extracted summary fields.
> Deserializing to Java `double[]` only to re-serialize wastes a full GC allocation cycle.

> [!WARNING]
> **Volatile field access discipline:** `amrArtifact.currentPositions` and
> `sta.currentSummary` are `volatile` fields on the artifact objects.
> `MainSimulator` reads them here without acquiring any lock. This is safe because:
> (a) Java `volatile` guarantees visibility of the most recently written value, and
> (b) both fields are written as complete immutable records, never mutated in place.
> Under no circumstances should `MainSimulator` call into CArtAgO's belief-base API
> to extract station or AMR state — the belief-base lock is held during Jason inference
> cycles and contending on it from the tick loop creates deadlock risk.

---

### Component C: Infrastructure Artifacts

These artifacts have no inter-artifact dependencies and can be developed in parallel after Component B.

#### [NEW] `src/env/factory/TimerArtifact.java`

NER-based TTL manager for `provisional_lock` timeouts (doc3 §2.2). Zero wall-clock dependency.

**Key fields:**
```java
// PriorityQueue orders by fire time — smallest simulated timestamp fires first
private final PriorityQueue<TimerEntry> timerQueue = new PriorityQueue<>(
    Comparator.comparingDouble(e -> e.fireAtSimTime)
);
private record TimerEntry(String orderId, double fireAtSimTime, String targetAgentId) {}
```

**`@OPERATION startTimer(String orderId, double ttlMs, String agentId)`:**
- Converts `ttlMs` from simulated milliseconds to simulated seconds: `fireAt = currentSimTime + ttlMs / 1000.0`
- Inserts `new TimerEntry(orderId, fireAt, agentId)` into `timerQueue`.
- All mutations under `synchronized(timerQueue)`.

**`evaluateTTLs(double simTime)` (called by `MainSimulator`, NOT an `@OPERATION`):**
- Polls all entries from `timerQueue` where `entry.fireAtSimTime <= simTime`.
- For each expired entry: calls `execInternalOp("signal_timer_expired", orderId, agentId)` or equivalent mechanism to inject `timer_expired(orderId)` into the target agent's event queue.

> [!IMPORTANT]
> Per doc3 §2.2, the **execution ordering invariant** requires that all `timer_expired`
> NERs for a given tick are resolved *before* inter-agent messages generated within that
> same tick window are processed. Achieving this requires `evaluateTTLs()` to be called
> by `MainSimulator` *before* it issues the `TimeAdvanceGrant` to agents.

**`@OPERATION cancelTimer(String orderId)`:**
- Removes the entry from the queue. Used when `accept_proposal` finalizes a lock before TTL fires.

#### [NEW] `src/env/factory/EnergyPriceArtifact.java`

Simulation-clock-driven energy price reader (doc3 §3.1). No executor, no wall-clock dependency.

**Initialization:** Reads `price_series.csv` at `init()` into a `NavigableMap<Double, Double> priceAtSimTime` (simulated time → EUR/MWh).

**`updatePrice(double simTime)` (called by `MainSimulator` at each TAG, NOT an `@OPERATION`):**
- Looks up `priceAtSimTime.floorEntry(simTime)` for current price.
- Updates observable property `energy_price(price)` via `defineObsProperty` / `updateObsProperty`.
- Broadcasts `energy_price_changed(price)` signal when price crosses a threshold defined in `price_series.csv`.

> [!NOTE]
> This method is not a CArtAgO `@OPERATION`. It is a plain `public synchronized void` method
> on the artifact class, called directly by `MainSimulator` inside the tick loop.
> CArtAgO operations run on the CArtAgO thread pool; this method runs on the `MainSimulator`
> tick loop thread. Use `synchronized` on the price field to prevent torn reads by agent
> plans that observe `energy_price`.

#### [NEW] `src/env/factory/DatabaseArtifact.java`

Lossless historian backed by SQLite with async write queue (doc3 §4.1).

**Queue and consumer:**
```java
private final ArrayBlockingQueue<BatchRecord> writeQueue = new ArrayBlockingQueue<>(300_000);
private final AtomicLong droppedRecordCount = new AtomicLong(0);
private volatile boolean backpressureActive = false;
```

**Consumer thread (started in `init()`):**
- `Thread.setDaemon(true)` — does not prevent JVM shutdown.
- Loop: `List<BatchRecord> batch = new ArrayList<>();`
  - `writeQueue.drainTo(batch, Math.min(MAX_BATCH, writeQueue.size()))` — adaptive drain.
  - If `batch.isEmpty()`: `Thread.sleep(500)` and retry.
  - Else: execute `INSERT OR IGNORE INTO batches (...) VALUES (?, ?, ?)` in a single transaction.

**SQLite pragmas (applied at connection open):**
```java
stmt.execute("PRAGMA journal_mode=WAL");
stmt.execute("PRAGMA wal_autocheckpoint=100");
stmt.execute("PRAGMA synchronous=NORMAL");
```

**Backpressure signals (checked after each `offer()`):**
- `queue.size() > 297_000` → `signal("database_backpressure")` + `backpressureActive = true`.
- `queue.size() < 3_000` && `backpressureActive` → `signal("database_pressure_normal")` + `backpressureActive = false`.

**`@OPERATION recordBatch(String orderId, int stationId, double startTime, double endTime, boolean passed)`:**
- Constructs `BatchRecord` and calls `writeQueue.offer(record)`.
- If `offer()` returns `false` (queue full): `droppedRecordCount.incrementAndGet()`.
- Never blocks.

#### [NEW] `src/env/factory/TelemetryArtifact.java`

Lossy WebSocket publisher — reads the `AtomicReference` snapshot and pushes binary Protobuf frames (doc3 §4.2, doc6 §5).

**Key fields:**
```java
// Injected by MainSimulator after it is constructed
public volatile AtomicReference<TelemetryFrameSnapshot> telemetryRef;
public final AtomicLong droppedTelemetryFrameCount = new AtomicLong(0);

private volatile double lastPublishedSimTimeS = -1.0;
private final double TARGET_HZ = 15.0;
private final double FRAME_INTERVAL_S = 1.0 / TARGET_HZ;

private Session wsSession;   // set when browser connects; null when disconnected
```

**WebSocket server setup (in `init()`):**
- Start Tyrus `WebSocketContainer` on `127.0.0.1:wsPort` (passed as constructor arg).
- Register endpoint class `TelemetryEndpoint`.
- Inbound binary or text frames: close session with code 1003 (`UNSUPPORTED_DATA`). The endpoint is publish-only.
- One session at a time: if a second `onOpen` arrives, close the existing session first with code `4001`.

**Consumer thread (started in `init()`, `setDaemon(true)`):**
```java
while (!shutdown) {
    Thread.sleep(1);   // ~1ms poll cadence, negligible CPU
    TelemetryFrameSnapshot snap = telemetryRef.get();
    if (snap == null) continue;
    if (snap.simTimeS() - lastPublishedSimTimeS < FRAME_INTERVAL_S) continue;
    if (wsSession == null || !wsSession.isOpen()) continue;

    try {
        wsSession.getAsyncRemote().sendBinary(
            ByteBuffer.wrap(snap.payload()),
            result -> {
                if (result.isOK()) {
                    lastPublishedSimTimeS = snap.simTimeS();  // Advance ONLY on success
                } else {
                    droppedTelemetryFrameCount.incrementAndGet();
                    // lastPublishedSimTimeS NOT advanced — same slot eligible next cycle
                }
            }
        );
    } catch (Exception e) {
        droppedTelemetryFrameCount.incrementAndGet();
    }
}
```

> [!IMPORTANT]
> **`lastPublishedSimTimeS` rule:** This value advances **only** inside the `sendBinary`
> callback's `result.isOK()` branch. A frame dropped due to TCP backpressure or a disconnected
> browser does not consume that simulation-time decimation slot. The next snapshot that clears
> the `FRAME_INTERVAL_S` gap will be eligible for delivery. This is the exact rule from
> doc3 §4.2 and doc6 §5.2.

> [!WARNING]
> **Do not** use `wsSession.getBasicRemote().sendBinary()` — it blocks until the TCP write
> buffer drains. Under browser backpressure, this stalls the consumer thread indefinitely,
> violating the non-blocking requirement (doc3 §4.2, doc6 §5.3). `getAsyncRemote()` with
> a callback is mandatory.

#### [NEW] `src/env/factory/UtilitySystemArtifact.java`

Lightweight monitoring artifact exposing BoP observable properties to agents.

- On each `updateFromStateVector(double[] sv)` call (invoked by `MainSimulator` after each tick):
  - `updateObsProperty("h2_pressure_bar", sv[ProtoIndex.H2_TANK_PRESSURE_BAR])`
  - `updateObsProperty("h2_fill_fraction", sv[ProtoIndex.H2_TANK_FILL_FRACTION])`
  - `updateObsProperty("chiller_temp_k", sv[ProtoIndex.CHILLER_TEMP_K])`
  - `updateObsProperty("compressor_power_kw", sv[ProtoIndex.COMPRESSOR_POWER_KW])`
- Agents observe `h2_pressure_bar(P)` etc. as beliefs to gate `RunBatchTest` requests.
- No gRPC calls — reads only from `MainSimulator`-supplied state vector.

---

### Component D: Factory Floor Artifacts

These three artifacts are the most complex. They implement the physical factory operations.

#### [NEW] `src/env/factory/BaseStationArtifact.java`

Station 1–4 fast-path artifact — all stochastics computed locally on JVM (doc1 §2.5).

**Constructor parameters:**
```java
public BaseStationArtifact(String stationId, int stationIndex,
    double tMean_s, double tStd_s, double defectRate, int runId)
```

**Random source (doc1 §2.5):**
```java
long seed = stationId.hashCode() ^ runId;
private final SplittableRandom rng = new SplittableRandom(seed);
```

`SplittableRandom` is preferred over `ThreadLocalRandom` because the seed is deterministic across Monte Carlo runs — essential for reproducibility.

**Volatile state publication (doc6 §3.2):**
```java
public volatile StationSummary currentSummary = StationSummary.IDLE;
```

Written atomically as a complete record replacement after every state transition. Never mutated field-by-field.

**`@OPERATION claimStation(String orderId)` → `OpFeedbackParam result`:**
- Guard: must be in `IDLE` state.
- Transition: `currentSummary = new StationSummary(STATION_PROVISIONAL_LOCK, orderId, 0.0f)`.
- Returns `"claimed"`.

**`@OPERATION processOrder(String orderId)` → `OpFeedbackParam result`:**
- Guard: must be in `STATION_PROVISIONAL_LOCK` for this `orderId`.
- Transition: `currentSummary = new StationSummary(STATION_BUSY_PROCESSING, orderId, 0.0f)`.
- Sample processing time: `double tProc = tMean_s + rng.nextGaussian() * tStd_s`
  (bounded to `[tMean_s * 0.1, tMean_s * 3.0]` to avoid degenerate negatives).
- Sample defect: `boolean defect = rng.nextDouble() < defectRate`.
- Simulate processing: blocks CArtAgO operation for `tProc` simulated seconds (coordinated via NER submission to `MainSimulator`).
  - In Phase 2, this is approximated by submitting a NER to `MainSimulator` with `requestedNextTime = currentSimTime + tProc` and `await()`-ing the `TimeAdvanceGrant` callback.
- On completion: `currentSummary = new StationSummary(STATION_IDLE, "", 0.0f)`.
- Returns `defect ? "defect" : "ok"`.
- Updates `processingProgress` during processing by exposing an observable property `station_progress(progress)`.

**`@OPERATION releaseStation(String orderId)`:**
- Force-resets to `STATION_IDLE` regardless of current state. Used by ADACOR abort in Phase 3.

> [!NOTE]
> The `processingProgress` float in `StationSummary` is updated periodically via
> `currentSummary = new StationSummary(STATION_BUSY_PROCESSING, orderId, progress)`.
> Since this is a volatile write, it is visible to `MainSimulator`'s volatile read
> without synchronization.

#### [NEW] `src/env/factory/TestBenchArtifact.java`

Station 5 electrochemical test — async gRPC `RunBatchTest` per doc4 §3.

**Full implementation per doc4 §3 (reproduced and expanded):**

```java
// Correlation tracking
private final ConcurrentHashMap<String, ClientCall<BatchTestRequest, BatchTestResponse>>
    activeCalls = new ConcurrentHashMap<>();
private final ConcurrentHashMap<String, AtomicBoolean>
    completedCalls = new ConcurrentHashMap<>();

public volatile StationSummary currentSummary = StationSummary.IDLE;
```

**`@OPERATION executeTest(String stackId, int numCells, double tempK, double pH2Bar, double pO2Bar, OpFeedbackParam result)`:**

```java
// 1. Transition to BUSY
currentSummary = new StationSummary(STATION_BUSY_PROCESSING, stackId, 0.0f);

// 2. Build request
BatchTestRequest req = BatchTestRequest.newBuilder()
    .setStackId(stackId).setNumCells(numCells)
    .setOperatingTempK(tempK)
    .setInletPressureH2Bar(pH2Bar)
    .setInletPressureO2Bar(pO2Bar)
    .build();

// 3. Correlation ID for exactly-once resumption
String corrId = UUID.randomUUID().toString();
ClientCall<BatchTestRequest, BatchTestResponse> call =
    grpcBridge.getChannel().newCall(SimBridgeGrpc.getRunBatchTestMethod(), CallOptions.DEFAULT);
activeCalls.put(corrId, call);
completedCalls.put(corrId, new AtomicBoolean(false));

// 4. Register listener
call.start(new ClientCall.Listener<>() {
    @Override
    public void onMessage(BatchTestResponse resp) {
        if (completedCalls.get(corrId).compareAndSet(false, true)) {
            // Parse failure bitmask and update station state
            boolean passed = resp.getPassed();
            int flags = resp.getFailureFlags();
            currentSummary = passed
                ? new StationSummary(STATION_IDLE, "", 0.0f)
                : new StationSummary(STATION_DEFECT_DETECTED, stackId, 1.0f);
            // Signal result to Jason agent
            signal("test_complete_" + corrId, passed, flags);
            resume(corrId);
        }
    }
    @Override
    public void onClose(Status status, Metadata trailers) {
        activeCalls.remove(corrId);
        if (!status.isOk()) {
            if (completedCalls.get(corrId).compareAndSet(false, true)) {
                currentSummary = new StationSummary(STATION_OFFLINE, stackId, 0.0f);
                signal("test_complete_" + corrId, false, /* SOLVER_DID_NOT_CONVERGE flag */ 0x10);
                resume(corrId);
            }
        }
    }
}, new Metadata());

call.sendMessage(req);
call.halfClose();
call.request(1);

// 5. Suspend with 30s watchdog
await(corrId, 30_000L);

// 6. Extract result from signal (arrived during suspension)
//    Use OpFeedbackParam to unify result in Jason
// ... result.set(signalValue) ...

// 7. Cleanup
activeCalls.remove(corrId);
completedCalls.remove(corrId);
```

**`cancelPendingRpc()` — must be wired to ADACOR `drop_intention()`:**
```java
public void cancelPendingRpc() {
    activeCalls.forEach((corrId, call) -> {
        call.cancel("ADACOR suspend", null);
        if (completedCalls.get(corrId).compareAndSet(false, true)) {
            currentSummary = StationSummary.IDLE;
            resume(corrId);   // Safely release await — RuntimeException trapped by Jason
        }
    });
    activeCalls.clear();
    completedCalls.clear();
}
```

> [!IMPORTANT]
> CArtAgO does **not** call `cancelPendingRpc()` automatically on `drop_intention()`.
> This method must be explicitly wired: override the `Artifact` lifecycle method that
> is invoked when an operation is interrupted externally (check JaCaMo 1.2 docs for
> `onOperationCancelled` or the equivalent hook). The connection between `.drop_intention()`
> in Jason and `cancelPendingRpc()` in Java is **manual** and is one of the most
> common omissions that strands Jason intentions (doc5 §2 Risk Table).

#### [NEW] `src/env/factory/AMRArtifact.java`

4D Spatio-Temporal Reservation Matrix for collision-free AMR routing (doc3 §2.3, doc6 §3.2).

**State:**
```java
// Reservation matrix: reservedBy[x][y][tickOffset] → amrId (null = free)
// tickOffset horizon: HORIZON_TICKS = 10 ticks ahead
private final String[][][] reservedBy;
private final int gridCols, gridRows;
private final int HORIZON_TICKS = 10;
private double currentSimTime = 0.0;
private double tickDt = 1.0;   // set by MainSimulator after first AdvanceTime

public volatile AMRSnapshot[] currentPositions;
```

**`@OPERATION reserveTrajectory(Object[] trajectory, OpFeedbackParam result)`:**

`trajectory` is an array of `[x, y, tickOffset]` tuples from Jason. Validates all cells are:
- Within grid bounds.
- Not already reserved by a different AMR.

If granted: marks cells in `reservedBy`. Sets `result.set("granted")`.
If collision detected: `result.set("rejected")`.

All mutations under `synchronized(reservedBy)`.

**`getGridUtilization()` (public method, called by supervisor agent):**
```java
public double getGridUtilization() {
    long occupied = 0;
    for (String[][] row : reservedBy)
        for (String[] cell : row)
            for (String amrId : cell)
                if (amrId != null) occupied++;
    return (double) occupied / (gridCols * gridRows * HORIZON_TICKS);
}
```

**`clearExpiredReservations()` (called by supervisor when utilization > 0.85):**
- Removes all reservation entries where `tickOffset == 0` (already elapsed).
- Advances the horizon window by one tick.

**`updatePositions(double simTime, double dt)` (called by `MainSimulator` after each TAG):**
- Scans `reservedBy` to compute current and next-cell for each known AMR.
- Computes `movementProgress = (simTime - lastDepartureTime[amrId]) / dt`.
- Writes the result atomically:
  ```java
  currentPositions = buildSnapshots();  // constructs full AMRSnapshot[] immutably
  ```
  This is a single `volatile` array reference write — safe for `MainSimulator`'s volatile read.

> [!IMPORTANT]
> Per doc6 §3.2: `currentPositions` must be written as a **single volatile reference
> assignment** to a fully constructed, immutable `AMRSnapshot[]`. Never mutate elements
> of the existing array in place. A torn read (stale `nextGridX` paired with fresh `gridX`)
> causes the browser to animate AMRs toward incorrect cells.

---

### Component E: Jason BDI Agents

#### [NEW] `src/ag/order_holon.asl`

```jason
// ── Initialization ──────────────────────────────────────────────────────
!start.

+!start
  <- ?run_id(RunId);
     .print("Order Holon started, run_id=", RunId);
     !request_next_batch.

// ── Production Cycle ────────────────────────────────────────────────────
+!request_next_batch
  <- .my_name(Me);
     .uuid(OrderId);
     .print("Initiating CNP for order ", OrderId);
     !call_for_proposals(OrderId, [s1, s2, s3, s4]).

// ── CNP Protocol (Station selection) ────────────────────────────────────

// Broadcast CFP to all eligible station agents
+!call_for_proposals(OrderId, Stations)
  <- .broadcast(tell, cfp(1, Stations, OrderId));
     !collect_proposals(OrderId, Stations, 0, []).

// Collect proposals with timeout (uses TimerArtifact NER, not wall-clock)
+!collect_proposals(OrderId, Stations, _, Proposals)
  : .length(Proposals, N) & N >= 1
  <- !select_best_proposal(OrderId, Proposals).

+!collect_proposals(OrderId, Stations, Attempt, Proposals)
  : Attempt < 3
  <- .wait(1000);   // 1s simulated wait
     !collect_proposals(OrderId, Stations, Attempt+1, Proposals).

+!collect_proposals(OrderId, _, _, _)    // Timeout: no proposals received
  <- .print("No proposals for order ", OrderId, " — retrying");
     !request_next_batch.

// Accumulate proposals as they arrive
+propose(StationId, Cost)[source(Sender)]
  <- .self(Me);
     // Note: Jason plan context reads from message mailbox, not belief base
     .print("Proposal from ", StationId, " cost=", Cost).

// Select minimum-cost proposal
+!select_best_proposal(OrderId, Proposals)
  <- .min_member(Cost-StationId, Proposals, _);
     // Send accept to winner
     .send(StationId, tell, accept_proposal(OrderId));
     // Send reject to all others
     .findall(S, .member(_-S, Proposals) & S \== StationId, Losers);
     .broadcast_to(Losers, tell, reject_proposal(OrderId, "not_selected"));
     !await_station_start(OrderId, StationId).

+!await_station_start(OrderId, StationId)
  <- .wait(inform_start(StationId)[source(StationId)], 30000, _);
     .print("Order ", OrderId, " started at ", StationId);
     !request_transport(OrderId, StationId, next_station(StationId)).

// ── Transport coordination ───────────────────────────────────────────────
+!request_transport(OrderId, From, To)
  <- .send(amr_1, tell, transport_request(OrderId, From, To));
     .wait(transport_complete(OrderId)[source(_)], 60000, TimedOut);
     (TimedOut ->
         .print("Transport timeout for ", OrderId)
      ;
         !request_next_batch
     ).
```

#### [NEW] `src/ag/resource_holon.asl`

Implements the CNP reservation state machine from doc3 §2.2 exactly.

```jason
// ── Initialization ──────────────────────────────────────────────────────
!start.

+!start
  <- ?station_id(SId);
     .concat("S", SId, StationName);
     +my_station(StationName);
     -+station_state(idle);
     .print("Resource Holon started for station ", StationName).

// ── CNP Responder ────────────────────────────────────────────────────────

// Respond to CFP only when idle
+cfp(Step, Stations, OrderId)[source(Sender)]
  : station_state(idle) & .member(MySt, Stations) & my_station(MySt)
  <- ?current_processing_cost(Cost);
     -+station_state(provisional_lock(OrderId));
     .send(Sender, tell, propose(MySt, Cost));
     startTimer(OrderId, 5000, me).   // 5s simulated TTL via TimerArtifact NER

// Ignore CFP when not idle
+cfp(_, _, _)[source(_)]
  : not station_state(idle)
  <- true.

// Retrieve cost from artifact observable property (station processing time estimate)
+?current_processing_cost(Cost)
  <- ?station_t_mean(Cost).

// ── Accept Proposal ──────────────────────────────────────────────────────

// IMPORTANT: Assert busy_processing FIRST to block timer_expired race (doc3 §2.2)
+accept_proposal(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId))
  <- cancelTimer(OrderId);
     -+station_state(busy_processing(OrderId));
     .send(Sender, tell, inform_start(me));
     !execute_physical_operation(OrderId).

// Catch-all: lock expired or superseded before accept arrived
+accept_proposal(OrderId)[source(Sender)]
  : not station_state(provisional_lock(OrderId))
  <- .send(Sender, tell, reject_proposal(me, "lock_expired_or_superseded")).

// ── TTL Expiry ───────────────────────────────────────────────────────────
+timer_expired(OrderId)
  : station_state(provisional_lock(OrderId))
  <- -+station_state(idle);
     .print("Provisional lock expired for order ", OrderId).

// Already transitioned — discard stale timer event
+timer_expired(OrderId)
  : not station_state(provisional_lock(OrderId))
  <- true.

// ── Physical Operation ───────────────────────────────────────────────────
+!execute_physical_operation(OrderId)
  : station_state(busy_processing(OrderId)) & my_station(SId)
  <- processOrder(OrderId, ResultCode);   // @OPERATION on BaseStationArtifact/TestBenchArtifact
     (ResultCode == "defect" ->
         .print("Defect detected for order ", OrderId, " at ", SId);
         !report_defect(OrderId)
      ;
         .print("Order ", OrderId, " processed OK at ", SId)
     );
     -+station_state(idle).

+!report_defect(OrderId)
  <- recordBatch(OrderId, me, 0.0, 0.0, false);   // DatabaseArtifact
     .broadcast(tell, defect_report(OrderId, me)).
```

#### [NEW] `src/ag/amr_agent.asl`

```jason
!start.

+!start
  <- ?amr_id(Id);
     +my_amr_id(Id);
     -+amr_status(idle);
     .print("AMR agent started: ", Id).

// ── Transport Assignment ─────────────────────────────────────────────────
+transport_request(OrderId, From, To)[source(Requester)]
  : amr_status(idle)
  <- -+amr_status(transporting(OrderId));
     !plan_route(OrderId, From, To, Requester).

// Busy — reject
+transport_request(OrderId, _, _)[source(Requester)]
  : not amr_status(idle)
  <- .send(Requester, tell, transport_rejected(OrderId, "amr_busy")).

// ── Route Planning ───────────────────────────────────────────────────────
+!plan_route(OrderId, From, To, Requester)
  <- !compute_trajectory(From, To, Traj);
     reserveTrajectory(Traj, ReservationResult);
     (ReservationResult == "granted" ->
         !execute_transport(OrderId, Traj, Requester)
      ;
         !handle_transport_blocked(OrderId, From, To, Requester)
     ).

+!compute_trajectory(From, To, Traj)
  <- // Simple Manhattan path for Phase 2; A* pathfinding in Phase 4
     .term2string(From, FromStr);
     .term2string(To, ToStr);
     .concat(FromStr, "->", ToStr, PathStr);
     Traj = [From, To].   // Simplified for Phase 2

// ── Blocked handling (doc3 §2.3 grid saturation) ────────────────────────
+!handle_transport_blocked(OrderId, From, To, Requester)
  <- getGridUtilization(Util);
     (Util > 0.85 ->
         .print("Grid saturated (", Util, "), waiting for clearance");
         .wait(2000);
         !plan_route(OrderId, From, To, Requester)
      ;
         .wait(500);
         !plan_route(OrderId, From, To, Requester)
     ).

// ── Transport Execution ──────────────────────────────────────────────────
+!execute_transport(OrderId, Traj, Requester)
  <- .print("Executing transport for ", OrderId);
     .wait(3000);   // Simulated transit time — Phase 4: NER-coordinated
     -+amr_status(idle);
     .send(Requester, tell, transport_complete(OrderId)).
```

---

### Component F: MoISE Organizational Specification

Phase 2 uses **centralized organizational schema only**. PROSA holonic and ADACOR adaptive schemas are introduced in Phase 3.

#### [NEW] `src/org/centralized_org.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<organisational-specification
    id="factory_centralized"
    xmlns="http://moise.sourceforge.net/os"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://moise.sourceforge.net/os
                        http://moise.sourceforge.net/xml/os.xsd">

    <!-- ── Structural Specification ─────────────────────────────────── -->
    <structural-specification>
        <role-definitions>
            <role id="order_manager"      />   <!-- CNP initiator -->
            <role id="station_operator"   />   <!-- CNP responder, resource holon -->
            <role id="transport_coordinator" /><!-- AMR routing agent -->
        </role-definitions>

        <group-specification id="production_line">
            <roles>
                <role id="order_manager"        min="1" max="1" />
                <role id="station_operator"     min="5" max="5" />
                <role id="transport_coordinator" min="1" max="4" />
            </roles>
            <links>
                <link from="order_manager"     to="station_operator"      type="authority" />
                <link from="order_manager"     to="transport_coordinator" type="authority" />
            </links>
        </group-specification>
    </structural-specification>

    <!-- ── Functional Specification ─────────────────────────────────── -->
    <functional-specification>
        <scheme id="production_scheme">
            <goal id="produce_batch" ttf="3600000">  <!-- 1h simulated TTF -->
                <plan operator="sequence">
                    <goal id="negotiate_station"  ttf="30000"  />  <!-- 30s -->
                    <goal id="process_at_station" ttf="600000" />  <!-- 10m max -->
                    <goal id="transport_to_next"  ttf="120000" />  <!-- 2m -->
                    <goal id="run_end_of_line_test" ttf="180000"/> <!-- 3m -->
                </plan>
            </goal>
        </scheme>
    </functional-specification>

    <!-- ── Normative Specification ───────────────────────────────────── -->
    <normative-specification>
        <norm id="station_must_respond_to_cfp"
              type="obligation"
              role="station_operator"
              mission="mProduceAtStation"
              time-constraint="40000" />   <!-- 40s deadline on CNP response -->
    </normative-specification>

</organisational-specification>
```

---

## Execution Order

```
Component A ──► Component B ──► Component C ──► Component D ──► Component E ──► Component F
(Gradle/proto)  (Java core)     (Infra arts)    (Floor arts)    (Jason ASL)     (MoISE XML)
    │
    ▼ first
  ./gradlew generateProto
  (verify: SimBridgeGrpc, TelemetryFrame, AMRState, StationState all generated)
    │
    ▼
  Implement B (ProtoIndex → StationSummary/AMRSnapshot records → GrpcClientBridge → MainSimulator)
    │
    ▼
  Implement C in parallel:
     TimerArtifact  ─┐
     EnergyPriceArt ─┤── all independent of each other
     DatabaseArtifact┤
     TelemetryArtifact
     UtilitySystemArt
    │
    ▼
  Implement D (depends on B's GrpcClientBridge, C's TimerArtifact for cancel ops):
     BaseStationArtifact (no gRPC)
     TestBenchArtifact   (needs GrpcClientBridge.getChannel())
     AMRArtifact         (independent)
    │
    ▼
  Implement E (depends on D's artifact @OPERATION names being final)
     order_holon.asl → resource_holon.asl → amr_agent.asl
    │
    ▼
  Implement F (depends on E's agent role assignments being stable)
     centralized_org.xml → factory.jcm
```

---

## File Manifest (Phase 2)

| Status | File | Component |
|--------|------|-----------|
| NEW | `settings.gradle` | A |
| NEW | `build.gradle` | A |
| NEW | `factory.jcm` | A |
| NEW | `src/java/factory/TelemetryFrameSnapshot.java` | B |
| NEW | `src/java/factory/NEREntry.java` | B |
| NEW | `src/java/factory/StationSummary.java` | B |
| NEW | `src/java/factory/AMRSnapshot.java` | B |
| NEW | `src/java/factory/ProtoIndex.java` | B |
| NEW | `src/java/factory/GrpcClientBridge.java` | B |
| NEW | `src/java/factory/MainSimulator.java` | B |
| NEW | `src/env/factory/TimerArtifact.java` | C |
| NEW | `src/env/factory/EnergyPriceArtifact.java` | C |
| NEW | `src/env/factory/DatabaseArtifact.java` | C |
| NEW | `src/env/factory/TelemetryArtifact.java` | C |
| NEW | `src/env/factory/UtilitySystemArtifact.java` | C |
| NEW | `src/env/factory/BaseStationArtifact.java` | D |
| NEW | `src/env/factory/TestBenchArtifact.java` | D |
| NEW | `src/env/factory/AMRArtifact.java` | D |
| NEW | `src/ag/order_holon.asl` | E |
| NEW | `src/ag/resource_holon.asl` | E |
| NEW | `src/ag/amr_agent.asl` | E |
| NEW | `src/org/centralized_org.xml` | F |

**Total: 22 new files.** No existing files modified in Phase 2 (all Phase 1 files remain unchanged).

---

## Verification Plan

### Prerequisites

Before running any JVM code:
```bash
# Python daemon must be running from Phase 1
cd physical_engine
python server.py --port 50051 &

# Verify it is ready
python -c "
import grpc, time
from protos import sim_bridge_pb2 as pb, sim_bridge_pb2_grpc as grpc_mod
ch = grpc.insecure_channel('localhost:50051')
stub = grpc_mod.SimBridgeStub(ch)
for _ in range(10):
    try:
        resp = stub.HealthCheck(pb.Empty())
        if resp.ready:
            print('Daemon ready'); break
    except:
        pass
    time.sleep(0.5)
"

# Build and generate protos
./gradlew generateProto
./gradlew compileJava
```

### Step-by-Step Verification (matches doc5 Phase 2 success criteria)

#### V1 — Proto generation and ProtoIndex validation

```bash
# Verify all expected classes are generated
ls build/generated/source/proto/main/java/factory/
# Must include: SimBridgeGrpc.java, TelemetryFrame.java, AMRState.java, StationState.java

# Compile and run ProtoIndex self-check
./gradlew run --args="--validate-only"
# MainSimulator should call ProtoIndex.validateVectorLength() against the running daemon
# and print: "ProtoIndex validated: VECTOR_LENGTH=9 matches daemon state_vector"
```

#### V2 — HealthCheck polling loop

```bash
# Start JVM — should poll at 500ms and proceed automatically when daemon is ready
./gradlew run
# Expected log output:
# [MainSimulator] HealthCheck poll #1: ready=false (t=0.5s)
# [MainSimulator] HealthCheck poll #N: ready=true — proceeding to simulation
```

Kill the Python daemon mid-poll to verify the loop does not use exponential backoff:
```bash
kill $DAEMON_PID; sleep 2; python server.py &
# JVM should continue polling at exactly 500ms intervals; no stall or crash
```

#### V3 — AdvanceTime integration tick

```bash
./gradlew run --args="--max-ticks=5"
# Expected for each tick:
# [MainSimulator] AdvanceTime(t=0.0, dt=1.0, epoch=0) → StepReady(t=1.0, success=true)
# [MainSimulator] state_vector[STACK_VOLTAGE_V] = <numeric value>
# [MainSimulator] TelemetryFrame seq=1 assembled (sim_t=1.0)
```

#### V4 — NER quorum

Add temporary instrumentation to `MainSimulator`:
```bash
./gradlew run --args="--max-ticks=10 --log-ner"
# Every tick must log:
# [TMC] NER quorum: 8/8 agents responded for tick t=N
# dropped_NER_count must remain 0 under normal conditions
```

Inject one agent with a deliberately slow NER (artificial 2s sleep in `order_holon.asl`) and verify:
```bash
# [TMC] NER quorum timed out: 7/8 agents, dropped_NER_count=1 — proceeding
```

#### V5 — CNP negotiation (one order, one station)

```bash
./gradlew run --args="--max-orders=1 --stations=S1"
# Expected:
# [order_manager] Initiating CNP for order <uuid>
# [station_1]     Received CFP, proposing cost=45.0
# [order_manager] Received proposal from S1, cost=45.0 — accepting
# [station_1]     Accepted, transitioning PROVISIONAL_LOCK → BUSY_PROCESSING
# [station_1]     Order <uuid> processed OK at S1
# [station_1]     Transitioning BUSY_PROCESSING → IDLE
```

Check `StationSummary` publication is visible to `MainSimulator`:
```bash
# TelemetryFrame should show S1 in STATION_BUSY_PROCESSING for intermediate ticks
# and STATION_IDLE after completion
```

#### V6 — TestBenchArtifact async gRPC

```bash
./gradlew run --args="--single-station=S5 --stack-id=STACK-001 --num-cells=85"
# Expected:
# [test_bench]    Dispatching RunBatchTest(stackId=STACK-001, numCells=85)
# [test_bench]    await(corrId, 30000) — suspending
# [Python daemon] RunBatchTest received, running Newton-Raphson for 12 points
# [test_bench]    onMessage: passed=true, failure_flags=0x0
# [test_bench]    resume(corrId) — CArtAgO thread woken
# [station_5]     StationSummary → STATION_IDLE
```

Inject `getRunBatchTestMethod()` with an artificial 31s timeout (past the 30s watchdog):
```bash
# [test_bench] await timeout after 30000ms — resuming with SOLVER_DID_NOT_CONVERGE flag
# [Jason]      test failure handled by contingency plan in resource_holon
```

#### V7 — TelemetryArtifact WebSocket delivery

```bash
# In a browser console, open the dashboard (Phase 4 full HTML) or a minimal test page:
ws = new WebSocket("ws://127.0.0.1:8080")
ws.binaryType = "arraybuffer"
ws.onmessage = e => {
    const frame = TelemetryFrame.decode(new Uint8Array(e.data))
    console.log("seq=" + frame.sequenceNumber + " sim_t=" + frame.simTimeS)
}
# Verify frames arrive at 15-20Hz (1 per ~50-67ms)
# Verify sequence numbers increment monotonically with no gaps under normal conditions
```

Throttle the browser network (Chrome DevTools → Network → Slow 3G) and verify:
```bash
# TelemetryArtifact log: droppedTelemetryFrameCount incrementing
# lastPublishedSimTimeS NOT advancing during throttle
# Frame delivery resumes cleanly when throttle lifted (no deadlock, no stall)
```

Verify inbound frame rejection:
```bash
ws.send("hello")
# WebSocket should close with code 1003 immediately
```

#### V8 — DatabaseArtifact write throughput and backpressure

```bash
./gradlew run --args="--burst-mode --records=500000"
# Push 500k batch records in rapid succession
# Expected:
# [database] queue occupancy rising...
# [database] SIGNAL database_backpressure (queue > 297,000)
# [database] WAL drain in progress (adaptive batch size)
# [database] SIGNAL database_pressure_normal (queue < 3,000)
# No records lost (verify SQLite row count = 500,000)
```

#### V9 — TimerArtifact TTL expiry vs accept_proposal race

This is the most critical correctness test for Phase 2:

```bash
./gradlew run --args="--cnp-slow-accept --ttl=2000"
# Configure order_holon to delay sending accept_proposal by 3 seconds (past the 2s TTL)
# Expected:
# [station_1]  provisional_lock(OrderId) asserted
# [timer]      timer_expired(OrderId) fired at sim_t=2s
# [station_1]  timer_expired plan: reverts to IDLE
# [order_holon] accept_proposal delivered at sim_t=3s
# [station_1]  catch-all rejection plan fires (lock_expired_or_superseded)
# TelemetryFrame shows S1 IDLE (not stuck in PROVISIONAL_LOCK)
```

Also test the accept-arrives-just-before-timer race:
```bash
# Configure accept to arrive at sim_t=1.9s, TTL=2s
# Expected:
# [station_1]  accept_proposal received, busy_processing asserted FIRST
# [timer]      timer_expired(OrderId) fires at sim_t=2s
# [station_1]  timer_expired guard fails (station_state != provisional_lock) — NOP
# TelemetryFrame shows S1 BUSY_PROCESSING — no premature IDLE transition
```

#### V10 — Phase 2 checklist (doc5 success criteria mapping)

| Criterion | Test | Pass Condition |
|-----------|------|----------------|
| Python daemon bootstraps with background warmup thread | V2 | HealthCheck returns `ready=false` then `ready=true` |
| JVM HealthCheck polls at fixed 500ms interval | V2 | Logs show 500ms cadence |
| CArtAgO artifacts use `resume()` from Netty NIO callbacks | V6 | Sub-millisecond wakeup, no polling loop |
| `TestBenchArtifact` prevents orphaned streams via correlation UUIDs | V6 | Each `corrId` cleaned up on success, timeout, and ADACOR cancel |
| `TelemetryArtifact` decimates at 15-20Hz, advances `lastPublishedSimTimeS` only on confirmed delivery | V7 | Network throttle test confirms `droppedTelemetryFrameCount++`, `lastPublished` freeze |
| `TelemetryArtifact` uses non-blocking WebSocket I/O | V7 | No consumer thread stall under throttle |
| TMC enforces deterministic NER quorum | V4 | `dropped_NER_count` observable, no wall-clock dependency |
| Binary Protobuf over WebSocket (no JSON re-encoding) | V7 | Browser receives `ArrayBuffer`, decoded by protobufjs |
| Zero additional read-locks on Python daemon from telemetry path | Architecture | `TelemetryArtifact` reads only `AtomicReference` — no gRPC calls |
| `dropped_telemetry_frame_count` metric exposed | V7 | Present in `TelemetryFrame.dropped_telemetry_frame_count` field |

> [!SUCCESS]
> Phase 2 is complete when all 10 verification steps pass and the 10-row checklist
> is green. At that point, the JVM cognitive layer is fully coupled to the Python
> physical engine, agents negotiate manufacturing tasks via CNP, the timer system
> is simulation-clock-pure, and the browser receives live binary telemetry at 15–20 Hz.
> Proceed to **Phase 3: PROSA holonic schemas, ADACOR adaptive reconfiguration,
> and the two-phase commit organizational transition protocol**.
