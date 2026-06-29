# Phase 3: Organizational Flexibility (PROSA vs. ADACOR) — Implementation Plan

## Background

Phase 2 delivered the complete JVM cognitive layer: all eight CArtAgO artifacts
(`TimerArtifact`, `EnergyPriceArtifact`, `DatabaseArtifact`, `TelemetryArtifact`,
`UtilitySystemArtifact`, `BaseStationArtifact`, `TestBenchArtifact`, `AMRArtifact`),
three Jason agents (`order_holon`, `resource_holon`, `amr_agent`) negotiating manufacturing
tasks via CNP under `centralized_org.xml`, a simulation-clock-pure NER quorum-based TMC, and
live binary Protobuf telemetry at 15–20 Hz. All 10 Phase 2 verification steps pass. The
`TelemetryFrame` proto already reserves `schema_epoch` (field 3) and `active_org_schema`
(field 4) per doc6 §3.1; both were populated as static constants (`0` / `"centralized"`) in
Phase 2. Phase 3 makes them live.

Phase 3 introduces **organizational flexibility**: the factory must operate under two distinct
multi-agent structural blueprints — **PROSA holonic** (fully decentralized, multiple concurrent
Order Holons self-organizing via CNP) and **ADACOR adaptive** (supervisor-coordinated,
dynamically reconfigured on energy price disturbances) — and must transition between them under
a two-phase commit protocol without stranding batches or deadlocking the production floor.

No Phase 1 or Phase 2 Python files are touched. No Protobuf field numbers are renumbered or
removed. Phase 3 is additive except for targeted modifications to six existing Java/ASL/JCM
files listed in the File Manifest.

### Strategic Constraints (Carried from Phases 1 & 2 + New for Phase 3)

| # | Constraint | Impact |
|---|-----------|--------|
| 1 | **All Phase 1 & 2 constraints remain in force** | See Phase 2 constraint table; no relaxation |
| 2 | **No wall-clock timers in Phase 0 / Phase 1 escrow** | `TTL_phase0 = 15 000` ms and `TTL_phase1 = 10 000` ms must use `TimerArtifact` NER queue entries — `ScheduledExecutorService` is forbidden |
| 3 | **`reservation_registry` is the sole abort authority** | Phase 0 timeout escrow sends `abort_current_operation(OrderId)` to BOTH the registered Order Holon and Resource Holon via Jason `.send()` in `supervisor_agent.asl` — Java artifact broadcast helpers are forbidden |
| 4 | **`abort_current_operation` plan must carry identity guard** | `+abort_current_operation(OrderId) : station_state(provisional_lock(OrderId))` — prevents corrupting a newer lock acquired after natural revert |
| 5 | **`schema_epoch` is captured before the RPC call** | `int currentEpoch = schemaEpoch.get()` must be captured once per tick and passed to both `AdvanceTime` and `TelemetryFrame` using the same local variable — never two separate `schemaEpoch.get()` reads |
| 6 | **`EnergyPriceArtifact.updatePrice(simTime)` only — no executor** | Called by `MainSimulator` at each TAG; `ScheduledExecutorService` and wall-clock polling are forbidden |
| 7 | **PROSA operates with multiple concurrent Order Holons** | Five Order Holon instances run simultaneously; the supervisor spawns/reaps via `.create_agent` / `.kill_agent`; the static JCM pre-declares five for Phase 3 |
| 8 | **AMR un-suspend trigger is symmetric and non-storm** | When `getGridUtilization() < 0.60`, the supervisor un-suspends exactly the holons stored in `suspended_holons(List)` — not a blind broadcast |
| 9 | **`active_org_schema` and `schema_epoch` in `TelemetryFrame` are live** | `MainSimulator` sets both from captured-local state on every tick; browser HUD reflects changes within one decimation interval |
| 10 | **Simulation time is read via `getSimTime()` @OPERATION only** | Publishing `sim_time_s` as a continuous observable generates belief-revision events at tick rate, overloading the BDI inference cycle (doc5); the supervisor fetches time synchronously when needed |
| 11 | **`TestBenchArtifact.cancelPendingRpc()` wired to `abortOperation`** | ADACOR Phase 1 issues `.drop_intention(executeTest)` to `station_5`; the artifact's `abortOperation` override calls `cancelPendingRpc()` to prevent orphaned gRPC streams |

---

## Proposed Changes

The work is organized into six components, ordered by dependency.

---

### Component A: Java Value Types (New Supporting Records)

Zero runtime logic — defines the immutable types required by `MainSimulator` and
`SupervisorArtifact` before either can be compiled.

#### [NEW] `src/java/factory/OrgSchemaTransition.java`

Immutable value type capturing the full state of an in-flight schema transition. Includes the
`TransitionPhase` enum as a nested type to minimize class count.

```java
package factory;

/**
 * Immutable snapshot of an in-flight organizational schema transition.
 * Written by MainSimulator.beginTransition() / commitTransition();
 * read by the tick loop for TelemetryFrame assembly and logging.
 * null → no transition currently in progress.
 */
public record OrgSchemaTransition(
    String          targetSchema,       // "prosa" or "adacor"
    int             newEpoch,           // schemaEpoch value applied at COMMITTED
    double          phaseStartSimTimeS, // Simulated time when current phase began
    TransitionPhase phase
) {
    public enum TransitionPhase {
        /** Phase 0: draining active negotiations; abort escrow armed. */
        DRAIN,
        /** Phase 1: suspend_intentions broadcast; force_commit deadline active. */
        SUSPEND,
        /** Transition committed; new schema active; epoch incremented. */
        COMMITTED
    }

    public static OrgSchemaTransition startDrain(String targetSchema, int newEpoch,
                                                  double simTimeS) {
        return new OrgSchemaTransition(targetSchema, newEpoch, simTimeS,
                                       TransitionPhase.DRAIN);
    }

    public OrgSchemaTransition advanceTo(TransitionPhase next, double simTimeS) {
        return new OrgSchemaTransition(targetSchema, newEpoch, simTimeS, next);
    }
}
```

---

### Component B: MainSimulator Schema Epoch & Transition Hooks

Targeted extensions to `MainSimulator.java`. The tick loop structure, NER quorum logic, and
`StepReady` processing from Phase 2 are unchanged.

#### [MODIFIED] `src/java/factory/MainSimulator.java`

**New fields:**

```java
// ── Organizational state ─────────────────────────────────────────────────

/** Monotonically increasing. Never resets within a simulation run. */
private final AtomicInteger schemaEpoch = new AtomicInteger(0);

/**
 * Active organizational schema name.
 * Volatile for wait-free reads on the tick loop thread.
 * Valid values: "centralized" | "prosa" | "adacor"
 */
private volatile String activeOrgSchema = "centralized";

/**
 * In-flight transition descriptor. null when quiescent.
 * Written by SupervisorArtifact callback (CArtAgO thread);
 * read by tick loop (tick-loop thread). Both accesses are synchronized.
 */
private volatile OrgSchemaTransition activeTransition = null;
```

**Critical fix — epoch capture before RPC dispatch:**

> [!IMPORTANT]
> `commitTransition()` executes on a **CArtAgO operation thread**, which is fully
> asynchronous to the tick loop. If it fires after `AdvanceTime` is dispatched but before
> `TelemetryFrame` is assembled, two separate calls to `schemaEpoch.get()` will return
> different values in the same tick. The `TelemetryFrame` would then carry the *new* epoch
> while its embedded `state_vector` was computed under the *old* epoch — violating doc1's
> Unary Synchronization Barrier and the doc6 §7 constraint that frame and RPC epochs must
> be identical. The fix is a single pre-RPC capture used for both the call and the frame.

**Tick loop amendment (replaces the two separate `schemaEpoch.get()` calls):**

```java
// --- Begin tick ---

// Capture epoch ONCE. This local is immutable for the remainder of this tick,
// regardless of any concurrent commitTransition() call on the CArtAgO thread.
final int currentEpoch = schemaEpoch.get();

// 1. Wait for NER quorum (unchanged from Phase 2)
awaitNERQuorum(currentTickTimeout);

// 2. Dispatch AdvanceTime using the captured epoch
StepReady ready = grpcBridge.advanceTime(currentTime, computedDt, currentEpoch);

// 3. Validate state vector on first tick (unchanged from Phase 2)

// 4. Assemble TelemetryFrame using the SAME captured epoch (not schemaEpoch.get())
TelemetryFrame.Builder frameBuilder = TelemetryFrame.newBuilder()
    .setSequenceNumber(++sequenceNumber)
    .setSimTimeS(ready.getTargetTime())
    .setSchemaEpoch(currentEpoch)           // ← captured local, not schemaEpoch.get()
    .setActiveOrgSchema(activeOrgSchema)    // volatile read; consistent with epoch
    // ... remaining fields unchanged from Phase 2 ...
    ;

// 5. Clear any COMMITTED transition descriptor after the frame is assembled
clearCommittedTransition();

// --- End tick ---
```

**Transition callbacks (invoked by `SupervisorArtifact`):**

These are `public synchronized` to be safe across the CArtAgO operation thread and the tick
loop thread. The tick loop reads `schemaEpoch` and `activeOrgSchema` via a pre-capture
(`currentEpoch`) and a volatile read respectively, so neither is blocked by the `synchronized`
monitor held during these callbacks.

```java
public synchronized OrgSchemaTransition beginTransition(String targetSchema,
                                                         double currentSimTimeS) {
    int nextEpoch = schemaEpoch.get() + 1;  // Reserved; not yet applied
    OrgSchemaTransition t = OrgSchemaTransition.startDrain(targetSchema, nextEpoch,
                                                            currentSimTimeS);
    activeTransition = t;
    return t;
}

public synchronized void commitTransition(OrgSchemaTransition t) {
    schemaEpoch.set(t.newEpoch());       // Atomic apply
    activeOrgSchema = t.targetSchema();  // Volatile write
    activeTransition = t.advanceTo(OrgSchemaTransition.TransitionPhase.COMMITTED,
                                    Double.NaN);
    // Cleared on the next tick after the COMMITTED TelemetryFrame is emitted.
}

public synchronized void clearCommittedTransition() {
    if (activeTransition != null
            && activeTransition.phase() == OrgSchemaTransition.TransitionPhase.COMMITTED) {
        activeTransition = null;
    }
}
```

**`MainSimulator` reference injection into `SupervisorArtifact`:**

```java
// In MainSimulator.main(), before the tick loop starts:
SupervisorArtifact supervisorArt = (SupervisorArtifact)
    workspace.getArtifact("supervisor_artifact");
supervisorArt.setMainSimulator(this);
```

---

### Component C: SupervisorArtifact (New CArtAgO Artifact)

The `SupervisorArtifact` is a **pure data artifact**. It owns the `reservation_registry` and
exposes query/mutation operations to the `supervisor_agent.asl`. It does **not** broadcast
messages to other agents — that responsibility belongs entirely to the Jason agent layer,
which uses `.send()` directly.

> [!IMPORTANT]
> **No `execInternalOp` broadcasts.** CArtAgO's `execInternalOp` enqueues a method call on
> the artifact's own internal operation thread; it has no path to any Jason agent's mailbox.
> There is no `@INTERNAL_OPERATION send_abort` or `send_suspend` defined anywhere in the
> codebase. Calling `execInternalOp("send_abort", ...)` would throw `NoSuchOperationException`
> at runtime. All inter-agent messaging is the responsibility of `supervisor_agent.asl` using
> Jason's `.send()` primitive, which is the correct and only supported mechanism.

#### [NEW] `src/env/factory/SupervisorArtifact.java`

```java
package factory;

import cartago.*;
import java.util.concurrent.ConcurrentHashMap;

public class SupervisorArtifact extends Artifact {

    /**
     * Maps OrderId (UUID string) → LockEntry(StationId, OrderHolonName).
     *
     * Populated by Resource Holons on accept_proposal (transition to busy_processing),
     * so the supervisor knows which agent pair to abort or monitor.
     * The station agent name and order holon name are stored as atoms (un-quoted),
     * enabling direct use in Jason .send() calls and list membership checks.
     */
    private final ConcurrentHashMap<String, LockEntry> reservationRegistry =
        new ConcurrentHashMap<>();

    private record LockEntry(String stationAgentName, String orderHolonName) {}

    private MainSimulator mainSimulator;

    /** Injected by MainSimulator before the tick loop starts. Not an @OPERATION. */
    public void setMainSimulator(MainSimulator ms) {
        this.mainSimulator = ms;
    }

    // ── Lock Registry Operations ─────────────────────────────────────────

    /**
     * Register a confirmed lock when a Resource Holon transitions to busy_processing.
     *
     * Called from resource_holon.asl's accept_proposal plan with three arguments:
     *   - orderId:        the stable UUID from the CFP (quoted Jason string)
     *   - stationName:    the Resource Holon's agent name atom (e.g., station_1)
     *   - orderHolonName: the Order Holon's agent name atom (e.g., order_2)
     *
     * Storing the order holon name eliminates the need to derive it from the UUID
     * and prevents the type-mismatch that would cause the grid-saturation filter to
     * incorrectly suspend all order holons (including those with active locks).
     */
    @OPERATION
    void registerLock(String orderId, String stationName, String orderHolonName) {
        reservationRegistry.put(orderId, new LockEntry(stationName, orderHolonName));
        log("Registry: registered " + orderId + " → [" + stationName
            + ", " + orderHolonName + "]");
    }

    /**
     * Remove a lock on normal completion, defect, abort, or TTL expiry.
     * Idempotent — safe to call even if the orderId is no longer present.
     */
    @OPERATION
    void releaseLock(String orderId) {
        reservationRegistry.remove(orderId);
        log("Registry: released " + orderId);
    }

    /**
     * Returns the current registry snapshot as a Jason list of
     * lock(OrderId, StationAgentName, OrderHolonName) terms.
     *
     * Term format:
     *   lock("f3a1-uuid", station_1, order_2)
     *   ┌── quoted string: UUID may contain hyphens (invalid atom characters)
     *                        └── unquoted atoms: valid Jason identifiers
     *
     * Caller (supervisor_agent) uses this to:
     *   1. Grid saturation: filter Order Holons NOT in any lock → low-priority candidates
     *   2. Phase 0 abort:   extract (StationName, OrderHolonName) pairs for .send() dispatch
     */
    @OPERATION
    void getActiveLocks(OpFeedbackParam locks) {
        StringBuilder sb = new StringBuilder("[");
        reservationRegistry.forEach((oid, entry) ->
            sb.append("lock(\"").append(oid).append("\",")
              .append(entry.stationAgentName()).append(",")    // unquoted atom
              .append(entry.orderHolonName()).append("),")     // unquoted atom
        );
        if (sb.length() > 1 && sb.charAt(sb.length() - 1) == ',') {
            sb.deleteCharAt(sb.length() - 1);
        }
        sb.append("]");
        locks.set(sb.toString());
    }

    // ── Transition Operations ─────────────────────────────────────────────

    /**
     * Begins Phase 0 of the two-phase commit. Calls MainSimulator.beginTransition()
     * to reserve the next epoch. Returns the reserved epoch number for the supervisor
     * to log and later verify at commit.
     */
    @OPERATION
    void initiateTransition(String targetSchema, double currentSimTimeS,
                            OpFeedbackParam reservedEpoch) {
        OrgSchemaTransition t = mainSimulator.beginTransition(targetSchema, currentSimTimeS);
        reservedEpoch.set(t.newEpoch());
        log("Transition initiated: target=" + targetSchema + " reservedEpoch="
            + t.newEpoch() + " simT=" + currentSimTimeS);
    }

    /**
     * Finalizes the two-phase commit. Calls MainSimulator.commitTransition(), which
     * atomically applies the new epoch and schema name. The very next AdvanceTime
     * RPC and TelemetryFrame will carry the new values.
     */
    @OPERATION
    void commitTransition(double currentSimTimeS) {
        OrgSchemaTransition t = mainSimulator.activeTransition;
        if (t == null || t.phase() == OrgSchemaTransition.TransitionPhase.COMMITTED) {
            log("commitTransition called with no active transition — ignoring");
            return;
        }
        mainSimulator.commitTransition(
            t.advanceTo(OrgSchemaTransition.TransitionPhase.COMMITTED, currentSimTimeS));
        log("Transition committed: schema=" + t.targetSchema()
            + " epoch=" + t.newEpoch() + " simT=" + currentSimTimeS);
    }
}
```

---

### Component D: Modified Infrastructure & Floor Artifacts

Four existing artifacts from Phase 2 require targeted modifications.

#### [MODIFIED] `src/env/factory/UtilitySystemArtifact.java`

Adds a synchronous `getSimTime()` `@OPERATION` so the supervisor agent can read the current
simulation time on demand without requiring a continuous observable.

> [!IMPORTANT]
> **Do not publish `sim_time_s` as a continuous observable property.** Updating an observable
> at tick rate (15–20 Hz) generates a belief-revision event in every focusing agent's BDI
> cycle on every tick. For the supervisor agent alone — which has multiple plans — this
> produces 15–20 inference cycles per second triggered solely by time updates, directly
> causing the "BDI Inference Overload" risk itemized in doc5 §2. The supervisor fetches time
> only when a plan needs it, via `getSimTime(SimT)`, which is a synchronous artifact query
> with zero observable side-effects.

**New field and method (additions only; Phase 2 content unchanged):**

```java
/** Updated by MainSimulator at each TAG via updateFromStateVector(). */
private volatile double currentSimTimeS = 0.0;

/**
 * Called by MainSimulator (not an @OPERATION) to update all observable properties
 * and the internal simulation time reference.
 * Signature extended from Phase 2 to accept simTimeS.
 */
public void updateFromStateVector(double[] sv, double simTimeS) {
    this.currentSimTimeS = simTimeS;
    // ... existing Phase 2 updateObsProperty calls unchanged ...
    updateObsProperty("h2_pressure_bar",    sv[ProtoIndex.H2_TANK_PRESSURE_BAR]);
    updateObsProperty("h2_fill_fraction",   sv[ProtoIndex.H2_TANK_FILL_FRACTION]);
    updateObsProperty("chiller_temp_k",     sv[ProtoIndex.CHILLER_TEMP_K]);
    updateObsProperty("compressor_power_kw",sv[ProtoIndex.COMPRESSOR_POWER_KW]);
}

/**
 * Synchronous simulation-time query. Called by supervisor_agent.asl via
 * getSimTime(SimT) whenever a plan needs to timestamp an event.
 * No observable event is generated; no belief revision occurs.
 */
@OPERATION
void getSimTime(OpFeedbackParam simTime) {
    simTime.set(currentSimTimeS);
}
```

> [!NOTE]
> `updateFromStateVector` gains a second parameter `simTimeS` in Phase 3. Update the call
> site in `MainSimulator.onStepReady()` accordingly:
> `utilitySystemArtifact.updateFromStateVector(stateVector, ready.getTargetTime())`.

#### [MODIFIED] `src/env/factory/EnergyPriceArtifact.java`

Phase 2 implemented the lookup and `updateObsProperty` call. Phase 3 adds threshold-crossing
detection. One Phase 3 note from the prior draft was incorrect and is corrected here.

**New fields:**

```java
private double spikeThresholdEurMwh = 150.0;  // Configurable via price_config.json
private boolean spikeActive = false;           // Hysteresis state
```

**Amended `updatePrice(double simTime)` — additions only:**

```java
public synchronized void updatePrice(double simTime) {
    // ... existing Phase 2 lookup and updateObsProperty("energy_price", ...) ...
    double currentPrice = priceAtSimTime.floorEntry(simTime).getValue();

    if (!spikeActive && currentPrice >= spikeThresholdEurMwh) {
        spikeActive = true;
        defineObsProperty("energy_price_spike", currentPrice);
        signal("energy_price_spike", currentPrice);
        log("Price spike: " + currentPrice + " EUR/MWh at simT=" + simTime);

    } else if (spikeActive && currentPrice < spikeThresholdEurMwh * 0.90) {
        // 10% hysteresis prevents oscillation at the threshold boundary.
        spikeActive = false;
        // No try-catch needed: spikeActive is only ever set true immediately after
        // defineObsProperty succeeds. The else-if guard makes it structurally
        // impossible to reach removeObsProperty when the property does not exist.
        removeObsProperty("energy_price_spike");
        signal("energy_price_normal", currentPrice);
        log("Price normal: " + currentPrice + " EUR/MWh at simT=" + simTime);
    }
}
```

#### [MODIFIED] `src/env/factory/BaseStationArtifact.java`

`releaseStation()` was declared as a stub in Phase 2. Phase 3 provides the complete
implementation with `TimerArtifact` cleanup.

```java
@OPERATION
void releaseStation(String orderId) {
    // Force-reset the volatile publish field so the dashboard's next read
    // sees STATION_IDLE, not a stale PROVISIONAL_LOCK or BUSY_PROCESSING.
    currentSummary = StationSummary.IDLE;

    // Cancel any pending TTL in TimerArtifact for this orderId.
    // execLinkedOp blocks until cancelTimer completes; this is safe because
    // cancelTimer only mutates a PriorityQueue under synchronized(timerQueue)
    // with no RPC or await(), so it returns within microseconds.
    execLinkedOp(timerArtifactId, "cancelTimer", orderId);

    log("Station " + stationId + " released for order " + orderId
        + " — currentSummary reset to IDLE");
}
```

> [!IMPORTANT]
> `releaseStation(OrderId)` **must** be called by `resource_holon.asl` wherever the Jason
> belief state reverts to `idle` without going through the normal `processOrder()` completion
> path — specifically in the `abort_current_operation` plan and in the `timer_expired` plan.
> If only the Jason belief is updated (`-+station_state(idle)`) without calling this
> operation, the volatile `currentSummary` field remains at `STATION_PROVISIONAL_LOCK`,
> and the dashboard's next volatile read will show that station as permanently locked.

#### [MODIFIED] `src/env/factory/TestBenchArtifact.java`

Phase 2 implemented `cancelPendingRpc()` in full. Phase 3 adds the lifecycle hook that wires
`.drop_intention()` to it.

```java
/**
 * Invoked by CArtAgO when Jason calls .drop_intention() on an intention
 * suspended inside this artifact's @OPERATION (e.g., executeTest awaiting gRPC).
 *
 * Without this override, the CArtAgO default is a no-op: the Netty NIO
 * callback will eventually call resume(corrId), find no waiting intention,
 * and leak a signal buffer entry. cancelPendingRpc() prevents this by
 * cancelling the in-flight ClientCall and safely releasing the await.
 *
 * Verify the exact override name against the JaCaMo 1.2 / CArtAgO 3.x
 * Javadoc for cartago.Artifact before deploying. The semantic requirement
 * is invariant: the hook fired by .drop_intention() on a suspended @OPERATION
 * must call cancelPendingRpc().
 */
@Override
protected void abortOperation(IOperation op) {
    log("ADACOR drop_intention received — cancelling pending gRPC call");
    cancelPendingRpc();
    super.abortOperation(op);
}
```

---

### Component E: Jason BDI Agent Updates

#### [NEW] `src/ag/supervisor_agent.asl`

The supervisor monitors energy price disturbances, orchestrates schema transitions, and manages
AMR grid saturation. All inter-agent messaging uses Jason's `.send()` directly — no Java
artifact broadcast helpers exist or are needed.

```jason
// ── Initialization ──────────────────────────────────────────────────────

!start.

+!start
  <- .print("Supervisor agent started");
     +active_schema(prosa);
     +suspended_holons([]);
     !register_active_holons.

+!register_active_holons
  <- +active_order_holons([order_1, order_2, order_3, order_4, order_5]);
     +active_resource_holons([station_1, station_2, station_3, station_4, station_5]);
     +active_transport_holons([amr_1, amr_2]).

// ── Energy Price Disturbance — ADACOR Trigger ────────────────────────────

+energy_price_spike(Price)[artifact_name("energy_price")]
  : active_schema(prosa) & not pending_transition(_, _)
  <- .print("Energy spike: ", Price, " EUR/MWh — initiating ADACOR transition");
     getSimTime(SimT);                                   // Synchronous @OPERATION query
     initiateTransition("adacor", SimT, ReservedEpoch);
     +pending_transition(adacor, ReservedEpoch);
     !run_phase0.

+energy_price_spike(_)[artifact_name("energy_price")]
  : active_schema(adacor) | pending_transition(_, _)
  <- true.   // Already in ADACOR or transition in progress — no-op

+energy_price_normal(Price)[artifact_name("energy_price")]
  : active_schema(adacor) & not pending_transition(_, _)
  <- .print("Energy normal: ", Price, " EUR/MWh — reverting to PROSA");
     getSimTime(SimT);
     initiateTransition("prosa", SimT, ReservedEpoch);
     +pending_transition(prosa, ReservedEpoch);
     !run_phase0.

// ── Two-Phase Commit: Phase 0 (Drain Active Negotiations) ────────────────

+!run_phase0
  <- .print("Phase0 DRAIN begin — TTL_phase0=15000ms simulated");
     startTimer("phase0_transition", 15000, self);
     !await_phase0_drain.

+!await_phase0_drain
  <- getActiveLocks(Locks);
     (Locks == [] ->
         cancelTimer("phase0_transition");
         .print("Phase0: all negotiations drained — advancing to Phase1");
         !run_phase1
      ;
         .wait(500);
         !await_phase0_drain
     ).

// Phase 0 TTL expired — compensating abort for all active locks.
// The supervisor iterates the registry directly and sends to each pair.
// No Java broadcast helper is used: .send() in Jason is the correct mechanism.
+timer_expired("phase0_transition")
  <- .print("Phase0 TTL expired — executing compensating abort");
     getActiveLocks(Locks);
     !abort_all_locks(Locks);
     !run_phase1.

+!abort_all_locks([]).
+!abort_all_locks([lock(OrderId, StationName, OrderHolonName)|Rest])
  <- // Send to the Resource Holon: revokes provisional_lock if still held
     .send(StationName,    tell, abort_current_operation(OrderId));
     // Send to the Order Holon: drops awaiting intentions
     .send(OrderHolonName, tell, abort_current_operation(OrderId));
     !abort_all_locks(Rest).

// ── Two-Phase Commit: Phase 1 (Suspend with Timeout) ────────────────────

+!run_phase1
  <- .print("Phase1 SUSPEND begin — TTL_phase1=10000ms simulated");
     ?active_order_holons(Orders);
     ?active_resource_holons(Stations);
     ?active_transport_holons(AMRs);
     .concat(Orders, Stations, All0);
     .concat(All0, AMRs, AllHolons);
     -+suspended_holons(AllHolons);
     // Send suspend_intentions individually via .send() — no broadcast helper.
     !send_suspend_to_all(AllHolons);
     startTimer("phase1_transition", 10000, self);
     !await_phase1_acks(AllHolons).

+!send_suspend_to_all([]).
+!send_suspend_to_all([H|Rest])
  <- .send(H, tell, suspend_intentions);
     !send_suspend_to_all(Rest).

+!await_phase1_acks([])
  <- cancelTimer("phase1_transition");
     .print("Phase1: unanimous ACK — clean commit");
     !do_commit.

+!await_phase1_acks(Pending)
  : Pending \== []
  <- .wait(suspend_ack(Who)[source(_)], 500, TimedOut);
     (TimedOut ->
         !await_phase1_acks(Pending)  // TTL will fire; continue polling
      ;
         .delete(Who, Pending, NewPending);
         !await_phase1_acks(NewPending)
     ).

+timer_expired("phase1_transition")
  <- .print("Phase1 TTL expired — issuing force_commit decree");
     !do_commit.

// ── Commit ───────────────────────────────────────────────────────────────

+!do_commit
  : pending_transition(TargetSchema, Epoch)
  <- getSimTime(SimT);
     commitTransition(SimT);
     -+active_schema(TargetSchema);
     -pending_transition(TargetSchema, Epoch);
     .print("Schema committed: ", TargetSchema, " epoch=", Epoch).

// ── AMR Grid Saturation: Deadlock Resolution (PROSA mode) ────────────────

+transport_blocked(BatchId)[source(_)]
  : active_schema(prosa)
  <- getGridUtilization(Util);
     (Util > 0.85 ->
         .print("Grid saturated (", Util, ") — suspending low-priority Order Holons");
         !suspend_low_priority_holons;
         clearExpiredReservations
      ;
         true
     ).

// Identify Order Holons with NO active lock — lowest priority for suspension.
//
// getActiveLocks returns: [lock(OrderId, StationName, OrderHolonName), ...]
// Orders is a list of agent name atoms: [order_1, order_2, ...]
//
// The filter checks the THIRD element of each lock term (OrderHolonName atom)
// against the agent names in Orders. This is now type-correct because the
// registry explicitly stores the order holon agent name, not the UUID.
+!suspend_low_priority_holons
  <- ?active_order_holons(Orders);
     getActiveLocks(Locks);
     .findall(O,
         (.member(O, Orders) & not .member(lock(_, _, O), Locks)),
         LowPri);
     -+suspended_holons(LowPri);
     !send_suspend_to_all(LowPri).

// Resume suspended holons when grid utilization falls below 0.60.
// Symmetric: un-suspends exactly the holons stored in suspended_holons.
+!check_grid_resume
  : suspended_holons(Suspended) & Suspended \== []
  <- getGridUtilization(Util);
     (Util < 0.60 ->
         .print("Grid normal (", Util, ") — resuming suspended holons");
         !resume_suspended_holons
      ;
         true
     ).

+!resume_suspended_holons
  : suspended_holons(Suspended)
  <- .for_each(.member(H, Suspended), .send(H, tell, resume_intention));
     -+suspended_holons([]).
```

> [!NOTE]
> Every invocation of `getSimTime(SimT)` in `supervisor_agent.asl` performs a synchronous
> artifact query that returns immediately with the `currentSimTimeS` volatile field value.
> It produces zero belief-revision events and zero observable property updates. Plans that
> need simulation time (e.g., `initiateTransition`, `commitTransition`) call it inline.
> No plan is triggered by time changes.

#### [MODIFIED] `src/ag/resource_holon.asl`

Four additions to the Phase 2 plan:

1. **3-arg `registerLock`** after `accept_proposal`, passing the sender's name.
2. **`releaseStation(OrderId)` on every non-normal terminal transition** — `abort_current_operation`, `timer_expired`, and defect path.
3. **`abort_current_operation` plan with identity guard.**
4. **Epoch change detection and `!reinitialize_schema`.**

**Amended `accept_proposal` plan:**

```jason
+accept_proposal(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId))
  <- cancelTimer(OrderId);
     -+station_state(busy_processing(OrderId));
     // Phase 3: register with all three fields so the supervisor's lock filter
     // can correctly identify which Order Holon holds a commitment at this station.
     // Sender is the Order Holon's agent name atom (e.g., order_2) — correct type.
     registerLock(OrderId, me, Sender);
     .send(Sender, tell, inform_start(me));
     !execute_physical_operation(OrderId).
```

**Amended `execute_physical_operation` plan (releaseLock on completion):**

```jason
+!execute_physical_operation(OrderId)
  : station_state(busy_processing(OrderId)) & my_station(SId)
  <- processOrder(OrderId, ResultCode);
     releaseLock(OrderId);        // Remove from registry on normal completion
     (ResultCode == "defect" ->
         releaseStation(OrderId); // Sync artifact volatile field
         !report_defect(OrderId)
      ;
         -+station_state(idle)    // processOrder already set artifact to IDLE on success
     ).
```

**Amended `timer_expired` plan — artifact sync (fixes pre-existing Phase 2 bug):**

```jason
// Station reverts from provisional_lock on TTL expiry.
// releaseStation() is required to sync the Java artifact's volatile currentSummary
// field with the Jason belief revert. Without it, the dashboard reads
// STATION_PROVISIONAL_LOCK indefinitely after the timer fires.
+timer_expired(OrderId)
  : station_state(provisional_lock(OrderId))
  <- -+station_state(idle);
     releaseStation(OrderId);   // Sync artifact volatile field
     // releaseLock is a no-op here: lock is only registered on accept_proposal,
     // which has not yet arrived when the TTL fires (station still in provisional_lock).
     // Calling it anyway is safe (ConcurrentHashMap.remove on absent key is a no-op).
     releaseLock(OrderId);
     .print("Provisional lock expired for order ", OrderId).

+timer_expired(OrderId)
  : not station_state(provisional_lock(OrderId))
  <- true.
```

**New plans (Phase 3 only):**

```jason
// ── Phase 0 Compensating Abort ────────────────────────────────────────────

// Identity guard (doc3 §3.1): fires only if this station holds the lock.
// Prevents corrupting a newer lock if the station naturally reverted first.
+abort_current_operation(OrderId)
  : station_state(provisional_lock(OrderId))
  <- -+station_state(idle);
     releaseStation(OrderId);   // Sync artifact volatile field — dashboard sees IDLE
     releaseLock(OrderId);      // No-op (lock not yet registered); safe to call
     .print("ADACOR Phase0 abort: provisional_lock revoked for ", OrderId).

// Lock already gone (natural revert or different order) — discard abort silently.
+abort_current_operation(OrderId)
  : not station_state(provisional_lock(OrderId))
  <- true.

// ── Phase 1 Suspend ───────────────────────────────────────────────────────

// Resource Holons drop only operations they can actually hold.
// .drop_intention(call_for_proposals) is NOT included: Resource Holons
// respond to CFPs — they never initiate them. That intention belongs to order_holon.asl.
+suspend_intentions[source(supervisor)]
  <- .drop_intention(execute_physical_operation(_));
     .send(supervisor, tell, suspend_ack(me));
     .print("Station ", me, " suspended by ADACOR Phase1").

+resume_intention[source(supervisor)]
  <- !start.

// ── Schema Epoch Validation ───────────────────────────────────────────────

// schema_epoch(E) is published by UtilitySystemArtifact as an observable property
// (updated once per tick alongside h2_pressure_bar etc.).
// Resource Holons hold the epoch in a belief; any change triggers reinitialize.
+schema_epoch(E)[artifact_name("utility_system")]
  : current_epoch(OldE) & E \== OldE
  <- .print("Epoch mismatch: ", OldE, " → ", E, " — reinitializing schema binding");
     -current_epoch(OldE);
     +current_epoch(E);
     !reinitialize_schema.

+!reinitialize_schema
  <- .drop_all_intentions;
     -+station_state(idle);
     !start.
```

> [!NOTE]
> The `schema_epoch` observable property IS appropriate for Resource and Order Holons because
> it changes very rarely (only on schema transitions, not every tick). It is distinct from
> `sim_time_s`, which would change on every tick. Publishing an observable that changes twice
> per simulation run generates two belief-revision events total — negligible BDI overhead.
> The supervisor's time queries use `getSimTime()` (synchronous) precisely to avoid
> registering a continuous high-frequency observable.

#### [MODIFIED] `src/ag/order_holon.asl`

```jason
// ── ADACOR Phase 0 Compensating Abort ────────────────────────────────────

+abort_current_operation(OrderId)
  : my_order_id(OrderId)
  <- .drop_intention(await_station_start(OrderId, _));
     .drop_intention(request_transport(OrderId, _, _));
     .print("ADACOR Phase0 abort: Order Holon dropping intentions for ", OrderId);
     !request_next_batch.

+abort_current_operation(_)   // Different order — ignore
  <- true.

// ── ADACOR Phase 1 Suspend / Resume ──────────────────────────────────────

// Correct placement: Order Holons DO initiate call_for_proposals.
+suspend_intentions[source(supervisor)]
  <- .drop_intention(request_next_batch);
     .drop_intention(call_for_proposals(_, _, _));     // Order Holons initiate CFPs
     .drop_intention(await_station_start(_, _));
     .drop_intention(request_transport(_, _, _));
     .send(supervisor, tell, suspend_ack(me));
     .print("Order Holon ", me, " suspended by ADACOR Phase1").

+resume_intention[source(supervisor)]
  <- !start.

// ── Schema Epoch Validation ───────────────────────────────────────────────

+schema_epoch(E)[artifact_name("utility_system")]
  : current_epoch(OldE) & E \== OldE
  <- -current_epoch(OldE);
     +current_epoch(E);
     .print("Order Holon epoch: ", OldE, " → ", E);
     !reinitialize_schema.

+!reinitialize_schema
  <- .drop_all_intentions;
     !request_next_batch.
```

#### [MODIFIED] `src/ag/amr_agent.asl`

```jason
// ── ADACOR Phase 1 Suspend / Resume ──────────────────────────────────────

+suspend_intentions[source(supervisor)]
  <- .drop_intention(execute_transport(_, _, _));
     .drop_intention(plan_route(_, _, _, _));
     -+amr_status(suspended);
     .send(supervisor, tell, suspend_ack(me)).

+resume_intention[source(supervisor)]
  <- -+amr_status(idle);
     !start.

// ── Grid Saturation Reporting ─────────────────────────────────────────────

// Injected into handle_transport_blocked (Phase 2) to notify the supervisor
// when grid utilization is high, triggering !suspend_low_priority_holons.
+!notify_grid_saturation(OrderId)
  <- getGridUtilization(Util);
     (Util > 0.85 ->
         .send(supervisor, tell, transport_blocked(OrderId))
      ;
         true
     ).
```

---

### Component F: MoISE Organizational Schemas & JCM Amendment

#### [NEW] `src/org/prosa_org.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<organisational-specification
    id="factory_prosa"
    xmlns="http://moise.sourceforge.net/os"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://moise.sourceforge.net/os
                        http://moise.sourceforge.net/xml/os.xsd">

    <structural-specification>
        <role-definitions>
            <role id="order_holon"      />   <!-- Self-organizing product holon -->
            <role id="resource_holon"   />   <!-- Autonomous resource holon -->
            <role id="transport_holon"  />   <!-- AMR routing holon -->
            <role id="prosa_supervisor" />   <!-- Observer; no authority links -->
        </role-definitions>

        <group-specification id="holonic_factory">
            <roles>
                <role id="order_holon"      min="1"  max="10" />
                <role id="resource_holon"   min="5"  max="5"  />
                <role id="transport_holon"  min="1"  max="4"  />
                <role id="prosa_supervisor" min="1"  max="1"  />
            </roles>
            <!-- No authority links: PROSA is peer-to-peer.
                 Holons self-organize via FIPA CNP. -->
            <links>
                <link from="prosa_supervisor" to="order_holon"    type="communication" />
                <link from="prosa_supervisor" to="resource_holon" type="communication" />
            </links>
        </group-specification>
    </structural-specification>

    <functional-specification>
        <scheme id="holonic_production">
            <goal id="produce_batch" ttf="3600000">
                <plan operator="sequence">
                    <goal id="negotiate_resource"   ttf="60000"  />
                    <goal id="process_at_resource"  ttf="600000" />
                    <goal id="transport_to_next"    ttf="120000" />
                    <goal id="run_end_of_line_test" ttf="300000" />
                </plan>
            </goal>
        </scheme>
    </functional-specification>

    <normative-specification>
        <norm id="resource_must_respond_to_cfp"
              type="obligation"
              role="resource_holon"
              mission="mProduceAtResource"
              time-constraint="60000" />
    </normative-specification>

</organisational-specification>
```

#### [NEW] `src/org/adacor_org.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<organisational-specification
    id="factory_adacor"
    xmlns="http://moise.sourceforge.net/os"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://moise.sourceforge.net/os
                        http://moise.sourceforge.net/xml/os.xsd">

    <structural-specification>
        <role-definitions>
            <role id="adacor_supervisor" />
            <role id="task_holon"        />
            <role id="resource_holon"    />
            <role id="transport_holon"   />
        </role-definitions>

        <group-specification id="adaptive_factory">
            <roles>
                <role id="adacor_supervisor" min="1"  max="1"  />
                <role id="task_holon"        min="0"  max="10" />
                <role id="resource_holon"    min="5"  max="5"  />
                <role id="transport_holon"   min="1"  max="4"  />
            </roles>
            <links>
                <link from="adacor_supervisor" to="task_holon"      type="authority" />
                <link from="adacor_supervisor" to="resource_holon"  type="authority" />
                <link from="adacor_supervisor" to="transport_holon" type="authority" />
            </links>
        </group-specification>
    </structural-specification>

    <functional-specification>
        <scheme id="adacor_production">
            <goal id="produce_batch_supervised" ttf="3600000">
                <plan operator="sequence">
                    <goal id="await_supervisor_assignment" ttf="30000"  />
                    <goal id="process_at_resource"        ttf="600000" />
                    <goal id="transport_to_next"          ttf="120000" />
                    <goal id="run_end_of_line_test"       ttf="300000" />
                </plan>
            </goal>
        </scheme>

        <scheme id="adacor_reconfiguration">
            <goal id="execute_schema_transition" ttf="30000">
                <plan operator="sequence">
                    <goal id="drain_negotiations" ttf="15000" />
                    <goal id="suspend_holons"     ttf="10000" />
                    <goal id="commit_transition"  ttf="5000"  />
                </plan>
            </goal>
        </scheme>
    </functional-specification>

    <normative-specification>
        <norm id="resource_must_ack_abort"
              type="obligation"
              role="resource_holon"
              mission="mAckAbort"
              time-constraint="5000" />

        <norm id="task_must_ack_suspend"
              type="obligation"
              role="task_holon"
              mission="mAckSuspend"
              time-constraint="10000" />

        <norm id="supervisor_must_respond_to_spike"
              type="obligation"
              role="adacor_supervisor"
              mission="mRespondToSpike"
              time-constraint="15000" />
    </normative-specification>

</organisational-specification>
```

#### [MODIFIED] `factory.jcm`

```jacamo
mas factory_twin {

    agent supervisor : supervisor_agent.asl {
        focus: factory_ws.supervisor_artifact,
               factory_ws.energy_price,
               factory_ws.amr_artifact,
               factory_ws.utility_system,
               factory_ws.timer_artifact
    }

    // Five concurrent Order Holons for PROSA concurrency testing.
    // Each agent carries order_holon_id so the supervisor can address it by name.
    agent order_1 : order_holon.asl {
        focus: factory_ws.base_station_1, factory_ws.base_station_2,
               factory_ws.base_station_3, factory_ws.base_station_4,
               factory_ws.test_bench,     factory_ws.amr_artifact,
               factory_ws.timer_artifact, factory_ws.supervisor_artifact,
               factory_ws.utility_system
        parameters: run_id(0), order_holon_id("order_1")
    }
    agent order_2 : order_holon.asl {
        focus: factory_ws.base_station_1, factory_ws.base_station_2,
               factory_ws.base_station_3, factory_ws.base_station_4,
               factory_ws.test_bench,     factory_ws.amr_artifact,
               factory_ws.timer_artifact, factory_ws.supervisor_artifact,
               factory_ws.utility_system
        parameters: run_id(0), order_holon_id("order_2")
    }
    agent order_3 : order_holon.asl { parameters: run_id(0), order_holon_id("order_3") }
    agent order_4 : order_holon.asl { parameters: run_id(0), order_holon_id("order_4") }
    agent order_5 : order_holon.asl { parameters: run_id(0), order_holon_id("order_5") }

    // Resource Holons — additionally focus supervisor_artifact for registerLock/releaseLock
    agent station_1 : resource_holon.asl {
        focus: factory_ws.base_station_1, factory_ws.timer_artifact,
               factory_ws.supervisor_artifact, factory_ws.utility_system
        parameters: station_id(1)
    }
    agent station_2 : resource_holon.asl {
        focus: factory_ws.base_station_2, factory_ws.timer_artifact,
               factory_ws.supervisor_artifact, factory_ws.utility_system
        parameters: station_id(2)
    }
    agent station_3 : resource_holon.asl { parameters: station_id(3) }
    agent station_4 : resource_holon.asl { parameters: station_id(4) }
    agent station_5 : resource_holon.asl {
        focus: factory_ws.test_bench,     factory_ws.timer_artifact,
               factory_ws.supervisor_artifact, factory_ws.utility_system
        parameters: station_id(5)
    }

    agent amr_1 : amr_agent.asl {
        focus: factory_ws.amr_artifact, factory_ws.supervisor_artifact
        parameters: amr_id("AMR-1")
    }
    agent amr_2 : amr_agent.asl {
        focus: factory_ws.amr_artifact, factory_ws.supervisor_artifact
        parameters: amr_id("AMR-2")
    }

    workspace factory_ws {
        artifact base_station_1  : factory.BaseStationArtifact("S1", 1, 45.0,  5.0,  0.005, 0)
        artifact base_station_2  : factory.BaseStationArtifact("S2", 2, 120.0, 15.0, 0.012, 0)
        artifact base_station_3  : factory.BaseStationArtifact("S3", 3, 30.0,  2.0,  0.002, 0)
        artifact base_station_4  : factory.BaseStationArtifact("S4", 4, 240.0, 30.0, 0.008, 0)
        artifact test_bench      : factory.TestBenchArtifact("S5", 0)
        artifact amr_artifact    : factory.AMRArtifact(20, 12, 2)
        artifact utility_system  : factory.UtilitySystemArtifact()
        artifact timer_artifact  : factory.TimerArtifact()
        artifact energy_price    : factory.EnergyPriceArtifact("price_series.csv")
        artifact database        : factory.DatabaseArtifact("factory_history.db")
        artifact telemetry       : factory.TelemetryArtifact(8080)
        artifact supervisor_artifact : factory.SupervisorArtifact()   // Phase 3 addition
    }

    org factory_prosa_org {
        org-file: "src/org/prosa_org.xml"
        group holonic_line : holonic_factory {
            players: supervisor  prosa_supervisor,
                     order_1     order_holon,
                     order_2     order_holon,
                     order_3     order_holon,
                     order_4     order_holon,
                     order_5     order_holon,
                     station_1   resource_holon,
                     station_2   resource_holon,
                     station_3   resource_holon,
                     station_4   resource_holon,
                     station_5   resource_holon,
                     amr_1       transport_holon,
                     amr_2       transport_holon
        }
    }

    org factory_adacor_org {
        org-file: "src/org/adacor_org.xml"
        group adaptive_line : adaptive_factory {
            players: supervisor  adacor_supervisor,
                     order_1     task_holon,
                     order_2     task_holon,
                     order_3     task_holon,
                     order_4     task_holon,
                     order_5     task_holon,
                     station_1   resource_holon,
                     station_2   resource_holon,
                     station_3   resource_holon,
                     station_4   resource_holon,
                     station_5   resource_holon,
                     amr_1       transport_holon,
                     amr_2       transport_holon
        }
    }
}
```

---

## Execution Order

```
Component A ──► Component B ──► Component C ──► Component D ──► Component E ──► Component F
(Value types)   (MainSimulator) (SupervisorArt)  (Artifacts)     (ASL agents)    (MoISE/JCM)

    │
    ▼ first
  Compile OrgSchemaTransition.java
  (verify: TransitionPhase enum accessible; no other Phase 3 Java depends on it)
    │
    ▼
  Extend MainSimulator:
    - Capture currentEpoch before AdvanceTime RPC (epoch-tearing fix)
    - Add beginTransition / commitTransition / clearCommittedTransition synchronized methods
    - Update TelemetryFrame assembly to use captured local (not schemaEpoch.get())
    - Update updateFromStateVector call site to pass simTimeS
    │
    ▼
  Implement SupervisorArtifact:
    - reservationRegistry ConcurrentHashMap
    - registerLock(orderId, stationName, orderHolonName)  ← 3 args, no broadcast logic
    - releaseLock(orderId)
    - getActiveLocks(locks)  ← returns lock(OrderId, StationName, HolonName) terms
    - initiateTransition / commitTransition (thin wrappers calling MainSimulator)
    - Wire MainSimulator reference in MainSimulator.main() before tick loop
    │
    ▼
  Modify in parallel (no inter-dependency within this group):
    UtilitySystemArtifact  ─┐  (add getSimTime @OPERATION + simTimeS field)
    EnergyPriceArtifact    ─┤  (add threshold logic; no erroneous try-catch)
    BaseStationArtifact    ─┤  (implement releaseStation; wire timerArtifactId)
    TestBenchArtifact      ─┘  (add abortOperation override)
    │
    ▼
  Implement ASL agents (all artifact @OPERATION signatures must be finalized first):
    supervisor_agent.asl   (uses .send() for all broadcasts; 3-arg lock filter)
    resource_holon.asl     (3-arg registerLock; releaseStation on abort/timer; no CFP drop)
    order_holon.asl        (abort handling; correct CFP drop_intention placement)
    amr_agent.asl          (suspend/resume; grid saturation notify)
    │
    ▼
  Implement MoISE schemas and update JCM (stable after agent role assignments confirmed):
    prosa_org.xml → adacor_org.xml → factory.jcm
```

---

## File Manifest (Phase 3)

| Status | File | Component | Fixes Applied |
|--------|------|-----------|---------------|
| NEW | `src/java/factory/OrgSchemaTransition.java` | A | — |
| MODIFIED | `src/java/factory/MainSimulator.java` | B | #2 (epoch capture) |
| NEW | `src/env/factory/SupervisorArtifact.java` | C | #1 (no execInternalOp), #3 (3-arg registry) |
| MODIFIED | `src/env/factory/UtilitySystemArtifact.java` | D | #5 (getSimTime @OPERATION) |
| MODIFIED | `src/env/factory/EnergyPriceArtifact.java` | D | #7 (no erroneous try-catch note) |
| MODIFIED | `src/env/factory/BaseStationArtifact.java` | D | #4 (releaseStation implemented) |
| MODIFIED | `src/env/factory/TestBenchArtifact.java` | D | abortOperation wiring |
| NEW | `src/ag/supervisor_agent.asl` | E | #1 (.send broadcasts), #3 (lock filter), #5 (getSimTime) |
| MODIFIED | `src/ag/resource_holon.asl` | E | #3 (3-arg registerLock), #4 (releaseStation), #6 (no CFP drop) |
| MODIFIED | `src/ag/order_holon.asl` | E | #6 (correct CFP drop placement) |
| MODIFIED | `src/ag/amr_agent.asl` | E | suspend/resume |
| NEW | `src/org/prosa_org.xml` | F | — |
| NEW | `src/org/adacor_org.xml` | F | — |
| MODIFIED | `factory.jcm` | F | — |

**Total: 5 new files + 9 modified files = 14 files.** No Phase 1 Python files are touched.
All Phase 2 proto field numbers are preserved. No existing `@OPERATION` signatures change.

---

## Verification Plan

### Prerequisites

All 10 Phase 2 verification steps must pass. Then:

```bash
./gradlew compileJava
# Expected: BUILD SUCCESSFUL
# OrgSchemaTransition, SupervisorArtifact all compile cleanly.
# No NoSuchOperationException risks from undefined execInternalOp targets.

# Verify proto field numbers are intact (no renumbering)
grep -n "schema_epoch\|active_org_schema" \
    build/generated/source/proto/main/java/factory/TelemetryFrameOuterClass.java
# Must show field 3 and field 4 — unchanged from Phase 2
```

---

### Step-by-Step Verification

#### V1 — Epoch Tearing: `schema_epoch` matches `AdvanceTime` on every tick

Instrument `MainSimulator` to log both the captured epoch and the TelemetryFrame epoch:

```bash
./gradlew run --args="--max-ticks=10 --log-epochs"
# Every tick must log exactly:
# [TMC] tick=N capturedEpoch=0 AdvanceTime.epoch=0 TelemetryFrame.epoch=0
# The three values must be identical on every row.
```

Inject an artificial `commitTransition()` call from a background thread timed to fire between
the `advanceTime()` dispatch and the `onStepReady()` assembly (simulate with a 1ms sleep
before `commitTransition()`):

```bash
# [TMC] tick=5 capturedEpoch=0 AdvanceTime.epoch=0 TelemetryFrame.epoch=0
# — NOT: TelemetryFrame.epoch=1 while AdvanceTime.epoch=0
# Without the fix, this test would have produced a tearing mismatch.
```

#### V2 — PROSA: Five Concurrent Order Holons, No CNP Collision

```bash
./gradlew run --args="--max-orders=5 --max-ticks=100"
# All five order_N agents must be active simultaneously.
# At no tick may two station entries in TelemetryFrame.station_states both show
# STATION_BUSY_PROCESSING with the same active_order_id.
```

In browser:
```javascript
ws.onmessage = e => {
    const f = TelemetryFrame.decode(new Uint8Array(e.data))
    const busy = f.stationStates.filter(s => s.state === 2).map(s => s.activeOrderId)
    if (new Set(busy).size !== busy.length)
        console.error("DUPLICATE ORDER IN BUSY STATIONS", busy)
}
```

#### V3 — TimerArtifact TTL + `releaseStation` Sync Under PROSA Load

Verify that after TTL expiry, the dashboard sees `STATION_IDLE` (not `STATION_PROVISIONAL_LOCK`):

```bash
./gradlew run --args="--max-orders=5 --cnp-slow-accept --ttl=2000"
# Expected for each expired lock:
# [station_N]  timer_expired(OrderId) — reverting to idle
# [station_N]  releaseStation called — currentSummary = IDLE
# TelemetryFrame: station_N shows STATION_IDLE within one decimation interval
# NO station remains stuck in STATION_PROVISIONAL_LOCK after timer fires
```

Also verify the Phase 0 abort path:
```bash
./gradlew run --args="--force-abort-on=station_1 --order=order_2"
# [station_1]  abort_current_operation(uuid) : provisional_lock → IDLE
# [station_1]  releaseStation called
# TelemetryFrame: S1 = STATION_IDLE — not frozen in PROVISIONAL_LOCK
```

#### V4 — `EnergyPriceArtifact`: Simulation-Clock-Only, No Erroneous Guard

```bash
./gradlew run --args="--price-series=price_series_spike_test.csv --max-ticks=50"
# price_series_spike_test.csv has price ≥ 150 EUR/MWh at simT=30s
# Expected:
# [energy_price] updatePrice(30.0) spike detected: 165.0 EUR/MWh
# [supervisor]   +energy_price_spike(165.0) — initiating ADACOR transition

# Verify no ScheduledExecutorService threads exist
jstack $(pgrep -f "factory.MainSimulator") | grep -i "scheduled\|wall.clock"
# Must return zero matches

# Verify hysteresis: inject 148 EUR/MWh (below threshold, above 90% band at 135)
# energy_price_normal must NOT fire at 148; must fire below 135
```

#### V5 — `getSimTime()` Does Not Produce Belief-Revision Events

Instrument Jason to log all belief-revision events for the supervisor agent:

```bash
./gradlew run --args="--max-ticks=30 --log-brf=supervisor"
# Expected: ZERO belief-revision events from sim_time_s observable
# (because sim_time_s is not an observable — only getSimTime() @OPERATION is used)
# Every getSimTime() call must appear as an artifact operation call, not a belief event
```

Verify `UtilitySystemArtifact` does NOT define `sim_time_s` as an observable:
```bash
grep "defineObsProperty.*sim_time" src/env/factory/UtilitySystemArtifact.java
# Must return zero matches
```

#### V6 — SupervisorArtifact: No `execInternalOp` Broadcast at Runtime

```bash
./gradlew run --args="--force-spike-at=5.0 --max-ticks=30"
# During Phase 0 abort, verify that abort messages are sent via Jason .send(),
# NOT via any Java artifact method.
# Enable Jason message tracing:
# Expected in trace:
# [supervisor → station_1] tell abort_current_operation("uuid")   ← Jason .send()
# [supervisor → order_2]   tell abort_current_operation("uuid")   ← Jason .send()
# No NoSuchOperationException in logs (which would indicate execInternalOp("send_abort"))
```

#### V7 — Lock Filter Type Correctness (Grid Saturation)

Configure a run where three Order Holons hold active locks:

```bash
./gradlew run --args="--max-orders=5 --grid-stress --lock-hold-orders=order_1,order_2,order_3"
# Scenario: order_1, order_2, order_3 are in busy_processing (locks registered)
#           order_4, order_5 are not (no active lock)
#           grid utilization > 0.85 triggers !suspend_low_priority_holons
# Expected:
# [supervisor] getActiveLocks → [lock("uuid1",station_1,order_1),
#                                lock("uuid2",station_2,order_2),
#                                lock("uuid3",station_3,order_3)]
# [supervisor] LowPri = [order_4, order_5]   ← ONLY holons without locks
# [supervisor] suspend_intentions sent to order_4 and order_5 ONLY
# order_1, order_2, order_3 continue processing — NO deadlock
```

Confirm the previously broken behavior does NOT occur:
```bash
# MUST NOT see: suspend_intentions sent to order_1, order_2, or order_3
# The old type-mismatch would have suspended all five holons, causing factory deadlock
```

#### V8 — ADACOR Phase 0 + Phase 1 Full Transition

```bash
./gradlew run --args="--force-spike-at=5.0 --max-ticks=60"
# Expected sequence:
# [supervisor]   initiateTransition("adacor", 5.0, 1)
# [supervisor]   Phase0 DRAIN begin
# [supervisor]   (if locks exist) abort dispatched via .send() — verified in V6
# [supervisor]   Phase1 SUSPEND begin
# [supervisor]   suspend_intentions sent to all 12 agents via !send_suspend_to_all
# [station_N]    suspend_ack(station_N) sent to supervisor
# [order_N]      suspend_ack(order_N) sent to supervisor
# [supervisor]   All 12 ACKs received — commitTransition
# [MainSimulator] schemaEpoch → 1, activeOrgSchema → "adacor"
# TelemetryFrame: schema_epoch=1, active_org_schema="adacor"
# Browser HUD: label transitions "PROSA" → "ADACOR" with amber animation
```

Force-commit path (one agent never ACKs):
```bash
./gradlew run --args="--force-spike-at=0.0 --block-ack-from=station_5 --max-ticks=30"
# [supervisor]   Phase1 TTL expired — force_commit
# [MainSimulator] epoch committed despite missing station_5 ACK
# TelemetryFrame: epoch=1, schema="adacor" — confirms force_commit path works
```

#### V9 — Schema Epoch Validation on Agent Resume

```bash
./gradlew run --args="--inject-epoch-mismatch-on=station_5 --max-ticks=40"
# Scenario: station_5 is in await(corrId) during RunBatchTest when force_commit fires
# schema_epoch observable updates to 1; station_5 agent perceives the change
# Expected:
# [station_5]  +schema_epoch(1) : current_epoch(0) ≠ 1 → !reinitialize_schema
# [station_5]  drop_all_intentions; -+station_state(idle); !start
# TelemetryFrame: S5 = STATION_IDLE — not stuck in STATION_BUSY_PROCESSING
```

#### V10 — Phase 3 Checklist (doc5 Success Criteria Mapping)

| Criterion | Test | Pass Condition |
|-----------|------|----------------|
| `TimerArtifact` and `EnergyPriceArtifact` use simulation clock only | V4 | Zero `ScheduledExecutorService` threads; price spike at correct simT |
| ADACOR transitions freeze all intentions and transition schema securely | V8 | All 12 ACKs received (or force_commit); epoch increments atomically |
| Phase 0 enforces two-party abort via `reservation_registry` | V8 | Both Order Holon and Resource Holon receive abort via Jason `.send()` |
| Agents detect schema modifications via `schema_epoch` validation | V9 | `!reinitialize_schema` fires on mismatch; station returns to IDLE |
| `schema_epoch` in `TelemetryFrame` equals `AdvanceTime` epoch every tick | V1 | Zero tearing mismatches across 10 instrumented ticks including concurrent `commitTransition` |
| `active_org_schema` field transitions within one decimation interval | V8 | Browser HUD updates within 67ms of commit |
| Lock filter correctly identifies low-priority Order Holons by agent name | V7 | Only lock-free holons suspended; holons with active locks continue uninterrupted |
| Dashboard station states update on abort (no frozen `PROVISIONAL_LOCK`) | V3 | `releaseStation()` called on every non-normal terminal path |
| `getSimTime()` used; zero belief-revision events from simulation time | V5 | No `sim_time_s` observable; BDF log shows zero time-driven belief events |
| `TestBenchArtifact.abortOperation` wired; no orphaned gRPC streams | V8 | Station 5 abort under ADACOR Phase 1 produces no stream leak |

> [!SUCCESS]
> Phase 3 is complete when all 10 verification steps pass and the 10-row checklist is green.
> At that point the factory operates under PROSA holonic self-organization, transitions to
> ADACOR supervised control on energy price disturbances via a simulation-clock-pure two-phase
> commit, reverts to PROSA on normalization, and propagates live organizational metadata to
> the browser HUD within one decimation interval — with all seven architectural flaws from the
> prior draft corrected. Proceed to **Phase 4: Monte Carlo production scale — 1:30 Single-JVM
> fan-out, 30 Python daemons, 8760-hour simulated years, and full burst-load historian
> throughput**.
