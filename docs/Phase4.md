# Phase 4: Production Scale (Monte Carlo Simulation) — Implementation Plan

> **Revision note:** this draft was checked against the live repository a second time after
> initial review and corrected on six points: the `factory.jcm` agent count (13, not 12), an
> unflagged `0.0.0.0` bind on the Python daemon, a `TelemetryHub` connection-limit rule that
> incorrectly keyed exclusivity on `run_id` instead of dashboard session, a vacuous assertion in
> the seeding test, a `DatabaseArtifact` failure path that could silently drop records on a failed
> batch commit, and a missing wall-clock (39-day) success criterion from doc5 that had been
> replaced by the simulated-time (8760h) figure from doc1 instead of checking both. All six are
> fixed in place below.

## Background

Phases 1–3 are complete per `docs/phases_archive/Phase1.md`, `docs/phases_archive/Phase2.md`, and
`docs/phases_archive/Phase3.md`: the physical layer (PEMFC electrochemistry, stack thermal
submodel, BoP components), the JVM cognitive layer (eight CArtAgO artifacts, three Jason agents,
the gRPC bridge), and organizational flexibility (PROSA ⇄ ADACOR two-phase commit,
`SupervisorArtifact`, schema-epoch validation) are implemented and verified.
`docs/phases_archive/Phase3.md` ends by handing off explicitly:

> *"Proceed to Phase 4: Monte Carlo production scale — 1:30 Single-JVM fan-out, 30 Python
> daemons, 8760-hour simulated years, and full burst-load historian throughput."*

This is doc5's **Phase 4: Production Scale (Monte Carlo Simulation)** — not to be confused with
the stale `docs/phases_archive/implementation_plan.md` draft, which mislabeled the visualization
dashboard as "Phase 4" before doc5/doc6 were finalized. That draft is superseded; the dashboard's
authoritative spec is doc6, and this plan treats doc6's own `[Status: Planned / Proposed (Phase 4)]`
tags (§6 WebSocket hardening, §7 Phase 4 addenda) as the dashboard's Phase 4 scope.

### Current State Audit

Before scoping work, the repository was pulled (`github.com/utczbr/Matrix_Factory`, `main`) and
checked file-by-file against the doc5 Phase 4 success criteria. Two classes of finding emerged:

**Correctly implemented already — reusable as-is:**
- `physical_engine/factory_simulation/pemfc_model.py` — `batch_polarization_sweep` uses a
  pre-allocated 2-D scratchpad indexed by `i % numba_threads`, `@njit(nogil=True, cache=True)`
  with no `get_thread_id()`, exactly per doc4 §4.2.
- `optimization/lut_manager.py` — `_generate_lut()` is correctly guarded by
  `fcntl.flock(LOCK_EX)`; `stacked_H` is declared once, not duplicated.
- `src/main/java/factory/GrpcClientBridge.java` — already sizes its executor as
  `Math.max(1, availableProcessors() / 30)` and already takes `port` as a constructor argument,
  which is exactly the shape Phase 4's fan-out needs to replicate 30 times.

**Gaps found — these block Phase 4 and are scoped below.** The doc1/doc3/doc6
`[Status: Production-Verified]` tags on some of these describe a *finalized specification*, not
verified running code; the actual files are materially behind that label:

| File | Actual state found | doc reference implying it should already exist |
|---|---|---|
| `src/main/java/factory/MainSimulator.java` | `public final int runId = 0;` hardcoded; `grpcBridge = new GrpcClientBridge(50051);` hardcoded single port | doc1 §3 "routes RPCs across 30 isolated Python daemons" |
| `factory.jcm` | One workspace, 13 agents (1 supervisor + 5 order holons + 5 resource holons + 2 AMRs), `run_id(0)` static belief on every order holon | doc1 §3 1:30 fan-out topology |
| `physical_engine/sim_bridge_server.py` | Single-daemon script; `_NUMBA_THREADS` defaults to hardcoded `2`; `serve(max_workers=4)` hardcoded; binds `0.0.0.0:{port}` (no loopback restriction); no `run_id`/`stack_id` constructor params | doc1 §3 (dynamic thread budget), doc4 §4 pt. 3 (deterministic seeding) |
| — (no such file) | No `daemon_launcher.py`, no `multiprocessing.get_context('spawn')` orchestrator, no `os.sched_setaffinity()` anywhere in the repo | doc1 §3 mandates exactly this launcher pattern |
| `src/main/java/factory/DatabaseArtifact.java` | 53 lines; synchronous `PreparedStatement.executeUpdate()` directly on the CArtAgO operation thread; no queue, no WAL pragmas, no backpressure signal | doc3 §4.1, doc5 Phase 4 criterion ("300,000-record bounded queue with adaptive drain-to-occupancy batching") |
| `src/main/java/factory/TelemetryArtifact.java` | 36 lines; the WebSocket send call is commented out (`// wsSession.getAsyncRemote().sendObject(...)`); comment reads *"the actual frontend dashboard is Phase 3"* | doc3 §4.2, doc6 §2–§5 |
| `visualization/` | Directory does not exist. No `index.html`, `dashboard.js`, `factory_layout.json`, or WebSocket server anywhere in the repo | doc6 §2–§5 marked "Production-Verified (Phase 1 & 2)" |

The practical implication: **Phase 4 cannot be scoped as "add the 30-daemon fan-out on top of a
working system."** Three pieces doc5/doc6 assume are already solid — the historian, the telemetry
pipeline, and the dashboard itself — do not exist as working code yet and are on the critical path,
because Phase 4's entire purpose (surviving 30× concurrent burst load) is the first time these
components would be exercised hard enough to matter. This plan treats them as Phase 4
prerequisites (Components E–G below) rather than pretending they're already mitigated.

---

## Scope of Phase 4

In scope, mapped to doc5's Phase 4 success criteria and doc6's Phase-4-tagged sections:

1. Deterministic 30-daemon Python launcher with per-daemon CPU/thread budget (doc1 §3).
2. Single-JVM fan-out: one JVM process driving 30 concurrent simulation runs, each bound to its
   own daemon port, under `taskset` core isolation (doc1 §3).
3. Deterministic RNG seeding wired end-to-end (`seed = stack_id ⊕ run_id`) (doc4 §4 pt. 3).
4. A real `DatabaseArtifact` — async bounded queue, WAL pragmas, backpressure/hysteresis (doc3 §4.1).
5. A real `TelemetryArtifact` + WebSocket server multiplexed across 30 runs, each tagged by
   `run_id` (doc3 §4.2, doc6 §4–§5).
6. A minimal dashboard implementing doc6's run-selector, WebGL performance-budget guard, and
   dropped-frame divergence check — the doc6 §7 Phase 4 addenda specifically (full rendering
   detail — AMR interpolation, station color states, gap recovery — is already fully specified in
   doc6 §2–§5 and is implemented following that document directly, not re-derived here).
7. Consistent gRPC executor sizing across Java and Python (doc4 §4.6).
8. WebSocket endpoint hardening (doc6 §6): loopback binding, one connection per dashboard session, publish-only.
9. A 30×8760-hour Monte Carlo soak test.

Out of scope: re-litigating Phase 1–3 physics/MAS correctness (already verified); TLS/JWT
production auth for the dashboard (doc6 §6 describes it as required for *public* exposure — Phase
4's target environment is an internal monitoring host, so this plan implements the loopback-bind
and connection-limit pieces and stubs the JWT hook rather than standing up a full auth service).

---

## Strategic Constraints

| # | Constraint | Source |
|---|---|---|
| 1 | All Phase 1–3 constraints remain in force (no relaxation of the synchronization barrier, no wall-clock timers, no `execInternalOp` broadcasts, etc.) | Phase 1–3 docs |
| 2 | `NUMBA_NUM_THREADS` must be set in the **child's target function**, before `import numba` (or anything importing it), inside a `multiprocessing.get_context('spawn')` process — never after | doc1 §3 |
| 3 | Numba thread budget and gRPC executor size must derive from the **same** `threads = max(1, os.cpu_count() // 30)` computation on both the Python daemon and the JVM channel | doc4 §4.6 |
| 4 | The JVM process must be `taskset`-pinned to a disjoint core set from all 30 daemons | doc1 §3 |
| 5 | Each daemon is pinned via `os.sched_setaffinity()` to a disjoint core set to prevent cross-NUMA migration | doc1 §3 |
| 6 | `DatabaseArtifact` is a single shared historian (not 30 per-run instances) with one bounded `ArrayBlockingQueue<>(300_000)` and adaptive drain-to-occupancy batching | doc3 §4.1, doc5 Phase 4 criteria |
| 7 | `TelemetryArtifact`'s queue and `DatabaseArtifact`'s queue remain fully independent — `database_backpressure` must never throttle telemetry | doc3 §4.1/§4.2 |
| 8 | `lastPublishedSimTimeS` (per run) advances only on confirmed WebSocket delivery, never at queue-offer time | doc3 §4.2, doc6 §5.2 |
| 9 | The visualization layer never opens any connection to a Python daemon, directly or via proxy | doc4 §1, doc6 §4.1 |
| 10 | The WebSocket endpoint is publish-only; any inbound frame closes the connection with code `1003` | doc6 §6 |
| 11 | One WebSocket connection per dashboard session; a run-switch triggers a reconnect, not a second concurrent connection | doc6 §6 |
| 12 | Seeding must be reproducible: `seed = int.from_bytes(stack_id.encode('utf-8')[:8], 'little') ^ run_id` | doc4 §4 pt. 3 |

---

## Proposed Changes

Work is organized into eight components, ordered by dependency.

---

### Component A: Deterministic Python Daemon Launcher

#### [NEW] `physical_engine/daemon_launcher.py`

A supervising parent process that spawns and monitors all 30 daemons, rather than 30
independently shell-launched processes — this gives Phase 4 centralized logging, crash-restart,
and coordinated shutdown, and is what doc1 §3 is specifying with the `_daemon_entry` pattern.

```python
"""
Monte Carlo fan-out launcher — spawns 30 isolated SimBridge daemons.

Topology (doc1 §3): ports 50051-50080, one daemon per Monte Carlo run.
Each daemon is a freshly-spawned interpreter (multiprocessing 'spawn' context,
NOT 'fork') so that NUMBA_NUM_THREADS is read by Numba at import time, before
any Numba-touching module has been imported in that process.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import sys
import time

logger = logging.getLogger(__name__)

BASE_PORT = 50051
NUM_DAEMONS = 30
# Cores reserved for the pinned JVM process (see Component C / launch_phase4.sh).
JVM_RESERVED_CORES = 2


def _daemon_entry(port: int, n_threads: int, run_id: int, core_set: list[int]) -> None:
    """Runs inside a freshly spawned child interpreter. Order is load-bearing:
    the env var MUST be set before `import numba` happens anywhere in the
    import chain — including transitively via sim_bridge_server."""
    os.environ["NUMBA_NUM_THREADS"] = str(n_threads)

    # CPU affinity — disjoint core set per daemon, prevents cross-NUMA migration.
    try:
        os.sched_setaffinity(0, core_set)
    except (AttributeError, OSError) as e:
        # sched_setaffinity is Linux-only; non-fatal on other platforms (dev/test).
        logger.warning(f"[daemon:{run_id}] CPU affinity pin skipped: {e}")

    # Only now do we import anything that touches numba.
    from physical_engine.sim_bridge_server import serve  # noqa: E402

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [run={run_id}] [%(levelname)s] %(message)s",
    )
    serve(port=port, max_workers=n_threads, run_id=run_id)


def compute_daemon_core_sets(num_daemons: int, jvm_reserved: int) -> list[list[int]]:
    """Partitions available cores into disjoint sets, one per daemon, after
    reserving `jvm_reserved` cores (0..jvm_reserved-1) for the JVM via taskset.

    Production-safe policy: strict disjoint pinning or nothing. If the host
    does not have enough cores to give the JVM its reserved set AND give
    every daemon at least one exclusive core, this fails fast rather than
    silently falling back to shared/overlapping core sets — a silent
    fallback here would defeat the entire point of Strategic Constraints
    4 and 5 without giving any signal that isolation was lost."""
    total_cores = os.cpu_count() or num_daemons
    required = jvm_reserved + num_daemons
    if total_cores < required:
        raise RuntimeError(
            f"Phase 4 requires at least {required} CPU cores for strict disjoint "
            f"pinning; found {total_cores}."
        )
    pool = list(range(jvm_reserved, total_cores))
    return [
        pool[i * len(pool) // num_daemons: (i + 1) * len(pool) // num_daemons]
        for i in range(num_daemons)
    ]


def main() -> None:
    ctx = multiprocessing.get_context("spawn")
    total_cores = os.cpu_count() or NUM_DAEMONS
    n_threads = max(1, total_cores // NUM_DAEMONS)
    core_sets = compute_daemon_core_sets(NUM_DAEMONS, JVM_RESERVED_CORES)

    logger.info(
        f"Launching {NUM_DAEMONS} daemons: {n_threads} numba threads each, "
        f"{JVM_RESERVED_CORES} cores reserved for JVM (of {total_cores} total)."
    )

    processes: dict[int, multiprocessing.process.BaseProcess] = {}
    for run_id in range(NUM_DAEMONS):
        port = BASE_PORT + run_id
        p = ctx.Process(
            target=_daemon_entry,
            args=(port, n_threads, run_id, core_sets[run_id]),
            name=f"simbridge-daemon-{run_id}",
            daemon=False,
        )
        p.start()
        processes[run_id] = p
        logger.info(f"[run={run_id}] started pid={p.pid} port={port}")

    shutdown = {"flag": False}

    def _handle_sigterm(signum, frame):
        shutdown["flag"] = True

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    # Supervise: restart any daemon that dies unexpectedly (crash resilience
    # for 8760h × 30 runs — a single daemon crash must not abort the batch).
    while not shutdown["flag"]:
        time.sleep(2.0)
        for run_id, p in list(processes.items()):
            if not p.is_alive() and not shutdown["flag"]:
                logger.error(f"[run={run_id}] daemon died (exitcode={p.exitcode}) — restarting")
                port = BASE_PORT + run_id
                new_p = ctx.Process(
                    target=_daemon_entry,
                    args=(port, n_threads, run_id, core_sets[run_id]),
                    name=f"simbridge-daemon-{run_id}",
                )
                new_p.start()
                processes[run_id] = new_p

    logger.info("Shutdown signal received — terminating all daemons.")
    for run_id, p in processes.items():
        p.terminate()
    for run_id, p in processes.items():
        p.join(timeout=10)
        if p.is_alive():
            logger.warning(f"[run={run_id}] did not exit cleanly — killing")
            p.kill()


if __name__ == "__main__":
    main()
```

---

### Component B: `sim_bridge_server.py` — Fixes

#### [MODIFIED] `physical_engine/sim_bridge_server.py`

Three targeted changes; the `AdvanceTime`/`RunBatchTest`/`HealthCheck` RPC logic and the
`_physics_step_lock` pattern are unchanged.

**1. Remove the hardcoded thread default; the value must come from the launcher's env
injection only, so a missing env var fails loud instead of silently capping at 2:**

```python
# Before:
_NUMBA_THREADS = int(os.environ.get("NUMBA_NUM_THREADS", "2"))
os.environ.setdefault("NUMBA_NUM_THREADS", str(_NUMBA_THREADS))

# After: no silent default under the Phase 4 launcher. Standalone single-daemon
# runs (dev/test) still work via the explicit CLI default in serve().
_NUMBA_THREADS = int(os.environ["NUMBA_NUM_THREADS"]) if "NUMBA_NUM_THREADS" in os.environ else None
```

**2. `SimBridgeServicer` gains `run_id` and a seeded RNG, per doc4 §4 pt. 3:**

```python
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
    # Deterministic seed: immune to PYTHONHASHSEED randomization across the
    # 30 spawned interpreters, per doc4 §4 pt. 3.
    seed = int.from_bytes(stack_id.encode("utf-8")[:8], "little") ^ run_id
    self._rng = np.random.default_rng(seed)
    logger.info(f"[run={run_id}] seeded RNG with seed={seed} (stack_id={stack_id!r})")
```

`self._rng` is exposed for any future stochastic diagnostic sampling on the Python side
(current `AdvanceTime`/`RunBatchTest` logic is deterministic given inputs — Station 1–4
stochastics stay Java-side per doc1 §2.5 — so this establishes the plumbing doc4 mandates
without inventing new randomness that doesn't yet exist in the model).

**3. Bind loopback-only, not `0.0.0.0`.** The daemon has no business accepting connections from
anywhere but the local JVM (doc4 §1's "no direct RPCs from outside the JVM" principle applies
just as much to the daemon's own bind address as it does to the visualization layer):

```python
# Before:
bind_addr = f"0.0.0.0:{port}"

# After:
bind_addr = f"127.0.0.1:{port}"
```

**4. `serve()` takes `run_id`, and its executor size is derived from the same budget the
launcher computed — never hardcoded independently of the Numba thread count:**

```python
def serve(
    port: int = 50051,
    max_workers: int | None = None,
    num_cells: int = 200,
    R_internal: float = 0.1,
    T_initial: float = 353.15,
    run_id: int = 0,
) -> None:
    if max_workers is None:
        # Falls back to the Numba budget already established for this process
        # (doc4 §4.6: gRPC executor sized consistently with the Numba budget).
        max_workers = _NUMBA_THREADS or max(1, (os.cpu_count() or 1) // 30)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = SimBridgeServicer(
        num_cells=num_cells, R_internal=R_internal, T_initial=T_initial, run_id=run_id,
    )
    ...
```

---

### Component C: JVM CPU Isolation

#### [NEW] `scripts/launch_phase4.sh`

```bash
#!/usr/bin/env bash
# Phase 4 launch sequence: pin the JVM to reserved cores, start the daemon
# fleet, wait for readiness, then start the fan-out JVM.
set -euo pipefail

JVM_CORES="0,1"          # Must match daemon_launcher.py's JVM_RESERVED_CORES=2
NUM_DAEMONS=30
BASE_PORT=50051

echo "[phase4] starting ${NUM_DAEMONS} python daemons..."
python3 -m physical_engine.daemon_launcher &
LAUNCHER_PID=$!

echo "[phase4] waiting for all daemons to report ready..."
for i in $(seq 0 $((NUM_DAEMONS - 1))); do
  port=$((BASE_PORT + i))
  until python3 -c "
import grpc, sys
from physical_engine.protos import sim_bridge_pb2, sim_bridge_pb2_grpc
ch = grpc.insecure_channel('127.0.0.1:${port}')
stub = sim_bridge_pb2_grpc.SimBridgeStub(ch)
r = stub.HealthCheck(sim_bridge_pb2.Empty(), timeout=1)
sys.exit(0 if r.ready else 1)
" 2>/dev/null; do
    sleep 0.5
  done
  echo "[phase4]   daemon run_id=${i} port=${port} ready"
done

echo "[phase4] all daemons ready — starting JVM pinned to cores ${JVM_CORES}"
taskset -c "${JVM_CORES}" ./gradlew run --args="--phase4 --run-count=${NUM_DAEMONS} --base-port=${BASE_PORT}"

kill "${LAUNCHER_PID}" 2>/dev/null || true
```

---

### Component D: Single-JVM 1:30 Fan-Out — `MainSimulator` and `factory.jcm`

This is the architectural core of Phase 4. `MainSimulator` currently assumes it is the only
simulation instance in the JVM (`public final int runId = 0`, one hardcoded `GrpcClientBridge`).
Hand-authoring 30 copies of the 13-agent block in `factory.jcm` (390 agents) is both unwieldy and
almost certainly too much concurrent BDI reasoning for two reserved JVM cores — so population
per run is a tunable, not a fixed copy of the Phase 3 config, and must be validated empirically
(see Verification V4).

#### [NEW] `scripts/generate_factory_jcm.py`

Generates `factory_phase4.jcm` programmatically instead of hand-duplicating agent blocks. Takes
`--run-count` and `--orders-per-run` (default lower than Phase 3's 5, pending V4 tuning) and
emits one workspace + one agent set per run, each wired to its own `GrpcClientBridge` port and
`run_id` belief, but sharing the **single** `database` and `telemetry` artifacts declared once at
the top level:

```python
# scripts/generate_factory_jcm.py (excerpt — template rendering, not full listing)
TEMPLATE_WORKSPACE = """
    workspace factory_ws_run_{run_id} {{
        artifact base_station_1  : factory.BaseStationArtifact("S1", 1, 45.0,  5.0,  0.005, {run_id})
        artifact base_station_2  : factory.BaseStationArtifact("S2", 2, 120.0, 15.0, 0.012, {run_id})
        artifact base_station_3  : factory.BaseStationArtifact("S3", 3, 30.0,  2.0,  0.002, {run_id})
        artifact base_station_4  : factory.BaseStationArtifact("S4", 4, 240.0, 30.0, 0.008, {run_id})
        artifact test_bench      : factory.TestBenchArtifact("S5", {run_id})
        artifact amr_artifact    : factory.AMRArtifact(20, 12, 2)
        artifact utility_system  : factory.UtilitySystemArtifact()
        artifact timer_artifact  : factory.TimerArtifact()
        artifact energy_price    : factory.EnergyPriceArtifact("price_series.csv")
        artifact supervisor_artifact : factory.SupervisorArtifact()
        // NOTE: no per-run `database` or `telemetry` artifact — both are
        // shared singletons declared once (see below), reached via
        // HistorianWriter/TelemetryHub, not per-workspace CArtAgO artifacts.
    }}
"""
# Top-level (once): artifact database : factory.DatabaseArtifact("factory_history.db")
#                    artifact telemetry : factory.TelemetryArtifact(8080)
# ... (agent blocks per run, `beliefs: run_id({run_id})`, omitted for brevity —
#      mechanically identical to the Phase 3 order_holon/resource_holon/amr_agent
#      blocks, just parameterized and repeated `run_count` times.)
```

#### [MODIFIED] `src/main/java/factory/MainSimulator.java`

Converts the class from an implicit singleton to a per-run instantiable object, managed by a new
`RunManager`.

```java
// Before: public final int runId = 0;  and a hardcoded GrpcClientBridge(50051)

public class MainSimulator {
    private final int runId;
    private final GrpcClientBridge grpcBridge;
    private final AtomicInteger schemaEpoch = new AtomicInteger(0);
    private volatile String activeOrgSchema = "centralized";
    private long sequenceNumber = 0;

    public MainSimulator(int runId, int port) {
        this.runId = runId;
        this.grpcBridge = new GrpcClientBridge(port);
    }

    public void start() {
        grpcBridge.pollUntilReady();   // per-run HealthCheck polling, doc1 §2.4
        // ... tick loop unchanged from Phase 3, except:
        //   - setRunId(runId) added to every TelemetryFrame.Builder
        //   - frame handed to TelemetryHub.publish(runId, frameBytes) instead of
        //     a per-workspace TelemetryArtifact.broadcast() call
        //   - DB writes go through HistorianWriter.enqueue(runId, ...) instead
        //     of a per-workspace DatabaseArtifact
    }

    public int getRunId() { return runId; }
    public GrpcClientBridge getGrpcBridge() { return grpcBridge; }
}
```

#### [NEW] `src/main/java/factory/RunManager.java`

```java
package factory;

import java.util.List;
import java.util.concurrent.*;

/**
 * Owns all 30 MainSimulator instances inside this single JVM process.
 * Each run's tick loop is a lightweight cooperative task — BDI reasoning
 * and TelemetryFrame assembly are cheap; the RPC latency to each run's
 * daemon is hidden by the non-blocking CArtAgO await() pattern already
 * used by TestBenchArtifact (doc1 §2.1), so 30 runs share the JVM's
 * pinned cores via a bounded pool rather than one thread each.
 */
public class RunManager {
    private final List<MainSimulator> runs;
    private final ExecutorService tickExecutor;

    public RunManager(int runCount, int basePort) {
        this.runs = new java.util.ArrayList<>(runCount);
        for (int i = 0; i < runCount; i++) {
            runs.add(new MainSimulator(i, basePort + i));
        }
        // Bounded — matches doc4 §4.6's discipline: no unbounded cached pool,
        // even on the tick-orchestration side.
        int poolSize = Math.max(2, Runtime.getRuntime().availableProcessors());
        this.tickExecutor = new ThreadPoolExecutor(
            poolSize, poolSize, 0L, TimeUnit.MILLISECONDS,
            new LinkedBlockingQueue<>(runCount * 2),
            new ThreadPoolExecutor.CallerRunsPolicy()
        );
    }

    public void startAll() {
        for (MainSimulator sim : runs) {
            tickExecutor.submit(sim::start);
        }
    }

    public void shutdownAll() {
        for (MainSimulator sim : runs) sim.getGrpcBridge().shutdown();
        tickExecutor.shutdown();
    }

    public List<MainSimulator> getRuns() { return runs; }
}
```

> **Open tuning question (resolve via Verification V4):** how many order holons per run is
> sustainable on 2 reserved JVM cores × 30 runs? Phase 3's 5-order-holon population was sized
> for a *single* run with the whole JVM available. Start `generate_factory_jcm.py` at
> `--orders-per-run=2` and increase only if V4's cycle-latency budget has headroom.

---

### Component E: `DatabaseArtifact` — Real Implementation (Prerequisite Fix)

#### [REWRITTEN] `src/main/java/factory/DatabaseArtifact.java`

Replaces the 53-line synchronous stub. Per Strategic Constraint 6, this is a **single shared**
historian across all 30 runs — one `ArrayBlockingQueue<>(300_000)`, one writer thread, one SQLite
connection, with a `run_id` column distinguishing rows.

```java
package factory;

import cartago.*;
import java.sql.*;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class DatabaseArtifact extends Artifact {
    private static final Logger logger = LoggerFactory.getLogger(DatabaseArtifact.class);
    private static final int QUEUE_CAPACITY = 300_000;
    private static final int MAX_BATCH = 2_000;
    private static final long DRAIN_INTERVAL_MS = 500;
    private static final int BACKPRESSURE_HIGH = QUEUE_CAPACITY; // full → signal
    private static final int HYSTERESIS_LOW = 3_000;              // per doc3 §4.1

    private Connection conn;
    private final ArrayBlockingQueue<Record> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final AtomicBoolean backpressureActive = new AtomicBoolean(false);
    private Thread drainThread;
    private volatile boolean running = true;

    private sealed interface Record permits StartRecord, FinishRecord {}
    private record StartRecord(int runId, String orderId, double simTime) implements Record {}
    private record FinishRecord(int runId, String orderId, double simTime,
                                 double revenue, double penalty) implements Record {}

    void init(String dbPath) {
        try {
            conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath);
            try (Statement stmt = conn.createStatement()) {
                // WAL + tuned checkpointing, per doc3 §4.1 — prevents multi-GB
                // WAL ballooning under the 1:30 fan-out burst load.
                stmt.execute("PRAGMA journal_mode=WAL");
                stmt.execute("PRAGMA wal_autocheckpoint=100");
                stmt.execute("PRAGMA synchronous=NORMAL");
                stmt.execute("CREATE TABLE IF NOT EXISTS Orders (" +
                    "run_id INTEGER, " +
                    "order_id TEXT, " +
                    "received_time REAL, " +
                    "finished_time REAL, " +
                    "revenue REAL, " +
                    "penalty REAL, " +
                    "PRIMARY KEY (run_id, order_id))");
            }
        } catch (SQLException e) {
            failed("DatabaseArtifact init failed: " + e.getMessage());
            return;
        }

        drainThread = new Thread(this::drainLoop, "database-artifact-drain");
        drainThread.setDaemon(true);
        drainThread.start();
    }

    // ── Non-blocking enqueue API — called by MainSimulator/HistorianWriter,
    //    never by a CArtAgO @OPERATION directly, so no run's tick loop ever
    //    blocks on SQLite. ────────────────────────────────────────────────
    public boolean enqueueStart(int runId, String orderId, double simTime) {
        return offerWithBackpressureCheck(new StartRecord(runId, orderId, simTime));
    }

    public boolean enqueueFinish(int runId, String orderId, double simTime,
                                  double revenue, double penalty) {
        return offerWithBackpressureCheck(
            new FinishRecord(runId, orderId, simTime, revenue, penalty));
    }

    private boolean offerWithBackpressureCheck(Record r) {
        boolean enqueued = queue.offer(r);   // never blocks
        if (!enqueued) {
            if (backpressureActive.compareAndSet(false, true)) {
                signal("database_backpressure");
                logger.warn("DatabaseArtifact queue full ({}). Backpressure engaged.",
                    QUEUE_CAPACITY);
            }
        }
        return enqueued;
    }

    // ── Drain loop: adaptive batch size proportional to occupancy, evaluated
    //    every 500ms, per doc3 §4.1. ──────────────────────────────────────
    private void drainLoop() {
        while (running) {
            try {
                Thread.sleep(DRAIN_INTERVAL_MS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            int batchSize = Math.min(MAX_BATCH, queue.size());
            if (batchSize == 0) continue;

            // Drain into a local buffer first — do NOT let poll() be the only
            // copy of these records. If the batch insert below fails, the
            // buffer is re-offered to the queue so nothing is silently lost
            // (an earlier draft polled and discarded on rollback).
            java.util.List<Record> batch = new java.util.ArrayList<>(batchSize);
            for (int i = 0; i < batchSize; i++) {
                Record r = queue.poll();
                if (r == null) break;
                batch.add(r);
            }

            try {
                conn.setAutoCommit(false);
                try (PreparedStatement startStmt = conn.prepareStatement(
                        "INSERT OR IGNORE INTO Orders (run_id, order_id, received_time) " +
                        "VALUES (?, ?, ?)");
                     PreparedStatement finishStmt = conn.prepareStatement(
                        "UPDATE Orders SET finished_time=?, revenue=?, penalty=? " +
                        "WHERE run_id=? AND order_id=?")) {

                    for (Record r : batch) {
                        switch (r) {
                            case StartRecord s -> {
                                startStmt.setInt(1, s.runId());
                                startStmt.setString(2, s.orderId());
                                startStmt.setDouble(3, s.simTime());
                                startStmt.addBatch();
                            }
                            case FinishRecord f -> {
                                finishStmt.setDouble(1, f.simTime());
                                finishStmt.setDouble(2, f.revenue());
                                finishStmt.setDouble(3, f.penalty());
                                finishStmt.setInt(4, f.runId());
                                finishStmt.setString(5, f.orderId());
                                finishStmt.addBatch();
                            }
                        }
                    }
                    // NOTE: a FinishRecord for an order whose StartRecord is
                    // still sitting in the queue (not yet drained) is a no-op
                    // UPDATE here — it will correctly match once that
                    // StartRecord's INSERT lands in a later batch, because
                    // TelemetryFrame/MainSimulator only ever enqueues Finish
                    // after Start for the same order_id (single-threaded per
                    // run tick loop). This ordering guarantee is what makes
                    // INSERT-then-UPDATE safe; it is NOT safe if any future
                    // caller enqueues Finish from a different thread without
                    // that same-order Start-before-Finish guarantee.
                    startStmt.executeBatch();
                    finishStmt.executeBatch();
                    conn.commit();
                } catch (SQLException inner) {
                    conn.rollback();
                    throw inner;
                }
            } catch (SQLException e) {
                logger.error("Drain batch of {} records failed, re-queuing: {}",
                    batch.size(), e.getMessage());
                // Re-offer failed records to the front of processing on the
                // next cycle. If the queue is near capacity this may itself
                // trigger backpressure, which is the correct signal — a
                // persistently failing batch (e.g. schema mismatch) should
                // surface as sustained backpressure, not silent data loss.
                for (Record r : batch) {
                    if (!queue.offer(r)) {
                        logger.error("Record dropped after failed re-queue attempt: {}", r);
                    }
                }
            }

            // Hysteresis: lift backpressure once occupancy falls below 3,000.
            if (backpressureActive.get() && queue.size() < HYSTERESIS_LOW) {
                backpressureActive.set(false);
                signal("database_pressure_normal");
                logger.info("DatabaseArtifact backpressure lifted (queue size < {}).",
                    HYSTERESIS_LOW);
            }
        }
    }

    void shutdownArtifact() {
        running = false;
        if (drainThread != null) drainThread.interrupt();
        try { if (conn != null) conn.close(); } catch (SQLException ignored) {}
    }
}
```

`MainSimulator.onStepReady()` (per run) calls `databaseArtifact.enqueueStart(runId, ...)` /
`enqueueFinish(runId, ...)` directly on the shared instance — there is exactly one
`DatabaseArtifact` for the whole JVM, declared once in `factory.jcm`, referenced by all 30
`MainSimulator` instances (injected via `RunManager` at startup, same pattern as Phase 3's
`SupervisorArtifact.setMainSimulator()` wiring).

---

### Component F: `TelemetryArtifact` + WebSocket Server — Real Implementation

#### [REWRITTEN] `src/main/java/factory/TelemetryArtifact.java`

Replaces the 36-line stub. Becomes a `TelemetryHub`-backed multiplexer: one
`AtomicReference<TelemetryFrameSnapshot>` slot per run, one non-blocking WebSocket endpoint per
connected browser client, each client subscribed to exactly one `run_id` at a time.

```java
package factory;

import cartago.*;
import jakarta.websocket.*;
import jakarta.websocket.server.ServerEndpoint;
import java.nio.ByteBuffer;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TelemetryArtifact extends Artifact {
    private static final Logger logger = LoggerFactory.getLogger(TelemetryArtifact.class);
    private static final double TARGET_HZ = 18.0; // within doc6's 15-20Hz band
    private static final double FRAME_INTERVAL_S = 1.0 / TARGET_HZ;

    // One slot per run_id — wait-free publish per doc1 §2.6.
    private final AtomicReference<byte[]>[] latestFrame;
    private final double[] lastPublishedSimTimeS;
    private final AtomicInteger[] droppedFrameCount;
    private int runCount;

    @SuppressWarnings("unchecked")
    void init(int port, int runCount) {
        this.runCount = runCount;
        this.latestFrame = new AtomicReference[runCount];
        this.lastPublishedSimTimeS = new double[runCount];
        this.droppedFrameCount = new AtomicInteger[runCount];
        for (int i = 0; i < runCount; i++) {
            latestFrame[i] = new AtomicReference<>(null);
            droppedFrameCount[i] = new AtomicInteger(0);
        }
        TelemetryHub.INSTANCE.attach(this);
        // WebSocket server (jakarta.websocket-compatible embedded container,
        // e.g. Tyrus standalone) is started by TelemetryHub, bound to
        // 127.0.0.1 only (doc6 §6) — see TelemetryWebSocketEndpoint below.
        logger.info("TelemetryArtifact listening on 127.0.0.1:{} for {} runs", port, runCount);
    }

    /** Called by each run's MainSimulator once per tick, after decimation gate. */
    public void publish(int runId, double simTimeS, byte[] frameBytes) {
        double sinceLast = simTimeS - lastPublishedSimTimeS[runId];
        if (sinceLast < FRAME_INTERVAL_S) return; // simulation-time decimation gate

        latestFrame[runId].set(frameBytes); // wait-free
        // lastPublishedSimTimeS advances only in onDeliveryConfirmed(), never here —
        // this preserves the "one retry opportunity" semantics of doc6 §5.2.
        TelemetryHub.INSTANCE.notifyNewFrame(runId, frameBytes);
    }

    void onDeliveryConfirmed(int runId, double simTimeS) {
        lastPublishedSimTimeS[runId] = simTimeS;
    }

    void onDeliveryFailed(int runId) {
        droppedFrameCount[runId].incrementAndGet();
    }

    public int getDroppedCount(int runId) { return droppedFrameCount[runId].get(); }
}
```

#### [NEW] `src/main/java/factory/TelemetryHub.java`

```java
package factory;

import jakarta.websocket.*;
import jakarta.websocket.server.ServerEndpoint;
import jakarta.websocket.server.ServerEndpointConfig;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Singleton fan-out point between the 30 MainSimulator run loops and any
 * number of WebSocket client sessions. Each session subscribes to exactly
 * one run_id (chosen at connect time via a query parameter), per doc6 §6's
 * "one connection per dashboard session, reconnect on run switch" model.
 */
public enum TelemetryHub {
    INSTANCE;

    // sessionId -> subscribed run_id
    private final Map<String, Integer> sessionRunId = new ConcurrentHashMap<>();
    private final Map<String, Session> sessions = new ConcurrentHashMap<>();
    private TelemetryArtifact artifact;

    void attach(TelemetryArtifact artifact) {
        this.artifact = artifact;
        // Start the embedded WS server here (Tyrus/Jetty), registering
        // TelemetryWebSocketEndpoint bound to 127.0.0.1 only (doc6 §6).
    }

    // clientToken -> currently-open session for that browser client. A "dashboard
    // session" is identified by a client-generated token carried as a second query
    // param (?client=<uuid>, minted once by dashboard.js on first load and reused
    // across reconnects) — NOT by run_id. Two different operators watching the
    // SAME run_id concurrently is a valid use case and must not be blocked; only
    // the SAME client opening a second connection (e.g. its own run-switch) may
    // supersede its own prior connection. This corrects an earlier draft that
    // mistakenly keyed exclusivity on run_id instead of on the client/session.
    private final Map<String, Session> sessionByClientToken = new ConcurrentHashMap<>();

    void registerSession(Session session, int runId, String clientToken) {
        // Enforce one connection per dashboard session (doc6 §6): if THIS client
        // already has an open connection (from a prior run-switch reconnect that
        // raced, or a stale tab), close it with 4001 before adopting the new one.
        Session prior = sessionByClientToken.get(clientToken);
        if (prior != null && prior.isOpen() && !prior.getId().equals(session.getId())) {
            try {
                prior.close(new CloseReason(
                    new CloseReason.CloseCode() { public int getCode() { return 4001; } },
                    "SUPERSEDED"));
            } catch (Exception ignored) {}
        }
        sessionByClientToken.put(clientToken, session);
        sessions.put(session.getId(), session);
        sessionRunId.put(session.getId(), runId);
    }

    void unregisterSession(Session session) {
        sessions.remove(session.getId());
        sessionRunId.remove(session.getId());
        sessionByClientToken.values().remove(session); // no-op if already superseded
    }

    void notifyNewFrame(int runId, byte[] frameBytes) {
        for (Map.Entry<String, Integer> e : sessionRunId.entrySet()) {
            if (e.getValue() != runId) continue;
            Session s = sessions.get(e.getKey());
            if (s == null || !s.isOpen()) continue;

            // Strictly non-blocking async send (doc3 §4.2, doc6 §5.3).
            s.getAsyncRemote().sendBinary(
                java.nio.ByteBuffer.wrap(frameBytes),
                result -> {
                    if (result.isOK()) {
                        artifact.onDeliveryConfirmed(runId, extractSimTimeS(frameBytes));
                    } else {
                        artifact.onDeliveryFailed(runId);
                    }
                }
            );
        }
    }

    // Note (multi-viewer semantics): droppedTelemetryFrameCount is counted per
    // failed async send attempt, aggregated at run level — a run with N
    // concurrently subscribed dashboard sessions can accumulate up to N
    // failed-send events per dropped frame, not one. Any divergence check
    // against a browser-side drop counter is therefore only directly
    // comparable in single-viewer-per-run mode; with multiple concurrent
    // viewers on the same run_id, the server-side count must be normalized
    // by the number of active sessions for that run before comparing against
    // any single client's drop counter.
    private double extractSimTimeS(byte[] frameBytes) {
        // Parsed from the already-serialized TelemetryFrame (field 2).
        try {
            return TelemetryFrameOuterClass.TelemetryFrame.parseFrom(frameBytes).getSimTimeS();
        } catch (Exception e) {
            return Double.NaN;
        }
    }
}
```

```java
// TelemetryWebSocketEndpoint.java (sketch) — the JSR-356 endpoint TelemetryHub registers.
@ServerEndpoint("/telemetry")
public class TelemetryWebSocketEndpoint {
    @OnOpen
    public void onOpen(Session session, EndpointConfig config) {
        Map<String, java.util.List<String>> params = session.getRequestParameterMap();
        int runId = Integer.parseInt(params.getOrDefault("run_id", java.util.List.of("0")).get(0));
        String clientToken = params.getOrDefault("client", java.util.List.of(session.getId())).get(0);
        TelemetryHub.INSTANCE.registerSession(session, runId, clientToken);
    }

    @OnMessage
    public void onMessage(Session session, ByteBuffer msg) {
        // Publish-only channel (doc6 §6): any inbound frame is rejected.
        try {
            session.close(new CloseReason(CloseReason.CloseCodes.CANNOT_ACCEPT, "UNSUPPORTED_DATA"));
        } catch (Exception ignored) {}
    }

    @OnClose
    public void onClose(Session session) {
        TelemetryHub.INSTANCE.unregisterSession(session);
    }
}
```

> **Binding:** the embedded WS container (Tyrus standalone, matching the `jakarta.websocket`
> dependency already present in `TelemetryArtifact.java`'s imports) must be configured to bind
> `127.0.0.1` only, per doc6 §6 and Strategic Constraint 9 — no public interface. The commented-out
> `wss://`/JWT path in doc6 §6 is out of scope for this internal-monitoring deployment; the hook is
> left as a `TODO` on `TelemetryWebSocketEndpoint.onOpen` for a later hardening pass.

---

### Component G: Minimal Dashboard — Phase 4 Addenda Only

`visualization/` does not exist yet, so it must be created from scratch. doc6 §2–§5 is the
complete, already-frozen rendering spec (Canvas 2D floor layer, AMR interpolation, gap recovery,
500ms interruption handling) — that is implemented directly from doc6, not redesigned here. This
component lists only the Phase 4-specific additions doc6 §7 calls out, layered on top:

#### [NEW] `visualization/index.html`, `visualization/dashboard.js`, `visualization/factory_layout.json`, `visualization/protobuf_decoder.js`

Base skeleton per doc6 §2.1–§2.5 (two-layer canvas stack, `VisualStateBuffer`, rAF loop,
`protobufjs`-based `TelemetryFrame.decode()`).

#### Phase 4 addenda on top of the base skeleton:

**Run selector (doc6 §7):**
```javascript
// HUD dropdown — switching run_id closes the current WebSocket and reconnects
// with a new ?run_id= query param, per doc6 §6's "graceful reconnect" model.
// Minted once per tab load, persists across reconnects — this is the identity
// the server uses to know "is this the same dashboard session reconnecting"
// versus "a different operator watching the same run_id" (doc6 §6).
const CLIENT_TOKEN = crypto.randomUUID();

function switchRun(newRunId) {
  if (ws) ws.close(1000, "run switch");
  ws = new WebSocket(`ws://127.0.0.1:8080/telemetry?run_id=${newRunId}&client=${CLIENT_TOKEN}`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = handleTelemetryFrame;
  currentRunId = newRunId;
}
```

**WebGL overlay self-disabling budget guard (doc6 §7):**
```javascript
function renderThermalOverlay() {
  const t0 = performance.now();
  drawWebGLHeatmap();
  const dt = performance.now() - t0;
  if (dt > 4.0) {
    thermalOverlayEnabled = false;
    console.warn("[Dashboard] WebGL overlay disabled: budget exceeded");
  }
}
```

**Dropped-frame divergence alert (doc6 §7):**
```javascript
function checkDropDivergence(frame) {
  const divergence = Math.abs(clientDroppedFrameCount - frame.droppedTelemetryFrameCount)
                      / Math.max(1, frame.sequenceNumber);
  if (divergence > 0.005) {
    console.error(
      `[Dashboard] Drop divergence ${(divergence*100).toFixed(2)}% — ` +
      `frames dropped before the WebSocket boundary, not just at the TCP edge.`
    );
  }
}
```

The remainder of the rendering pipeline (AMR extrapolation, station color map, gap-recovery
rebasing, 500ms interruption banner) follows doc6 §2.3–§5.5 verbatim.

---

### Component H: Seeding & Determinism — Verification Wiring

#### [NEW] `physical_engine/factory_simulation/seeding_test.py`

```python
"""Verifies the doc4 §4 pt.3 seeding formula is stable and collision-free
across all 30 run_ids for a fixed stack_id, and across the 5 station stack_ids
used in Phase 3's factory.jcm (S1..S5)."""
import itertools
from physical_engine.sim_bridge_server import SimBridgeServicer


def test_seed_determinism_across_runs():
    seeds = set()
    for run_id in range(30):
        svc = SimBridgeServicer(run_id=run_id, stack_id="S5")
        seed = int.from_bytes("S5".encode("utf-8")[:8], "little") ^ run_id
        assert seed not in seeds, f"seed collision at run_id={run_id}"
        seeds.add(seed)


def test_seed_reproducible_same_run_id():
    svc_a = SimBridgeServicer(run_id=7, stack_id="S5")
    svc_b = SimBridgeServicer(run_id=7, stack_id="S5")
    # Same (stack_id, run_id) must produce an identical seed and therefore an
    # identical RNG stream — check the actual bit_generator state, not a live
    # draw (drawing from svc_a first would advance its state and make the two
    # streams diverge even though the seed was correct).
    assert svc_a._rng.bit_generator.state == svc_b._rng.bit_generator.state


def test_seed_differs_across_run_ids():
    svc_a = SimBridgeServicer(run_id=7, stack_id="S5")
    svc_b = SimBridgeServicer(run_id=8, stack_id="S5")
    assert svc_a._rng.bit_generator.state != svc_b._rng.bit_generator.state
```

---

## Execution Order

```
Component A ──► Component B ──► Component C
(launcher)      (server.py fixes) (taskset script)
    │
    ▼
Component E (DatabaseArtifact rewrite) ──┐
Component F (TelemetryArtifact/Hub)     ──┤── can proceed in parallel;
Component H (seeding tests)             ──┘   no inter-dependency
    │
    ▼
Component D (RunManager / MainSimulator refactor / generate_factory_jcm.py)
    — depends on E and F being ready to inject (HistorianWriter, TelemetryHub)
    │
    ▼
Component G (dashboard skeleton + Phase 4 addenda)
    — depends on F's WebSocket endpoint being live to test against
    │
    ▼
Full 30×8760h Monte Carlo soak test (Verification V7/V8)
```

---

## File Manifest

| Status | File | Component |
|---|---|---|
| NEW | `physical_engine/daemon_launcher.py` | A |
| MODIFIED | `physical_engine/sim_bridge_server.py` | B |
| NEW | `physical_engine/factory_simulation/seeding_test.py` | H |
| NEW | `scripts/launch_phase4.sh` | C |
| NEW | `scripts/generate_factory_jcm.py` | D |
| MODIFIED | `src/main/java/factory/MainSimulator.java` | D |
| NEW | `src/main/java/factory/RunManager.java` | D |
| REWRITTEN | `src/main/java/factory/DatabaseArtifact.java` | E |
| REWRITTEN | `src/main/java/factory/TelemetryArtifact.java` | F |
| NEW | `src/main/java/factory/TelemetryHub.java` | F |
| NEW | `src/main/java/factory/TelemetryWebSocketEndpoint.java` | F |
| NEW | `visualization/index.html` | G |
| NEW | `visualization/dashboard.js` | G |
| NEW | `visualization/dashboard.css` | G |
| NEW | `visualization/factory_layout.json` | G |
| NEW | `visualization/protobuf_decoder.js` | G |
| GENERATED | `factory_phase4.jcm` (via generate_factory_jcm.py) | D |

**Total: 13 new files, 2 rewritten, 1 modified**, plus one generated config. No Phase 1–3 Python
physics files or Protobuf field numbers are touched.

---

## Verification Plan

### Prerequisites

All Phase 1–3 verification steps must still pass. Then:

```bash
./gradlew compileJava
# RunManager, TelemetryHub, DatabaseArtifact (rewritten) compile cleanly.

python -m pytest physical_engine/factory_simulation/seeding_test.py -v
```

### V1 — Daemon Fleet: Deterministic Thread Injection

```bash
python3 -m physical_engine.daemon_launcher &
sleep 5
for pid in $(pgrep -f simbridge-daemon); do
  cat /proc/$pid/environ | tr '\0' '\n' | grep NUMBA_NUM_THREADS
done
# Every daemon must report the SAME value = max(1, cpu_count // 30).
# None may report the module-level default of "2" that the old code silently
# fell back to — confirms Component B's fix removed the footgun.
```

### V2 — CPU Affinity Isolation

```bash
for pid in $(pgrep -f simbridge-daemon); do
  taskset -pc $pid
done
# Each daemon's core set MUST be disjoint from every other daemon's AND
# disjoint from the JVM's taskset -c 0,1 pin. There is no shared/overlapping
# fallback: if the host has fewer than JVM_RESERVED_CORES + NUM_DAEMONS cores,
# daemon_launcher.py raises RuntimeError at startup instead of silently
# assigning overlapping core sets (compute_daemon_core_sets, Component A).
```

### V3 — gRPC Executor / Numba Thread Consistency

```bash
# Per daemon: confirm serve()'s ThreadPoolExecutor size equals the injected
# NUMBA_NUM_THREADS value (Component B fix #3), not the old hardcoded 4.
grep -A2 "def serve" physical_engine/sim_bridge_server.py
# max_workers must derive from _NUMBA_THREADS when not explicitly passed.
```

### V4 — Per-Run BDI Population Tuning (resolves Component D's open question)

```bash
./scripts/launch_phase4.sh --orders-per-run=2
# Measure: average CArtAgO @OPERATION dispatch latency across all 30 runs,
# sampled from MainSimulator's tick loop instrumentation.
# Target: p99 tick latency < 200ms (well inside the 500ms decimation window).
# If exceeded, reduce orders-per-run or increase JVM_RESERVED_CORES and re-run.
```

### V5 — DatabaseArtifact Burst Survival

```bash
./scripts/launch_phase4.sh --force-adacor-transition-all-runs --max-ticks=200
# During the simultaneous ADACOR Phase 1 broadcast across all 30 runs:
sqlite3 factory_history.db "SELECT run_id, COUNT(*) FROM Orders GROUP BY run_id;"
# Expected: all 30 run_ids present, no SQLITE_BUSY errors in logs, queue
# occupancy (log via drainLoop instrumentation) never exceeds 300,000,
# database_backpressure/database_pressure_normal both fire and clear cleanly.
```

### V6 — Telemetry Multi-Run Isolation & Dashboard Run Switching

```javascript
// In browser console, connected to run_id=3:
const clientToken = crypto.randomUUID();
ws = new WebSocket("ws://127.0.0.1:8080/telemetry?run_id=3&client=" + clientToken);
ws.onmessage = e => {
  const f = TelemetryFrame.decode(new Uint8Array(e.data));
  console.assert(f.runId === 3, "received frame from wrong run!", f.runId);
};
// Then call switchRun(17) from the HUD dropdown — verify the old connection
// closes (code 1000) and the new one only ever receives runId === 17 frames.
```

```bash
# Connection-limit enforcement (doc6 §6) — the rule is per-SESSION, not per-run_id:
# Case 1 (must be ALLOWED): two DIFFERENT browser tabs, each with its own
#   CLIENT_TOKEN, both open ws://.../telemetry?run_id=5. Both must stay open —
#   two operators watching the same run concurrently is a valid use case.
# Case 2 (must be REJECTED): the SAME tab's switchRun() reconnects (same
#   CLIENT_TOKEN, new run_id). The tab's PRIOR connection must receive close
#   code 4001 "SUPERSEDED" when the new one registers.
# An earlier draft of this plan enforced Case 1 as if it were Case 2 — this
# test exists specifically to catch that regression if it recurs.
```

### V7 — WebGL Overlay Auto-Disable Under Load

```bash
# Artificially throttle the monitoring machine's GPU (or run in a headless
# CI environment with software rendering) and load the dashboard.
# Browser console must show:
# "[Dashboard] WebGL overlay disabled: budget exceeded"
# Canvas 2D floor layer must continue rendering at 60fps regardless.
```

### V8 — Full 30×8760h Monte Carlo Soak Test

Two separate budgets are in play here and must both be checked — doc1 §3 specifies the
**simulated-time** span per run ("thirty 8760-hour simulated years"); doc5's Phase 4 goal
separately specifies a **wall-clock** budget for the whole campaign ("Complete thirty full Monte
Carlo evaluations over 39 days without crashing"). An earlier draft of this plan tracked only the
first and silently dropped the second — both are checked below.

```bash
START_EPOCH=$(date +%s)
./scripts/launch_phase4.sh --run-count=30 --sim-hours=8760
END_EPOCH=$(date +%s)
ELAPSED_SECONDS=$((END_EPOCH - START_EPOCH))
BUDGET_SECONDS=$((39 * 86400))
echo "Wall-clock duration: ${ELAPSED_SECONDS}s (budget: ${BUDGET_SECONDS}s)"
[ "$ELAPSED_SECONDS" -le "$BUDGET_SECONDS" ] || echo "FAIL: exceeded 39-day wall-clock budget"

# Success criteria (doc5 Phase 4):
# - Wall-clock duration ≤ 39 days for all 30 runs combined.
# - All 30 runs complete without JVM or daemon crash (daemon_launcher.py's
#   crash-restart supervision may fire but the batch must still finish).
# - factory_history.db contains complete Orders rows for all 30 run_ids.
# - dropped_ner_count and dropped_telemetry_frame_count are logged per run
#   and are observable (non-zero under load is acceptable; SILENT is not).
# - clientDroppedFrameCount vs frame.dropped_telemetry_frame_count divergence
#   < 0.5% for each run, logged at simulation end (doc6 §7).
# - No component relied on gRPC's default cached thread pool (grep for
#   `Executors.newCachedThreadPool` across src/ — must return zero matches).
```

### Phase 4 Checklist (doc5 Success Criteria Mapping)

| Criterion | Test | Pass Condition |
|---|---|---|
| Numba `prange` scratchpad pre-allocated, no NRT heap contention | (Phase 1, re-verified) | Already correct in `pemfc_model.py` — no change needed |
| `DatabaseArtifact` sustains burst telemetry via 300k bounded queue + adaptive batching | V5 | Zero `SQLITE_BUSY`, queue never exceeds capacity, backpressure/hysteresis both fire |
| WAL PRAGMAs prevent OOM/disk lockups | V5, V8 | `factory_history.db-wal` stays bounded (checked via `PRAGMA wal_checkpoint`) |
| 1:30 Single-JVM fan-out survives CPU contention via `taskset` | V2, V8 | Disjoint core sets confirmed; 8760h×30 completes |
| Daemon thread limits injected via `os.environ` before import, `spawn` context | V1 | Every daemon reports identical, correctly-derived `NUMBA_NUM_THREADS` |
| JVM + Python gRPC servers both use bounded, explicitly-sized executors | V3 | No cached-pool usage anywhere; sizes match the shared budget formula |
| No `@njit` kernel combines `cache=True` with `get_thread_id()` under `parallel=True` | (Phase 1, re-verified) | Already correct — `i % numba_threads` indexing confirmed in `pemfc_model.py` |
| `run_id` in `TelemetryFrame` correctly identifies the active run; HUD switches without JVM restart | V6 | Frame `run_id` matches subscription; reconnect confirmed, no restart |
| Telemetry consumer thread CPU footprint does not inflate under 30-daemon load | V8 | Per-run thread CPU usage ≤ `threads/30` of one core |
| WebGL overlay self-disables under budget pressure | V7 | Console log confirms auto-disable; Canvas 2D unaffected |
| Dropped-frame counters cross-validated, divergence alerted | V8 | For single-viewer-per-run validation, divergence under 0.5 percent per run; otherwise metric is normalized by active viewer sessions. |

> Phase 4 is complete when all eight verification steps pass and the checklist above is green.
> At that point the factory can execute thirty independent 8760-hour Monte Carlo replications
> inside a single pinned JVM against thirty isolated, deterministically-seeded Python daemons,
> with a shared historian that survives concurrent ADACOR bursts across all 30 runs and a
> dashboard that can inspect any one of them live without restarting the simulation.