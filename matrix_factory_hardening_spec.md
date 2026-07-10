# Matrix Factory — Hardening Specification
### AMR Planning, Test Automation, Memory Safety, Telemetry Auth, Config Generation

This is an implementation-ready spec for the five gaps identified in the audit. Every recommendation is anchored to the actual file, class, and method it modifies — nothing here is generic advice.

---

## 1. AMR Collision Avoidance — Space-Time A* over the existing reservation grid

### 1.1 Diagnosis, precisely

`AMRArtifact.java` already has half the right architecture:

```java
private String[][][] reservedBy; // [gridCols][gridRows][HORIZON_TICKS]
```

`clearExpiredReservations()` shifts this window every tick, and `refreshGridOccupancy()` writes index 0 with *actual* current AMR positions — but this is read-only telemetry. The two places that should consult it never do:

- `reserveTrajectory(Object[] trajectory, OpFeedbackParam<String> result)` — unconditionally returns `"granted"`.
- `stepAMR()`, line 522: `a.path = manhattanPath((int) a.x, (int) a.y, targetX, targetY);` — a pure L-shaped Manhattan path (horizontal run, then vertical run) with **zero** obstacle or peer-AMR awareness.

Two AMRs with intersecting Manhattan paths will occupy the same cell in the same tick. Nothing in the current code detects or prevents this.

### 1.2 Algorithm: Cooperative A* (Silver, 2005) / Windowed Space-Time A*

This is the correct fit — not full multi-agent optimal search (e.g. Conflict-Based Search), which is overkill for a 2–4 AMR fleet and adds real implementation cost for no measurable benefit at this scale. Cooperative A* is:

- **Sequential, not joint**: plan one AMR at a time, in priority order. Each already-planned AMR's reserved cells become static obstacles for the next AMR's search.
- **Polynomial**: N single-agent A* searches instead of one exponential joint search.
- **A drop-in fit for `reservedBy`**: the reservation table *is* the obstacle set.

**State space.** A node is `(x, y, t)` where `t` is a relative tick offset from now, `0 ≤ t < HORIZON_TICKS`.

**Successors of `(x, y, t)`** (5-connected: 4 directions + wait):

| Action | Result | Rejected if |
|---|---|---|
| Move N/S/E/W | `(x', y', t+1)` | out of grid bounds, `reservedBy[x'][y'][t+1] != null && != thisAmrId` (**vertex conflict**), or edge `(x',y')→(x,y)` reserved by another AMR at `t→t+1` (**swap/edge conflict** — two AMRs crossing the same edge in opposite directions in the same tick) |
| Wait | `(x, y, t+1)` | `reservedBy[x][y][t+1]` held by another AMR |
| — | any successor with `t+1 ≥ HORIZON_TICKS` | horizon exceeded → this branch fails, doesn't crash the search |

Edge conflicts need a second reservation set alongside `reservedBy`, since two cells can each be legally unoccupied at every instant while the AMRs still collide mid-edge:

```java
// Pack (x1,y1,x2,y2,t) into a long key; O(1) contains/add.
private final Set<Long> edgeReservations = ConcurrentHashMap.newKeySet();

private static long edgeKey(int x1, int y1, int x2, int y2, int t) {
    return (((long) x1) << 48) | (((long) y1) << 36) | (((long) x2) << 24) | (((long) y2) << 12) | t;
}
```

**Cost/heuristic.** `g(x,y,t) = t`. `h(x,y) = |x - goalX| + |y - goalY|` (Manhattan distance — admissible and consistent for 4-connected uniform-cost movement, and it's the exact metric `manhattanPath` already uses, so no new geometry is introduced). `f = g + h`, standard `PriorityQueue<Node>` ordered by `f` with `h` as tiebreak.

### 1.3 `reserveTrajectory()` — real implementation

```java
@OPERATION
public void reserveTrajectory(String amrId, int goalX, int goalY, OpFeedbackParam<Boolean> granted) {
    synchronized (reservedBy) {
        List<int[]> path = spaceTimeAStar(amrId, currentCell(amrId), new int[]{goalX, goalY});
        if (path == null) {
            granted.set(false);   // horizon exhausted — no safe path found
            return;
        }
        commitReservation(amrId, path);   // writes reservedBy[x][y][t] and edgeReservations
        setAmrPath(amrId, path);          // replaces the manhattanPath() assignment at line 522
        granted.set(true);
    }
}
```

Replace line 522 with a call into this path — `AMRSim.path`/`pathIndex` already exist as fields, so the consuming code in `stepAMR()` needs no change, only the source of `a.path` changes.

**On denial**, don't invent new plumbing: `amr_agent.asl` already has a working congestion-response path (`getGridUtilization` → `transport_blocked` when utilization > 0.85, feeding the existing retry/backoff logic). Route `reserveTrajectory` denial into the same signal so the existing retry envelope handles it — this is a wiring change, not a new subsystem.

### 1.4 Horizon sizing

`HORIZON_TICKS = 10` is undersized: `manhattanPath`'s own step guard allows paths up to `2*(gridCols+gridRows)+4` cells, which can exceed 10 for a factory-sized grid. Two options, in order of preference:

1. **Raise `HORIZON_TICKS`** to `gridCols + gridRows + margin`. The reservation array is `String[][][]` — at current grid sizes this is a few hundred references, trivial memory cost. Do this first; it's a one-line, low-risk fix that removes truncation risk entirely at the current fleet size.
2. **True windowed re-planning** if the fleet or grid grows enough that (1) gets expensive: only commit the first `W` ticks of a found path, and re-invoke `spaceTimeAStar` for the remaining tail as the AMR approaches the edge of the horizon. `clearExpiredReservations()` already slides the window every tick, so the mechanical hook for this already exists — it just isn't being used to trigger replanning yet.

### 1.5 Fairness note

Cooperative A* is priority-order-dependent — the AMR planned first always gets the shorter/more direct reservation. With only 2 AMRs today this is a non-issue, but if the fleet grows, rotate priority order per planning cycle (e.g., round-robin by `amrId` hash mod tick) rather than a fixed order, to avoid one AMR chronically absorbing detours.

---

## 2. JVM / MAS Automated Testing — from log-eyeballing to invariant assertions

### 2.1 What's actually wrong with `run_all_tests.sh`

It runs 9 scenario configs and writes `test_v1.log` … `test_v9.log`. There is no pass/fail signal anywhere in that pipeline — a regression only surfaces if a human rereads a log and happens to notice. Given how much of this codebase's real bug history lives in timing/concurrency (`ROOT CAUSE FIX` comments across `order_holon.asl`, `amr_agent.asl`, `resource_holon.asl`, `MainSimulator.java`, `TimerArtifact.java`), this is the highest-leverage gap in the project — precisely the bug class that's hardest to catch by eye and easiest to catch by assertion.

### 2.2 Framework

JUnit 5 is **already a `testImplementation` dependency in `build.gradle` and is currently unused.** No new dependency needed — just use what's there.

Build a thin harness that boots the simulation in-process (not via `./gradlew run` + external log scraping), so tests can assert directly against live CArtAgO artifact state:

```java
// src/test/java/factory/SimulationTestHarness.java
public class SimulationTestHarness {
    public SimRunHandle run(String jcmPath, int tickBudget, long seed) {
        // boots MainSimulator programmatically, injects seed, runs to tickBudget
        // returns handles to the live DatabaseArtifact / SupervisorArtifact / TimerArtifact
        // instances instead of forcing tests to re-parse stdout
    }
}
```

### 2.3 Concrete invariant tests (this is what "catches stuck orders / starvation" actually means)

**Liveness — no stuck orders.**
```java
@Test
void noOrderExceedsMaxLifetimeTicks() {
    SimRunHandle h = harness.run("factory.jcm", 5000, 42L);
    for (OrderRecord o : h.database().allOrders()) {
        assertTrue(o.isTerminal() || o.ageTicks() < MAX_ORDER_LIFETIME_TICKS,
            "Order " + o.id() + " stuck in state " + o.state() + " for " + o.ageTicks() + " ticks");
    }
}
```

**Conservation — nothing vanishes.**
```java
@Test
void completedPlusAbortedEqualsSubmitted() {
    SimRunHandle h = harness.run("factory.jcm", 5000, 42L);
    assertEquals(h.database().submittedCount(),
                 h.database().completedCount() + h.database().abortedCount());
}
```

**Starvation — every resource actually gets used.**
```java
@Test
void everyAmrCompletesAtLeastOneJob() {
    SimRunHandle h = harness.run("factory.jcm", 5000, 42L);
    h.amrArtifact().fleetIds().forEach(id ->
        assertTrue(h.amrArtifact().completedJobCount(id) > 0, id + " never dispatched"));
}
```

**Race reproduction via seeded replay.** The Python side already has this discipline (`seeding_test.py`) — mirror it on the JVM side instead of leaving it Python-only:

```java
@ParameterizedTest
@ValueSource(longs = {1, 2, 3, /* ... */ 500})
void invariantsHoldAcrossSeeds(long seed) {
    SimRunHandle h = harness.run("factory.jcm", 2000, seed);
    assertNoStuckOrders(h);
    assertNoDeadlockedThreads();
}
```

Turns "I read `test_v3.log` and it looked fine" into "500 seeded runs, 0 invariant violations" — the actual bar for a codebase with this much concurrency history.

**Deadlock detection as a cheap catch-all.** Given how many of the fixed bugs were races, add this as a teardown assertion in every test, not just a dedicated one:

```java
private void assertNoDeadlockedThreads() {
    long[] ids = ManagementFactory.getThreadMXBean().findDeadlockedThreads();
    assertNull(ids, "Deadlocked threads detected: " + Arrays.toString(ids));
}
```

### 2.4 Migration path

Keep `run_all_tests.sh` as an exploratory/manual tool if useful, but move CI's actual gate to `./gradlew test`. The 9 existing scenario configs (`test_v1`…`test_v9`) don't need to be thrown away — wrap each as a `@Test` that runs the scenario through the harness and asserts the invariants above, instead of just capturing stdout.

---

## 3. Memory Management — `DatabaseArtifact.qualityProfiles`

### 3.1 The actual lifecycle (this determines the right fix)

```java
private final ConcurrentHashMap<String, QualityProfile> qualityProfiles = new ConcurrentHashMap<>();
// write path: qualityProfiles.merge(stackId, delta, QualityProfile::plus);
// read path:  qualityProfiles.getOrDefault(stackId, QualityProfile.EMPTY);
```

The read path is called by Station 5 exactly once per stack, at the terminal stage of the pipeline, to build the final `BatchTestRequest`. Once that read happens, the entry is provably dead — no station downstream of S5 exists to write to it again.

That makes this **not** a generic caching problem — it's a lifecycle-tracking bug. The correct primary fix is explicit removal at the one well-defined point where a stack's profile becomes permanently unneeded:

```java
@OPERATION
public void getQualityProfile(String stackId, OpFeedbackParam<QualityProfile> out) {
    QualityProfile p = qualityProfiles.remove(stackId); // was: getOrDefault (non-removing)
    out.set(p != null ? p : QualityProfile.EMPTY);
}
```

### 3.2 Why that alone isn't sufficient — the ADACOR abort path

The abort logic visible in `Log.txt` (orders cancelled mid-flight) means some stacks legitimately **never reach Station 5** — their `qualityProfiles` entry would live forever even with the fix above, since nothing ever calls the removing read for them. This needs a second, independent safety net for orphaned entries, not just the lifecycle fix.

### 3.3 Safety net: bounded + time-boxed cache (Caffeine)

`build.gradle` already declares `mavenCentral()` as a repository, so adding Caffeine is a one-line dependency addition, not new infrastructure:

```groovy
implementation 'com.github.ben-manes.caffeine:caffeine:3.1.8'
```

```java
private final Cache<String, QualityProfile> qualityProfiles = Caffeine.newBuilder()
    .maximumSize(10_000)                       // generous multiple of realistic concurrent in-flight stacks
    .expireAfterAccess(Duration.ofMinutes(30))  // catches orphans from aborted orders
    .build();

// write: qualityProfiles.asMap().merge(stackId, delta, QualityProfile::plus);
// read + remove: QualityProfile p = qualityProfiles.asMap().remove(stackId);
```

This preserves the existing `merge`/read semantics exactly (via `.asMap()`), so no call site outside `DatabaseArtifact` needs to change.

**On the alternative you named (LRU via `LinkedHashMap`)**: technically possible via `removeEldestEntry`, but plain `LinkedHashMap` isn't thread-safe, and wrapping it in `Collections.synchronizedMap` puts a single coarse lock on a map that's currently a lock-free `ConcurrentHashMap` on a hot path called by every station on every quality-recording event. That's a real concurrency regression for zero benefit here — Caffeine gives bounded-size *and* TTL *and* stays lock-free/striped internally. Don't use the `LinkedHashMap` route on this particular map.

**Observability**: expose `qualityProfiles.estimatedSize()` in the existing telemetry frame or periodic log line, so a future leak (e.g., from a new pipeline stage bypassing S5) shows up as a metric instead of requiring another manual audit to rediscover.

---

## 4. WebSocket Telemetry Auth — short-lived signed tickets validated at handshake

### 4.1 Current state, precisely

```java
// TelemetryWebSocketEndpoint.java, @ServerEndpoint("/telemetry")
// onOpen reads run_id and client straight from query params — no validation at all.
```

```js
// dashboard.js
return `ws://127.0.0.1:8080/telemetry?run_id=${runId}&client=${CLIENT_TOKEN}`;
```

Loopback-only, plaintext, unauthenticated. `TelemetryHub` already does useful work here (per-`(client, run_id)` session exclusivity, stale-connection eviction) — but that's session bookkeeping, not access control. Anyone who can reach port 8080 can read any run's telemetry.

### 4.2 Why "ticket," not "send a JWT as a header"

Browsers' native `WebSocket` API cannot set custom headers on the handshake request — there is no way to attach `Authorization: Bearer <jwt>` to a WS connect from `dashboard.js` as written. This is exactly why every production system with this constraint (Slack RTM, AWS IoT Core, GCP) uses a **short-lived, single-use ticket passed as a query parameter**, minted by a side-channel request, rather than fighting the WS API. The ticket itself is a signed JWT — so this is the JWT-and-ticket approaches combined, not a choice between them.

### 4.3 Concrete flow

**Step 1 — issuance endpoint.** Tyrus is WS-only; add a minimal HTTP endpoint alongside it using `com.sun.net.httpserver.HttpServer` (JDK-builtin, zero new dependency):

```
GET /telemetry/ticket?run_id=3
→ 200 { "ticket": "<compact-signed-token>" }
```

**Step 2 — ticket contents**, HMAC-SHA256 signed with a server-side secret (env var — and fix the adjacent hygiene issue of not committing secrets alongside the `.db-wal` files already flagged):

```
claims = { sub: clientToken, run_id: 3, iat: now, exp: now + 10s, jti: <uuid> }
```

10 seconds is deliberately short: the ticket only needs to survive the round-trip from issuance to WS handshake, not the life of the connection.

**Step 3 — client connects** with the ticket in place of the current raw `client` param:

```
wss://host/telemetry?run_id=3&ticket=<token>
```

**Step 4 — validate at handshake, not in `onOpen`.** Use `ServerEndpointConfig.Configurator.modifyHandshake()`, which runs during the HTTP Upgrade — *before* any WS session is created:

```java
public class TicketAuthConfigurator extends ServerEndpointConfig.Configurator {
    @Override
    public void modifyHandshake(ServerEndpointConfig sec, HandshakeRequest req, HandshakeResponse res) {
        String ticket = queryParam(req, "ticket");
        String runId  = queryParam(req, "run_id");
        Claims c = verifyAndParse(ticket);              // signature + exp check
        if (c == null || !c.runId().equals(runId) || alreadyConsumed(c.jti())) {
            throw new HandshakeRejectedException(401);  // rejected before upgrade completes
        }
        markConsumed(c.jti());                            // single-use; tiny short-TTL set, tickets live ≤10s
    }
}
```

This closes an **authorization** gap, not just authentication: the check confirms the ticket's `run_id` claim matches the `run_id` being requested, so a valid ticket for run 3 can't be replayed against run 7's stream.

**Step 5 — per-frame cost.** Because the ticket is validated once at handshake, there's zero added overhead on the actual high-frequency telemetry stream afterward — exactly the property you need for a telemetry channel, versus a scheme that re-validates a signature per message.

### 4.4 Transport

Terminate TLS at a reverse proxy (nginx/Caddy) in front of Tyrus rather than configuring `SSLContext` inside Tyrus directly — simpler operationally, and consistent with treating this as "fine on loopback today, needs to not stay that way."

### 4.5 Library choice

The ticket is only ever minted and verified by this same server — it doesn't need external interop. A hand-rolled `javax.crypto.Mac`-based HMAC signer (a few dozen lines, zero new dependency) is the better fit for this project's minimal-dependency style than pulling in a full JWT library like `com.auth0:java-jwt`. Use the latter only if there's a reason to want standards-compliant JWTs elsewhere in the system.

---

## 5. Template Drift — stop having two hand-maintained files, then add a structural check

### 5.1 The actual bug, confirmed by tracing the call chain

- `factory.jcm` (working, hand-patched) focuses `amr_1`/`amr_2` on `factory_ws.timer_artifact`.
- `factory.jcm.template` (the Phase 4 generator's base) does not.
- `amr_agent.asl` calls `cancelTimer(OrderId, Me)` with **no explicit `[artifact_name(...)]` annotation** — it relies entirely on ambient focus.
- `scripts/generate_factory_jcm.py` builds all 30 Phase 4 workspaces from the template via regex rewriting.

Result: every AMR agent in a Phase 4 run silently lacks the focus it needs to cancel timers on abort — a regression that has probably never fired because Phase 4 hasn't been soak-tested yet, and would surface confusingly deep into a long run.

### 5.2 Immediate patch (do this regardless of anything else below)

Add `factory_ws.timer_artifact` to the `amr_1`/`amr_2` focus lines in `factory.jcm.template` to match `factory.jcm`.

### 5.3 Root cause: two files that can drift is the actual defect

The one-line patch above fixes today's instance; it doesn't prevent the next one. The structural problem is that `factory.jcm` and `factory.jcm.template` are independently hand-edited near-duplicates. The fix that removes the *class* of bug is to stop having two sources of truth:

1. **Single declarative manifest.** Define agents and their focus lists once:

```yaml
# config/agents_manifest.yaml
agents:
  - name: amr_1
    asl: amr_agent.asl
    focus: [amr_artifact, supervisor_artifact, timer_artifact]
  - name: amr_2
    asl: amr_agent.asl
    focus: [amr_artifact, supervisor_artifact, timer_artifact]
  # ...
```

2. **Generate both outputs from this one manifest** — `factory.jcm` becomes a build artifact (`generate_factory_jcm.py --run-count 1 --output factory.jcm`, wired as a Gradle task dependency), not a hand-edited file that can silently diverge from the template. There is then structurally only one place focus bindings are ever written.

3. **Prefer a real templating engine (Jinja2) over hand-rolled regex substitution** for the actual JCM text generation. The current `\b{token}\b`-boundary regex approach is careful, but it's still string-rewriting a config format rather than generating it from structure — every future template edit re-opens the same risk class. Jinja2's `{% for %}` blocks over the manifest's agent list express "repeat this, injecting run_id" declaratively, which is what this generation step actually is.

### 5.4 The check that would have caught this specific bug

Even with (1)–(3), a manifest can still drift from what the `.asl` files actually call — so add a build-time structural check, extending a pattern the codebase already uses. `generate_factory_jcm.py` already has `validate_structural()`, which cross-checks `.send(...)` targets against declared agents. Add a sibling pass with the same philosophy:

```python
# Auto-derive the registry instead of hand-maintaining a second list that can itself drift:
# grep every factory/*Artifact.java for @OPERATION method signatures once, per artifact class.
OPERATION_TO_ARTIFACT = scan_artifact_operations("src/main/java/factory/")
# e.g. {"cancelTimer": "timer_artifact", "startTimer": "timer_artifact",
#       "reserveTransport": "amr_artifact", ...}

def validate_focus_bindings(agent, asl_text, jcm_focus_list):
    for call in bare_operation_calls(asl_text):        # calls with no [artifact_name(...)] annotation
        required_artifact = OPERATION_TO_ARTIFACT.get(call)
        if required_artifact and required_artifact not in jcm_focus_list:
            sys.exit(f"{agent}: calls {call}() but is not focused on {required_artifact}")
```

Explicit-annotated calls (e.g. `cancelTransport(...)[artifact_name("amr_artifact"), wsp("factory_ws")]`, which does appear elsewhere in the same file) validate directly against their own annotation and don't need the registry lookup.

This directly matches the project's existing fail-fast philosophy (`validate_asl`, `validate_structural` already `sys.exit` loudly on mismatch) — it's the same technique, applied to one more class of binding that currently has zero verification.

---

## Suggested sequencing

1. **Template drift (§5.2)** — a one-line patch, do it today regardless of everything else.
2. **Memory fix (§3.1)** — the lifecycle-removal change is a one-method edit with no new dependency; ship it same week.
3. **JVM test harness (§2)** — highest long-term leverage given this codebase's concurrency history; start with the liveness/conservation invariants before the seeded-replay parameterization.
4. **AMR collision avoidance (§1)** — the largest single piece of new logic; build it behind the existing `reserveTrajectory` signature so no `.asl` files need to change.
5. **WebSocket auth (§4)** — do this before any non-loopback deployment, not before.
