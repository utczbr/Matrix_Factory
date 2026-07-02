# Phase 3.5: Specification-Reality Reconciliation — Implementation Plan

## Background

`Phase4.md`'s **Current State Audit** pulled `github.com/utczbr/Matrix_Factory` (`main`) and
checked it file-by-file against the doc1/doc3/doc4/doc6 `[Status: Production-Verified]` tags and
doc5's Phase 2/3 "Mitigated" risk entries. Seven items are tagged as finished specification but are
either stub code, hardcoded single-instance state, or missing entirely:

| # | File | Claimed state | Actual state |
|---|---|---|---|
| 1 | `src/main/java/factory/DatabaseArtifact.java` | doc3 §4.1, doc5 risk table: **"Mitigated (Phase 2)"** — async bounded queue, WAL pragmas, backpressure/hysteresis | 53 lines; synchronous `PreparedStatement.executeUpdate()` on the CArtAgO operation thread; no queue, no WAL pragmas, no backpressure signal |
| 2 | `src/main/java/factory/TelemetryArtifact.java` | doc3 §4.2, doc1 §2.6: **"Production-Verified (Phase 1 & 2 / Phase 3)"** | 36 lines; WebSocket send call is commented out; comment reads *"the actual frontend dashboard is Phase 3"* |
| 3 | `visualization/` | doc6 §2–§5: **"Production-Verified (Phase 1 & 2)"** | Directory does not exist — no `index.html`, `dashboard.js`, `factory_layout.json`, WebSocket server |
| 4 | `physical_engine/sim_bridge_server.py` — bind address | doc4 §1 (no unauthorized external access) | Binds `0.0.0.0:{port}` — accepts connections from any host, not loopback-only |
| 5 | `physical_engine/sim_bridge_server.py` — seeding | doc4 §4 pt. 3: **"Production-Verified (Phase 1 & 2)"** — `seed = stack_id ⊕ run_id` | No `run_id`/`stack_id` constructor params anywhere in `SimBridgeServicer`; seeding is not wired |
| 6 | `src/main/java/factory/MainSimulator.java` | doc1 §2.6 lock-free publish: **"Production-Verified (Phase 3)"** | `public final int runId = 0;` hardcoded; `grpcBridge = new GrpcClientBridge(50051);` hardcoded single port — code cannot run as anything but instance 0 of 1 |
| 7 | `factory.jcm` | — | One workspace, 13 agents, `run_id(0)` static belief hardcoded on every order holon |

**Why this cannot simply become "Phase 4, Components E–G" as originally drafted:** Phase 4's entire
purpose is exercising these components under 30× concurrent burst load. If the *first* time
`DatabaseArtifact`'s queue, `TelemetryArtifact`'s decimation, and the dashboard's WebSocket client
are ever run at all is simultaneously the first time they're run at 30× scale, any bug surfaced by
the soak test is ambiguous by construction — is it a correctness bug in the component, or a
concurrency/scale bug in the fan-out? There is no way to tell without a working single-instance
baseline to compare against. Phase 3.5 exists to produce that baseline: every item above is brought
up to its *already-claimed* Phase 1–3 spec at **run-count = 1**, verified in isolation, and only
then does Phase 4 multiply a known-good single instance by 30.

A secondary goal: doc5's Phase 2 risk table currently asserts `DatabaseArtifact` backpressure is
"Mitigated (Phase 2)" against a 53-line synchronous stub. That entry is factually wrong and this
plan corrects the audit trail, not just the code.

---

## Scope of Phase 3.5

In scope — bring each audited gap up to its already-claimed spec, at single-run scale:

1. **`DatabaseArtifact`** — real async bounded-queue historian per doc3 §4.1: `ArrayBlockingQueue<>(300_000)`,
   adaptive drain-to-occupancy batching, WAL pragmas, `database_backpressure` /
   `database_pressure_normal` hysteresis. Validated at 1 run's worth of write load (30-run burst
   validation is explicitly deferred to Phase 4 V5).
2. **`TelemetryArtifact`** — wire the WebSocket send that is currently commented out: read the
   `AtomicReference` snapshot, decimate to 15–20Hz, advance `lastPublishedSimTimeS` only on
   confirmed delivery, expose `dropped_telemetry_frame_count`, per doc3 §4.2.
3. **`visualization/`** — the doc6 §2–§5 minimal single-run dashboard: `index.html`,
   `dashboard.js`, `factory_layout.json`, binary-Protobuf WebSocket client, station/AMR rendering,
   gap-recovery interpolation. This is the doc6 baseline; the multi-session `TelemetryHub`,
   run-switching, and connection-limit hardening in doc6 §6–§7 remain Phase 4 scope, unchanged from
   `Phase4.md`.
4. **`sim_bridge_server.py` loopback bind** — `0.0.0.0` → `127.0.0.1`. This is a standing security
   gap independent of fan-out and is fixed now rather than waiting on Phase 4's launcher work.
5. **`sim_bridge_server.py` seeding** — add `run_id`/`stack_id` constructor parameters to
   `SimBridgeServicer` and wire `seed = int.from_bytes(stack_id.encode('utf-8')[:8], 'little') ^ run_id`
   per doc4 §4 pt. 3, defaulting to `run_id=0, stack_id="S5"` for the current single-daemon
   deployment. This establishes the exact constructor signature Phase 4's `daemon_launcher.py` will
   call 30 times with different values — Phase 4 does not modify this signature, only supplies it.
6. **`MainSimulator.java`** — replace the hardcoded `runId = 0` field and hardcoded
   `new GrpcClientBridge(50051)` with constructor/CLI-injectable `runId` and `port` parameters,
   defaulting to today's single-instance values so existing single-run behavior is unchanged.
   Phase 4's `scripts/generate_factory_jcm.py` and launch sequence consume this parameter surface;
   they do not add it.
7. **`factory.jcm`** — replace the static `run_id(0)` belief with a workspace-level parameter
   consumed at load time, still emitting exactly one workspace/13-agent set for Phase 3.5. The
   30-workspace generation itself (`scripts/generate_factory_jcm.py`) remains Phase 4 Component D.
8. **Audit trail correction** — update doc5's Phase 2 risk-table entry for `DatabaseArtifact` from
   "Mitigated (Phase 2)" to reflect this plan's completion, and add a Phase 3.5 verification log
   section to doc5 mirroring the existing Phase 1/Phase 2 appendix format.

Out of scope (explicitly deferred to `Phase4.md`, unchanged):
- `daemon_launcher.py`, `multiprocessing.get_context('spawn')` orchestration, `os.sched_setaffinity()`
  pinning, `taskset` JVM isolation — all of Component A/C.
- 30-workspace `factory.jcm` generation and the `orders-per-run` tuning question (Component D).
- `TelemetryHub` multi-session fan-out, run-switching, connection-limit enforcement (doc6 §6).
- WebGL overlay budget guard, dropped-frame divergence checks at scale (doc6 §7).
- The 30×8760h Monte Carlo soak test and the 39-day wall-clock budget.
- gRPC executor sizing consistency across 30 daemons (doc4 §4.6) — `GrpcClientBridge.java` is
  already correctly sized per the audit's "Correctly implemented already" list; no work needed
  until Phase 4 replicates it 30 times.

---

## Strategic Constraints

| # | Constraint | Source |
|---|---|---|
| 1 | Every component built here must work correctly at `run_count = 1` before Phase 4 is allowed to multiply it by 30. No Phase 3.5 deliverable is considered done based on code review alone — each has its own verification step below. | This plan |
| 2 | No new parameter surface introduced here may assume 30-daemon topology. `run_id`, `port`, and `stack_id` become constructor/CLI arguments with defaults that reproduce today's single-instance behavior unchanged. | This plan (feeds doc1 §3) |
| 3 | All Phase 1–3 constraints remain in force (synchronization barrier, no wall-clock timers, no `execInternalOp` broadcasts, etc.). | Phase 1–3 docs |
| 4 | `DatabaseArtifact` and `TelemetryArtifact` queues remain fully independent — `database_backpressure` must never throttle telemetry. | doc3 §4.1/§4.2 |
| 5 | `lastPublishedSimTimeS` advances only on confirmed WebSocket delivery, never at queue-offer time. | doc3 §4.2, doc6 §5.2 |
| 6 | The visualization layer never opens any connection to the Python daemon, directly or via proxy — only through `TelemetryArtifact`. | doc4 §1, doc6 §4.1 |
| 7 | The Python daemon binds loopback-only; no service should be reachable from outside the host running the JVM. | doc4 §1 |
| 8 | Seeding must be reproducible: `seed = int.from_bytes(stack_id.encode('utf-8')[:8], 'little') ^ run_id`, wired end-to-end, not left as a documented-but-unimplemented formula. | doc4 §4 pt. 3 |

---

## Proposed Changes

Six components, ordered by dependency. A → B → C is the telemetry path (historian, then live feed,
then dashboard); D → E → F is the parameter-surface path (daemon, then JVM, then agent config) that
Phase 4 will later multiply by 30.

---

### Component A: `DatabaseArtifact` — Real Async Historian

#### [MODIFIED] `src/main/java/factory/DatabaseArtifact.java`

Replace the synchronous `executeUpdate()`-on-operation-thread pattern with a bounded queue and a
dedicated drain thread, per doc3 §4.1. Critically, drained records must never be lost on failed
commit: records are staged in a local batch buffer and re-queued if the transaction fails.

```java
package factory;

import cartago.*;
import java.sql.*;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class DatabaseArtifact extends Artifact {
    private static final int QUEUE_CAPACITY = 300_000;
    private static final int MAX_BATCH = 2_000;
    private static final int BACKPRESSURE_HIGH = 300_000;      // queue full
    private static final int BACKPRESSURE_LOW  = 3_000;        // hysteresis clear point
    private static final long DRAIN_INTERVAL_MS = 500L;

    private final ArrayBlockingQueue<TelemetryRecord> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final AtomicBoolean backpressureActive = new AtomicBoolean(false);
    private Connection conn;
    private Thread drainThread;

    void init() {
        try {
            conn = DriverManager.getConnection("jdbc:sqlite:factory_history.db");
            try (Statement s = conn.createStatement()) {
                s.execute("PRAGMA journal_mode=WAL;");
                s.execute("PRAGMA wal_autocheckpoint=100;");
                s.execute("PRAGMA synchronous=NORMAL;");
                s.execute("CREATE TABLE IF NOT EXISTS Orders(" +
                          "run_id INTEGER, order_id TEXT, event_type TEXT, sim_time REAL)");
            }
        } catch (SQLException e) {
            throw new IllegalStateException("DatabaseArtifact init failed", e);
        }
        drainThread = new Thread(this::drainLoop, "database-artifact-drain");
        drainThread.setDaemon(true);
        drainThread.start();
    }

    @OPERATION
    void recordEvent(int runId, String orderId, String eventType, double simTime) {
        TelemetryRecord rec = new TelemetryRecord(runId, orderId, eventType, simTime);
        boolean offered = queue.offer(rec);
        if (!offered) {
            // Queue genuinely full — this is the failure path doc3 flags as a silent-drop
            // risk if unhandled. Do not drop silently: signal and let the caller decide.
            signal("database_write_dropped", orderId);
            return;
        }
        if (queue.size() >= BACKPRESSURE_HIGH && backpressureActive.compareAndSet(false, true)) {
            signal("database_backpressure");
        }
    }

    private void drainLoop() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                Thread.sleep(DRAIN_INTERVAL_MS);
                int batchSize = Math.min(MAX_BATCH, queue.size());
                if (batchSize == 0) continue;

                java.util.ArrayList<TelemetryRecord> batch = new java.util.ArrayList<>(batchSize);
                for (int i = 0; i < batchSize; i++) {
                    TelemetryRecord rec = queue.poll();
                    if (rec == null) break;
                    batch.add(rec);
                }
                if (batch.isEmpty()) continue;

                try (PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO Orders(run_id, order_id, event_type, sim_time) VALUES (?,?,?,?)")) {
                    conn.setAutoCommit(false);
                    for (TelemetryRecord rec : batch) {
                        ps.setInt(1, rec.runId);
                        ps.setString(2, rec.orderId);
                        ps.setString(3, rec.eventType);
                        ps.setDouble(4, rec.simTime);
                        ps.addBatch();
                    }
                    ps.executeBatch();
                    conn.commit();
                    conn.setAutoCommit(true);
                } catch (SQLException e) {
                    // Failed commit path: restore records to queue so drained events are not
                    // silently lost, then signal failure with restored-count context.
                    int restored = 0;
                    for (TelemetryRecord rec : batch) {
                        if (queue.offer(rec)) restored++;
                    }
                    signal("database_batch_commit_failed", restored);
                }

                if (queue.size() <= BACKPRESSURE_LOW && backpressureActive.compareAndSet(true, false)) {
                    signal("database_pressure_normal");
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private record TelemetryRecord(int runId, String orderId, String eventType, double simTime) {}
}
```

Notes:
- `recordEvent` is intentionally **not** an `IBlockingCmd` — it must return immediately (`offer`,
  not `put`) so a full queue cannot stall the BDI cycle, matching the non-blocking intent of
  doc3 §4.1.
- The batch-commit failure path is the specific gap flagged in the audit ("a `DatabaseArtifact`
    failure path that could silently drop records on a failed batch commit") — this design stages
    drained records, attempts commit, re-queues on failure, and signals
    `database_batch_commit_failed` with restored-record context.
- At `run_count = 1` this queue will never approach 300,000 under normal load; Phase 4 V5 is what
  actually exercises the backpressure/hysteresis pair under 30-run burst conditions. Phase 3.5's
  verification (below) confirms the mechanism *works*, not that it survives 30× load.

---

### Component B: `TelemetryArtifact` — Wire the Live Feed

#### [MODIFIED] `src/main/java/factory/TelemetryArtifact.java`

```java
package factory;

import cartago.*;
import jakarta.websocket.Session;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

public class TelemetryArtifact extends Artifact {
    private static final int QUEUE_CAPACITY = 5_000;
    private static final double PUBLISH_INTERVAL_S = 1.0 / 18.0; // ~18Hz, within 15-20Hz band

    private final ArrayBlockingQueue<byte[]> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final AtomicLong droppedTelemetryFrameCount = new AtomicLong(0);
    private volatile double lastPublishedSimTimeS = Double.NEGATIVE_INFINITY;
    private Thread consumerThread;

    void init() {
        consumerThread = new Thread(this::consumeLoop, "telemetry-artifact-consumer");
        consumerThread.setDaemon(true);
        consumerThread.start();
    }

    @OPERATION
    void publishSnapshot(java.util.concurrent.atomic.AtomicReference<StateSnapshot> snapshotRef) {
        StateSnapshot snap = snapshotRef.get();
        if (snap == null) return;
        // Decimation gate BEFORE touching the queue, per doc3 §4.2 — this is what
        // keeps a slow consumer from ever backpressuring the physics integration loop.
        if (snap.simTime() - lastPublishedSimTimeS < PUBLISH_INTERVAL_S) return;

        byte[] frameBytes = snap.toProtobufFrame(); // pre-serialized, no JSON re-encode
        boolean offered = queue.offer(frameBytes);
        if (!offered) {
            droppedTelemetryFrameCount.incrementAndGet();
            // Drop is intentional and observable — telemetry is lossy by design (doc3 §4.2).
        }
        // NOTE: lastPublishedSimTimeS is NOT advanced here. It only advances on confirmed
        // WebSocket delivery inside consumeLoop's async send callback (Strategic Constraint 5).
    }

    private void consumeLoop() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                byte[] frame = queue.take();
                Session s = TelemetryWebSocketEndpoint.currentSession(); // Phase 3.5: single fixed session
                if (s == null || !s.isOpen()) continue;

                s.getAsyncRemote().sendBinary(
                    java.nio.ByteBuffer.wrap(frame),
                    result -> {
                        if (result.isOK()) {
                            lastPublishedSimTimeS = StateSnapshot.extractSimTimeS(frame);
                        } else {
                            droppedTelemetryFrameCount.incrementAndGet();
                        }
                    }
                );
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        }
    }

    long getDroppedTelemetryFrameCount() {
        return droppedTelemetryFrameCount.get();
    }
}
```

Notes:
- `TelemetryWebSocketEndpoint.currentSession()` is a Phase 3.5 stand-in for the full `TelemetryHub`
  multi-session registry (`Phase4.md` Component F/G). For this to be safe, Phase 3.5 explicitly
  defines single-session ownership semantics: newest valid `@OnOpen` replaces the prior session,
  stale/closed sessions are evicted on read, and reconnect from the same browser tab must never
  accumulate hidden zombie sessions.
- The confirmed-delivery-only advance of `lastPublishedSimTimeS` and the pre-queue decimation gate
  are carried over unchanged from `Phase4.md`'s design — Phase 3.5 is where they are *implemented*
  for the first time; Phase 4 does not modify this logic, only adds multi-session addressing on top
  of it.

#### [NEW] `src/main/java/factory/TelemetryWebSocketEndpoint.java`

Phase 3.5 uses a minimal endpoint contract for the single-session baseline:

```java
@ServerEndpoint("/telemetry")
public class TelemetryWebSocketEndpoint {
    private static final java.util.concurrent.atomic.AtomicReference<Session> CURRENT =
        new java.util.concurrent.atomic.AtomicReference<>();

    @OnOpen
    public void onOpen(Session session) {
        Session prior = CURRENT.getAndSet(session);
        if (prior != null && prior.isOpen() && !prior.getId().equals(session.getId())) {
            try { prior.close(); } catch (Exception ignored) {}
        }
    }

    @OnClose
    public void onClose(Session session) {
        CURRENT.compareAndSet(session, null);
    }

    static Session currentSession() {
        Session s = CURRENT.get();
        if (s != null && !s.isOpen()) {
            CURRENT.compareAndSet(s, null);
            return null;
        }
        return s;
    }
}
```

---

### Component C: `visualization/` — Minimal Single-Run Dashboard

#### [NEW] `visualization/index.html`, `visualization/dashboard.js`, `visualization/factory_layout.json`

Scope is strictly doc6 §2–§5 (station/AMR rendering, gap-recovery interpolation, the WebSocket
client, layout data) — no run-selector, no multi-session handling, no WebGL performance-budget
guard (those are doc6 §6–§7, Phase 4).

```javascript
// visualization/dashboard.js (excerpt — connection + frame handling only)
const ws = new WebSocket("ws://127.0.0.1:8080/telemetry");
ws.binaryType = "arraybuffer";

ws.onmessage = (event) => {
  const frame = TelemetryFrame.decode(new Uint8Array(event.data)); // protobuf-decoded, not JSON
  renderStations(frame.stationStates);
  renderAMRs(frame.amrPositions, frame.simTimeS); // gap-recovery interpolation per doc6 §4
  updateDroppedFrameHud(frame.droppedTelemetryFrameCount);
};

ws.onclose = (event) => {
  console.warn(`Telemetry connection closed (code ${event.code}) — reconnecting in 2s`);
  setTimeout(connect, 2000);
};
```

Notes:
- The connection target is a bare `/telemetry` path with no `run_id`/`client` query parameters —
  those are introduced in `Phase4.md`'s Component F/G when multi-session support is added. Building
  the single-run client first means Phase 4's later addition of query-parameter-based session
  identity is a strictly additive change, not a rewrite.
- `factory_layout.json` encodes the static station/AMR-path geometry doc6 assumes already exists;
    Phase 3.5 authors it once from the current factory floor plan (Stations 1–5, AMR grid) since no
    version of it exists in the repo today despite the doc6 tag implying it does.
- `factory_layout.json` is marked as `layout_version: "phase3_5_provisional"` and becomes an
    explicit input artifact reviewed against doc6 geometry. Phase 4 must consume this same layout
    baseline (or migrate it via a documented schema update), not silently replace it ad hoc.

---

### Component D: `sim_bridge_server.py` — Loopback Bind + Seeding

#### [MODIFIED] `physical_engine/sim_bridge_server.py`

**1. Loopback bind (security fix, independent of Phase 4 topology):**

```python
# Before:
bind_addr = f"0.0.0.0:{port}"

# After:
bind_addr = f"127.0.0.1:{port}"
```

**2. `SimBridgeServicer` gains `run_id`/`stack_id`, wired exactly as doc4 §4 pt. 3 specifies,
defaulting to today's single-instance identity:**

Add a pure helper so deterministic-seed verification does not depend on full server bootstrap:

```python
def derive_seed(stack_id: str, run_id: int) -> int:
    return int.from_bytes(stack_id.encode("utf-8")[:8], "little") ^ run_id

def __init__(
    self,
    num_cells: int = 200,
    R_internal: float = 0.1,
    T_initial: float = 353.15,
    run_id: int = 0,
    stack_id: str = "S5",
) -> None:
    ...
    self._run_id = run_id
    seed = derive_seed(stack_id, run_id)
    self._rng = np.random.default_rng(seed)
    logger.info(f"[run={run_id}] seeded RNG with seed={seed} (stack_id={stack_id!r})")
```

**3. `serve()` accepts `run_id` and passes it through, defaulting to `0` so the current
single-daemon `python -m physical_engine.sim_bridge_server` invocation is unaffected:**

```python
def serve(
    port: int = 50051,
    max_workers: int = 4,
    num_cells: int = 200,
    R_internal: float = 0.1,
    T_initial: float = 353.15,
    run_id: int = 0,
) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = SimBridgeServicer(
        num_cells=num_cells, R_internal=R_internal, T_initial=T_initial, run_id=run_id,
    )
    ...
```

`max_workers` stays at its current hardcoded default here — deriving it from a shared
Numba-thread-budget formula only makes sense once there is a 30-daemon budget to derive it from
(`Phase4.md` Component B change #4 supersedes this default). Phase 3.5 does not touch the thread
count; it only adds the parameter surface `Phase4.md`'s launcher will call into.

---

### Component E: `MainSimulator.java` — Parameterize `runId` / Port

#### [MODIFIED] `src/main/java/factory/MainSimulator.java`

```java
// Before:
public final int runId = 0;
...
grpcBridge = new GrpcClientBridge(50051);

// After:
public final int runId;
private final GrpcClientBridge grpcBridge;

public MainSimulator(int runId, int port) {
    this.runId = runId;
    this.grpcBridge = new GrpcClientBridge(port);
}

public static void main(String[] args) {
    int runId = args.length > 0 ? Integer.parseInt(args[0]) : 0;
    int port  = args.length > 1 ? Integer.parseInt(args[1]) : 50051;
    new MainSimulator(runId, port).run();
}
```

Default invocation (`./gradlew run` with no args) reproduces today's `runId=0, port=50051`
single-instance behavior exactly — this is a pure refactor from the current single-run operator's
point of view, and is the one change on the critical path Phase 4's `scripts/launch_phase4.sh`
depends on directly (it invokes the JVM with `--run-count`, which in turn constructs 30
`MainSimulator` instances using this constructor).

---

### Component F: `factory.jcm` — Parameterize `run_id` Belief

#### [MODIFIED] `factory.jcm`

Replace the static `run_id(0)` belief asserted identically on every order/resource holon with a
workspace-level parameter substituted at load time:

```jason
// Before (hardcoded in every agent block):
run_id(0).

// After (single template value, substituted by a trivial 1-run preprocessing
// step that Phase 4's generate_factory_jcm.py generalizes to 30 runs):
run_id({{RUN_ID}}).
```

For Phase 3.5, `{{RUN_ID}}` is substituted with `0` by a one-line script
(`scripts/render_factory_jcm.py --run-id=0`) rather than hand-edited, establishing the templating
convention `scripts/generate_factory_jcm.py` (Phase 4 Component D) will reuse for all 30 runs
instead of inventing a second templating approach later.

---

## Verification Plan

### V1 — DatabaseArtifact Async Path

```bash
# Single JVM run, force ~5,000 recordEvent() calls in a tight loop (e.g. via a
# test harness plan that rapidly cycles order state transitions).
sqlite3 factory_history.db "SELECT COUNT(*) FROM Orders WHERE run_id = 0;"
# Expected: count matches the number of recordEvent() calls (no silent drops).
grep "database_backpressure\|database_pressure_normal" jvm.log
# Expected: absent under normal single-run load (queue never approaches 300,000
# at run_count=1) — presence would indicate a queue-capacity or drain-rate bug.
```

### V2 — DatabaseArtifact Batch-Commit Failure Path

```bash
# Inject a forced SQLException (e.g. temporarily lock factory_history.db with a
# competing writer, or point at a read-only path) during a batch commit.
grep "database_batch_commit_failed" jvm.log
# Expected: signal fires with a non-zero batch size, and the artifact continues
# operating afterward (no crash, no silent record loss going unlogged).
```

### V3 — TelemetryArtifact Live Delivery

```javascript
// In browser console, connected to the Phase 3.5 single-run dashboard:
let frameCount = 0;
ws.addEventListener("message", () => frameCount++);
// After 10 seconds of simulation running:
console.log(frameCount); // Expected: roughly 150-200 frames (15-20Hz * 10s)
```

```bash
# Confirm decimation, not raw tick rate, governs publish frequency:
grep "publishSnapshot" jvm.log | wc -l   # raw AdvanceTime tick count (high)
# vs. frames actually sent over the wire (frameCount above) — the ratio should
# roughly match PUBLISH_INTERVAL_S against the simulation's dt.
```

### V4 — `lastPublishedSimTimeS` Confirmed-Delivery Semantics

```bash
# Artificially stall the browser (e.g. pause the tab / throttle network in
# devtools) mid-run, then resume.
# Expected: droppedTelemetryFrameCount increases while stalled; upon resume,
# lastPublishedSimTimeS reflects only frames that were actually ACKed by the
# WebSocket write, not frames that were merely queued during the stall.
```

### V5 — Dashboard Renders a Live Run End-to-End

```bash
# Start the daemon, JVM, and open visualization/index.html in a browser.
# Manual check: station color states update, AMR positions interpolate
# smoothly across gaps (not teleport), and the WebSocket reconnects
# automatically after a forced daemon restart.
```

### V6 — Seeding Reproducibility

```bash
python3 -c "
from physical_engine.sim_bridge_server import derive_seed
assert derive_seed('S5', 0) == derive_seed('S5', 0), 'seed not reproducible'
assert derive_seed('S5', 0) != derive_seed('S5', 1), 'seed not differentiating run_id'
print('OK: derive_seed deterministic and run_id-sensitive')
"
```

### V7 — Loopback Bind

```bash
python3 -m physical_engine.sim_bridge_server &
sleep 2
# From a different host on the network (or via a non-loopback interface IP):
grpcurl -plaintext <host-lan-ip>:50051 factory.SimBridge/HealthCheck
# Expected: connection refused / times out. Only 127.0.0.1:50051 responds.
```

### V8 — `MainSimulator` / `factory.jcm` Parameterization Round-Trip

```bash
./gradlew run --args="1 50052"
# Expected: JVM starts, connects to a daemon on port 50052 (started separately
# with `python -m physical_engine.sim_bridge_server --port=50052 --run-id=1`),
# and factory.jcm agents' run_id belief reads 1, not the previous hardcoded 0.
# This is the exact call pattern Phase 4's launch script will issue 30 times
# with run_id/port pairs (1, 50052) through (30, 50081) — Phase 3.5 confirms
# it works once before Phase 4 trusts it 30 times concurrently.
```

---

## Phase 3.5 Checklist (Audit Gap Closure Mapping)

| Audit Finding | Component | Verification | Pass Condition |
|---|---|---|---|
| `DatabaseArtifact` synchronous stub, no queue/WAL/backpressure | A | V1, V2 | Queue-backed writes confirmed in SQLite; backpressure signals absent under normal load; batch-commit failures signaled, not swallowed |
| `TelemetryArtifact` WebSocket send commented out | B | V3, V4 | Live frames arrive in-browser at 15-20Hz; `lastPublishedSimTimeS` advances only on confirmed delivery |
| `visualization/` directory does not exist | C | V5 | Dashboard renders a live single run end-to-end with gap-recovery interpolation |
| `sim_bridge_server.py` binds `0.0.0.0` | D.1 | V7 | Only loopback-reachable; LAN connection attempts refused |
| Seeding formula documented but unwired | D.2 | V6 | Identical `(run_id, stack_id)` reproducibly yields identical RNG stream |
| `MainSimulator` hardcodes `runId=0`, port `50051` | E | V8 | JVM accepts `runId`/`port` as parameters; default invocation unchanged |
| `factory.jcm` hardcodes `run_id(0)` on every agent | F | V8 | `run_id` belief reflects the injected `{{RUN_ID}}` value |
| doc5 Phase 2 risk table falsely marks `DatabaseArtifact` "Mitigated" | Audit trail | Manual doc review | doc5 entry updated to cite this plan's V1/V2, not the Phase 2 date |

> Phase 3.5 is complete when all eight rows are green. At that point every component `Phase4.md`'s
> Components A–G depend on has a **working, verified single-instance implementation** — Phase 4's
> remaining work becomes purely the fan-out multiplication (daemon launcher, CPU pinning, 30-agent
> generation, multi-session `TelemetryHub`, the 30×8760h soak test) on top of code already known to
> be correct at 1×, rather than debugging correctness and concurrency simultaneously for the first
> time under Monte Carlo load.

Audit-trail governance rule: the doc5 risk-table correction is merged only after V1 and V2 pass in
CI (or documented manual evidence). Before that point, doc5 must mark the row as
"Correction pending Phase 3.5 verification" to avoid replacing one factual mismatch with another.