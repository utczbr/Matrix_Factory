# Document 3: Multi-Agent System (MAS) & Organizational Design

## 1. Overview **[Status: Production-Verified (Phase 1 & 2)]**

The cognitive layer is orchestrated by the JaCaMo framework. It is fundamentally composed of Jason-based BDI (Belief-Desire-Intention) agents navigating physical tasks, structured by MoISE organizational blueprints.

## 2. Jason BDI Agents **[Status: Production-Verified (Phase 1 & 2)]**

The agents encapsulate operational intelligence. To ensure reusability, agents are deliberately decoupled from specific organizational topologies, relying instead on clean belief bases and standardized negotiation protocols.

### 2.1 Order Holon (`order_holon.asl`) **[Status: Production-Verified (Phase 1 & 2)]**
Represents the production batch in transit. Its primary intent is to secure resources to fulfill its manufacturing recipe.
*   **Behavior (CNP Protocol):** To progress through the factory grid, it initiates FIPA Contract-Net Protocols (CNP) broadcasting a Call For Proposal (CFP) to all eligible station agents.

### 2.2 Resource Holon (`resource_holon.asl`) **[Status: Production-Verified (Phase 1 & 2)]**
Represents a specific physical manufacturing cell. To prevent double-booking under high concurrency, the Resource Holon implements a transactional reservation state-machine with provisional locking.

#### CNP Reservation State-Machine

When generating a `propose` message, the Resource Holon asserts a temporary `provisional_lock` in its belief base accompanied by a predefined Time-To-Live (TTL) timeout.

> **Implementation Constraint (No Wall-Clock Timers):** The TTL mechanism must NOT use a wall-clock `ScheduledExecutorService` as it drifts randomly relative to the discrete physical $dt$. Instead, the `TimerArtifact` must manage TTLs exclusively as NextEventRequest (NER) priority queue entries evaluated strictly upon the `StepReady` payload of the synchronization barrier. The TTL value (e.g., `5000`) is measured in **simulated milliseconds**, mapped directly to the physical $dt$.
> 
> **Execution Ordering Invariant:** To prevent race conditions between timeouts and incoming messages, the system guarantees that all `timer_expired` NERs for a given tick are resolved and applied to belief bases *before* any inter-agent messages generated within that same tick window are processed.
>
> **Unification Key Consistency:** The lock must use the stable batch `OrderId` (a stable UUID passed in the CFP) rather than the `Sender` agent name.

```jason
// Plan: Respond to CFP with transactional reservation
+!call_for_proposal(Step, Stations, OrderId)[source(Sender)] 
   : .member(MyId, Stations) & station_state(idle)
   <- ?current_processing_cost(Cost);
      -+station_state(provisional_lock(OrderId)); // Use stable OrderId
      .send(Sender, tell, propose(MyId, Cost));
      startTimer(OrderId, 5000).  // Discrete-event NER Timer

// Plan: Accept proposal finalizes lock (Prevent Same-Cycle Ambiguity)
+accept_proposal(OrderId)[source(Sender)]
   : station_state(provisional_lock(OrderId))
   <- -+station_state(busy_processing(OrderId)); // Assert FIRST to block timer_expired
      .send(Sender, tell, inform_start(MyId));
      !execute_physical_operation(OrderId).

// Plan: Catch-all rejection for delayed accept_proposal (superseded lock)
+accept_proposal(OrderId)[source(Sender)]
   : not station_state(provisional_lock(OrderId))
   <- .send(Sender, tell, reject_proposal(MyId, "lock_expired_or_superseded")).

// Plan: TimerArtifact TTL expiry reverts to idle
+timer_expired(OrderId)
   : station_state(provisional_lock(OrderId))
   <- -+station_state(idle);
      .print("Lock expired for ", OrderId).
```

### 2.3 AMR Agent (`amr_agent.asl`) **[Status: Production-Verified (Phase 1 & 2)]**
Represents the Autonomous Mobile Robots. Accepts transport assignments and negotiates collision-free paths via the `AMRArtifact`'s **4D Spatio-Temporal Reservation Matrix**.

**Grid Saturation Deadlock Resolution:**
Under extreme PROSA load, 10+ orders concurrently routing can saturate the grid, returning `transport_blocked(BatchId)` to all orders endlessly. The `AMRArtifact` exposes a `getGridUtilization()` guard. When a transport failure is observed and utilization > 0.85, the supervisor suspends all low-priority Order Holons via `.drop_intention(request_transport)` and issues `clearExpiredReservations()` to flush stale 4D projections. To prevent permanent starvation, the supervisor must broadcast a symmetric un-suspend trigger when `getGridUtilization() < 0.60`, resuming the suspended intentions.

## 3. MoISE Organizational Specifications **[Status: Production-Verified (Phase 3)]**

The Digital Twin implements three distinct MoISE structural blueprints: Centralized Hierarchical, PROSA Holonic, and ADACOR Adaptive.

### 3.1 ADACOR Adaptive (`adacor_org.xml`) **[Status: Production-Verified (Phase 3)]**
A hybrid architecture capable of dynamic reconfiguration. The `supervisor` toggles between Autonomous (PROSA) and Supervised (Centralized) modes based on external disturbances.

#### The Energy Price Disturbance

The ADACOR transition is triggered by an `EnergyPriceArtifact` reading `price_series.csv`. 
- **Implementation:** The artifact MUST NOT use a wall-clock executor. The artifact observes the simulation clock via a callable `updatePrice(simTime)` invoked by the `MainSimulator` at each TAG issuance, maintaining exact temporal coherence with the physics engine.

#### Two-Phase Commit for Organizational Reconfiguration

To transition schemas without stranding batches or deadlocking the factory, a strict two-phase commit protocol is enforced:

1.  **Phase 0 — Drain Active Negotiations (with Timeout):** The supervisor queries all Order Holons for pending commitments. 
    - **Timeout Escrow:** Bound by a `TTL_phase0 = 15s`. Upon expiry, the supervisor executes a two-party compensating transaction: utilizing a `reservation_registry: Map<OrderId, StationId>`, it broadcasts `abort_current_operation(OrderId)` to BOTH the Order Holon and the registered Resource Holon. This cleanly revokes the provisional locks, preventing 245-second latency deadlocks. The Jason plan for the abort must include an identity guard to prevent corrupting a newer lock if the state naturally reverted: `+abort_current_operation(OrderId) : station_state(provisional_lock(OrderId)) <- -+station_state(idle).`
2.  **Phase 1 — Suspend (with Timeout):** The supervisor broadcasts `suspend_intentions` to all holons, enforcing preemption via `.drop_intention`.
    - **Timeout Escrow:** Bound by a `TTL_phase1 = 10s`. If unanimous consensus fails, a `force_commit` is decreed.
3.  **Epoch Validation:** Following a `force_commit`, agents may resume from blocked states with stale MoISE bindings. Agents call `?schema_epoch(E)` and compare it with the epoch explicitly attached to the `AdvanceTime` response. If mismatched, they execute `!reinitialize_schema` to drop old normative intentions.

## 4. Telemetry and Historian **[Status: Production-Verified (Phase 1 & 2)]**

In highly concurrent architectures (e.g., PROSA), state extraction must not interfere with the physical engine's tick rate or the BDI cycle latency.

### 4.1 `DatabaseArtifact` (Lossless Historian) **[Status: Production-Verified (Phase 1 & 2)]**

Query unification over tens of thousands of historical batch records causes severe BDI lag. Historical records must be offloaded to an external `DatabaseArtifact` backed by SQLite.

> **Write Contention & Burst Telemetry:** During ADACOR Phase 1 synchronization broadcasts, the SQLite WAL serialization will severely block the BDI cycle. To maintain $O(1)$ latency during the 1:30 Phase 4 fan-out, the `DatabaseArtifact` utilizes an asynchronous `ArrayBlockingQueue<>(300_000)` combined with adaptive drain-to-occupancy batching (`batchSize = min(MAX_BATCH, queue.size())`) evaluated every 500ms, clearing backlogs proportionally to burst demand instead of a fixed ceiling.
> 
> **Aggressive Tuning & Backpressure:** The artifact enforces the PRAGMAs `journal_mode=WAL`, `wal_autocheckpoint=100`, and `synchronous=NORMAL` to prevent multi-gigabyte WAL file ballooning. If the queue fills, the artifact emits `database_backpressure` to actively throttle MAS dispatch. A hysteresis signal `database_pressure_normal` is emitted when occupancy falls below 3,000 records to seamlessly lift the throttle.

### 4.2 `TelemetryArtifact` (Lossy Observer) **[Status: Production-Verified (Phase 1 & 2)]**

The web dashboard visualization is decoupled via a `TelemetryArtifact` that mirrors the database pattern but acts as a lossy observer rather than a lossless historian. 

It reads off the `AtomicReference` snapshot published by the `MainSimulator` and pushes it onto its own bounded queue. A separate consumer thread flushes these batches over WebSocket to the browser.

> **Decimation & Drop on Overflow:** The telemetry must not backpressure the simulation. The `TelemetryArtifact` decimates the simulation data (e.g., capping at 15–20Hz) by gating publication on simulation time before touching the queue. Critically, `lastPublished` must advance only upon **confirmed delivery** (e.g., inside the WebSocket library's `onReady`/successful-write callback), not at the moment of queue-offer. This prevents a frame dropped at the network edge (due to client-side TCP backpressure) from being silently and permanently counted as "sent" for that decimation slot. A `dropped_telemetry_frame_count` metric must be exposed, mirroring the existing `dropped_NER_count` pattern, so that degraded telemetry fidelity under sustained network throttling is observable rather than silent.
>
> **Non-Blocking WebSocket I/O:** The WebSocket consumer thread must use strictly non-blocking network I/O. If the browser tab throttles and the underlying TCP write buffer fills, the consumer thread must drop the frame at the network edge rather than block.

