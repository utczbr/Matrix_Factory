# Document 6: Real-Time Visualization Dashboard Specification

## Amendment Notice

This document extends Documents 1–5 without relaxing any of their constraints. Where a section below amends a prior document, the original section remains authoritative for all other details not mentioned here.

| Amended Section | Amendment Location in This Document |
| :--- | :--- |
| doc1 §2.6 — Visualization Telemetry Pipeline | §3.2 (JVM Payload Assembly), §5 (Backpressure) |
| doc4 §2 — Protobuf Service Definition | §3.1 (Amended `.proto` Definitions) |
| doc3 §4.2 — `TelemetryArtifact` | §5.2 (`lastPublished` Advancement), §5.3 (Consumer Thread) |
| doc5 Phase 1–4 Success Criteria | §7 (Phase Integration Milestones) |

---

## 1. Overview & Architectural Mandate **[Status: Production-Verified (Phase 1 & 2)]**

The real-time dashboard delivers a **top-down, spatially accurate visualization** of the Matrix Fuel Cell Factory, showing the live positions of Autonomous Mobile Robots (AMRs), the discrete operational state of each manufacturing station, and a thermodynamic readout panel for Station 5 and Balance-of-Plant (BoP) systems.

The dashboard is not a passive log viewer. It must render at 60 fps with smooth, physically plausible AMR movement between state updates — achieved entirely through client-side interpolation — while receiving authoritative positional ground truth at only 15–20 Hz from the server.

**Three constraints from existing documents are non-negotiable and are elevated here for clarity:**

1. The visualization layer must **never** initiate a gRPC call, HTTP request, or any other connection to the Python physical daemon (doc4 §1 re-stated and extended, §4 of this document).
2. The `TelemetryArtifact` advances `lastPublishedSimTime` only upon **confirmed WebSocket delivery**, not at queue-offer time (doc3 §4.2, reiterated at §5.2 of this document).
3. The WebSocket consumer thread must use **strictly non-blocking I/O** and drop frames at the network edge if TCP write buffers are full; it must never block waiting for the browser client to drain (doc3 §4.2, reiterated at §5.3 of this document).

---

## 2. Frontend Rendering Architecture **[Status: Production-Verified (Phase 1 & 2)]**

### 2.1 Technology Selection: Two-Layer Canvas Stack

The dashboard UI is structured around two stacked `<canvas>` elements, mounted inside a single `<div id="factory-viewport">`, with identical pixel dimensions and `position: absolute` layering.

| Layer | Index | Technology | Responsibility |
| :--- | :--- | :--- | :--- |
| **Floor layer** | 0 (bottom) | **HTML5 Canvas 2D** | Factory grid cells, station bounding boxes, conveyor path lines, AMR sprites, station state color fills, labels, progress arcs. Redrawn on every `requestAnimationFrame` tick. |
| **Thermal overlay** | 1 (top, `alpha: true`) | **WebGL** (optional) | Per-cell heat map derived from `thermo_state_vector` (stack core/skin temperatures from the H1,1/H0,0 Hermite submodel, see doc2 §4.4). Redrawn only when a new `TelemetryFrame` arrives, not on every rAF tick. |

The WebGL layer is **strictly optional**. Its failure to initialize (e.g., on browsers without WebGL support) must not affect the Canvas 2D floor layer. A `try { initWebGLOverlay() } catch (e) { thermalOverlayEnabled = false; }` guard enforces this. For Phase 1–3 deployments with ≤20 AMRs and 5 stations, the Canvas 2D floor layer alone provides sufficient rendering throughput; the WebGL layer is a Phase 4 enhancement.

**Rendering cost budget (per rAF tick at 60 fps, 8ms frame budget):**
- Grid background (static fill, cached to an offscreen `OffscreenCanvas`): ~0.3 ms
- Station state fills (5 stations, `fillRect` + optional progress arc): ~0.5 ms
- AMR sprites (up to 20, `drawImage` with interpolated sub-pixel positions): ~1.0 ms
- Conveyor path edges (static lines, read from cached offscreen canvas): ~0.1 ms
- KPI text panel (Canvas 2D `fillText`, 8 fields): ~0.4 ms
- **Total: ≤ 2.3 ms** — well within budget.

The Protobuf decode step must **never** occur inside the rAF callback. It executes in `WebSocket.onmessage` and writes pre-decoded data into a `VisualStateBuffer` object. The rAF callback reads from this buffer exclusively.

### 2.2 Static Factory Layout Configuration

The physical geometry of the factory floor — station bounding boxes, conveyor path waypoints, AMR dock/home positions, and no-go zones — is defined in a static `factory_layout.json` file loaded once at dashboard startup.

```jsonc
{
  "grid": { "cols": 20, "rows": 12, "cell_size_px": 48 },
  "stations": [
    { "id": "S1", "label": "MEA Prep",      "cells": [[2,2],[3,3]] },
    { "id": "S2", "label": "Cat. Dep.",     "cells": [[6,2],[7,3]] },
    { "id": "S3", "label": "BP Stamp",      "cells": [[10,2],[11,3]] },
    { "id": "S4", "label": "Stack Asm.",    "cells": [[14,2],[15,3]] },
    { "id": "S5", "label": "Test Bench",    "cells": [[2,7],[5,10]] }
  ],
  "amr_docks": [
    { "id": "AMR-1", "home": [1, 11] },
    { "id": "AMR-2", "home": [2, 11] }
  ],
  "conveyor_paths": [
    [[3,2],[6,2]], [[7,2],[10,2]], [[11,2],[14,2]], [[15,2],[18,2]]
  ]
}
```

This file is **never transmitted over WebSocket** — it encodes invariant physical factory geometry. The dashboard can cache it in `localStorage` after the first load. No server-side RPC is required to fetch it.

### 2.3 Machine State Rendering

Each station's fill color is determined by the `StationStateEnum` received in the latest `TelemetryFrame.station_states` array. Transitions are applied **on the rAF tick that processes the new frame** — no interpolation is applied to discrete machine states; they snap atomically to the new value.

**Color and animation map:**

| `StationStateEnum` | Canvas Fill | Additional Visual Treatment |
| :--- | :--- | :--- |
| `STATION_IDLE` | `#1B5E20` (deep green) | None |
| `STATION_PROVISIONAL_LOCK` | `#F57F17` (amber) | Thin white border pulse, 1 Hz, CSS `@keyframes` on an overlaid `<div>` |
| `STATION_BUSY_PROCESSING` | `#0D47A1` (navy blue) | Arc progress overlay: `strokeArc(cx, cy, r, 0, 2π × processing_progress)` in `#82B1FF` |
| `STATION_DEFECT_DETECTED` | `#B71C1C` (deep red) | Fill flashes between `#B71C1C` and `#FF8A80` at 2 Hz via `Math.sin(performance.now()/250)` |
| `STATION_OFFLINE` | `#424242` (charcoal) | Diagonal hatch pattern via `createPattern()` on a 4×4 offscreen canvas |

When a state transition is **inferred** (detected via a sequence number gap rather than directly observed — see §5.4), the station cell border is drawn in white `(#FFFFFF, lineWidth=2)` for exactly one rAF tick to signal the transition was not directly witnessed.

**Organizational schema indicator:** A HUD label in the top-right corner of the viewport displays `active_org_schema` from the latest frame: `"PROSA"`, `"ADACOR"`, or `"CENTRALIZED"`. When the schema changes, the label animates a brief 400 ms color transition (amber → new color) to draw the operator's eye.

### 2.4 AMR Animation & Client-Side Interpolation

The core rendering challenge is producing visually smooth AMR movement at 60 fps while receiving position updates at only 15–20 Hz. The solution is **predictive extrapolation** using per-AMR motion data embedded in each `TelemetryFrame`.

**Per-AMR payload fields** (defined in §3.2):
- `grid_x`, `grid_y` — Integer cell the AMR occupies at snapshot time.
- `next_grid_x`, `next_grid_y` — Next reserved cell from the 4D spatio-temporal reservation matrix at tick `t+1`.
- `movement_progress` — Float `[0.0, 1.0]` indicating how far the AMR has physically transited between `grid` and `next_grid` at snapshot time.
- `status` — Enum `(IDLE, MOVING, LOADING, UNLOADING, BLOCKED)`.

The browser maintains a `Map<string, VisualAMRState>` keyed on `amr_id`:

```javascript
const VisualAMRState = {
  renderX: 0.0,          // Current interpolated pixel X (cell-centre)
  renderY: 0.0,          // Current interpolated pixel Y
  fromCellX: 0,          // grid_x at last received frame
  fromCellY: 0,          // grid_y at last received frame
  toCellX: 0,            // next_grid_x at last received frame
  toCellY: 0,            // next_grid_y at last received frame
  baseProgress: 0.0,     // movement_progress at last received frame
  receivedAtMs: 0.0,     // performance.now() when last frame arrived
  status: "IDLE",
  carryingOrderId: "",
};
```

**rAF extrapolation (executed every frame):**

```javascript
function interpolateAMR(vs, nowMs, serverFrameIntervalMs) {
  const elapsed = nowMs - vs.receivedAtMs;
  // Advance progress linearly from server-reported base
  const extrapProgress = vs.baseProgress + elapsed / serverFrameIntervalMs;
  const p = Math.min(extrapProgress, 1.0);  // clamp: never overshoot destination

  const CELL = LAYOUT.cell_size_px;
  const toPixel = (cell) => cell * CELL + CELL / 2;

  vs.renderX = toPixel(vs.fromCellX) + p * (toPixel(vs.toCellX) - toPixel(vs.fromCellX));
  vs.renderY = toPixel(vs.fromCellY) + p * (toPixel(vs.toCellY) - toPixel(vs.fromCellY));
}
```

`serverFrameIntervalMs = 1000.0 / TARGET_HZ` (e.g., 66.7 ms at 15 Hz). Clamping `p` at `1.0` prevents sprite overshoot if a frame is late.

**On reception of a new contiguous `TelemetryFrame`:**

```javascript
vs.fromCellX = frame.gridX;   vs.fromCellY = frame.gridY;
vs.toCellX   = frame.nextGridX; vs.toCellY = frame.nextGridY;
vs.baseProgress   = frame.movementProgress;
vs.receivedAtMs   = performance.now();
vs.status         = frame.status;
vs.carryingOrderId = frame.carryingOrderId;
```

**On reception of a frame after a detected sequence number gap** (§5.4), do **not** snap `fromCell` to the new position — that produces a teleport artifact. Instead, rebase:

```javascript
// Back-project current render position into new segment's [0,1] space
const pixFromX = toPixel(frame.gridX), pixFromY = toPixel(frame.gridY);
const pixToX   = toPixel(frame.nextGridX), pixToY = toPixel(frame.nextGridY);
const segLen   = Math.hypot(pixToX - pixFromX, pixToY - pixFromY);
if (segLen > 0) {
  const projX = vs.renderX - pixFromX, projY = vs.renderY - pixFromY;
  vs.baseProgress = Math.max(0, (projX*(pixToX-pixFromX) + projY*(pixToY-pixFromY))
                               / (segLen * segLen));
} else {
  vs.baseProgress = 0.0;
}
vs.fromCellX = frame.gridX;   vs.fromCellY = frame.gridY;
vs.toCellX   = frame.nextGridX; vs.toCellY = frame.nextGridY;
vs.receivedAtMs = performance.now();
```

**Large-gap fast-snap exception:** If the Euclidean cell distance between `vs.fromCellX/Y` and the new `frame.gridX/Y` exceeds 2 cells (indicating the AMR traversed multiple cells during the gap), snap `renderX/Y` immediately to the new cell centre and apply a CSS `transition: transform 120ms ease-out` on the sprite's wrapper element to soften the discontinuity.

### 2.5 requestAnimationFrame Loop Architecture

The rendering loop is explicitly decoupled from WebSocket message processing to preserve 60 fps render cadence regardless of WebSocket event timing:

```
WebSocket.onmessage  → protobuf.decode(buffer)  → VisualStateBuffer.write()
                                                           │
                              ┌────────────────────────────┘ (single JS thread, no lock needed)
                              ▼
rAF callback (60 fps) → VisualStateBuffer.read() → interpolateAll() → ctx.drawImage() × N
```

The JS event loop's single-threaded execution model guarantees `onmessage` and the rAF callback never interleave; no `SharedArrayBuffer` or locking primitive is required.

**Offscreen canvas cache for the static grid:**
The grid background, conveyor path lines, and station border outlines are pre-rendered once into an `OffscreenCanvas` on startup and on any `factory_layout.json` reload. The rAF loop draws this cached image via a single `ctx.drawImage(offscreenCanvas, 0, 0)` call before applying dynamic overlays. This reduces per-frame redraw cost by approximately 80%.

---

## 3. Telemetry Payload Expansion **[Status: Production-Verified (Phase 1 & 2)]**

### 3.1 Amended Protobuf Definitions (`sim_bridge.proto`)

The following additions are **strictly additive** — no existing field numbers are renumbered or removed, preserving wire compatibility with Phase 1 Python daemons that may not yet populate AMR fields.

```protobuf
syntax = "proto3";
package factory;

// ═══════════════════════════════════════════════════════════
// EXISTING DEFINITIONS (unchanged, abbreviated for reference)
// ═══════════════════════════════════════════════════════════

service SimBridge {
  rpc AdvanceTime (TimeStep)        returns (StepReady);
  rpc RunBatchTest (BatchTestRequest) returns (BatchTestResponse);
  rpc HealthCheck (Empty)           returns (HealthStatus);
}

// [TimeStep, StepReady, BatchTestRequest, BatchTestResponse — unchanged]
// See doc4 §2 for existing field definitions.

// ═══════════════════════════════════════════════════════════
// NEW ENUMERATIONS
// ═══════════════════════════════════════════════════════════

enum AMRStatusEnum {
  AMR_IDLE      = 0;
  AMR_MOVING    = 1;
  AMR_LOADING   = 2;
  AMR_UNLOADING = 3;
  AMR_BLOCKED   = 4;  // Grid utilization > 0.85, awaiting clearExpiredReservations()
}

enum StationStateEnum {
  STATION_IDLE             = 0;
  STATION_PROVISIONAL_LOCK = 1;  // CNP provisional_lock(OrderId) asserted
  STATION_BUSY_PROCESSING  = 2;  // execute_physical_operation/RunBatchTest in flight
  STATION_DEFECT_DETECTED  = 3;  // Stochastic defect or Station 5 failure_flags ≠ 0
  STATION_OFFLINE          = 4;  // Component initialization error or ADACOR Phase 1 suspend
}

// ═══════════════════════════════════════════════════════════
// NEW MESSAGES: AMR and STATION STATE SNAPSHOTS
// ═══════════════════════════════════════════════════════════

// Snapshot of a single AMR's spatio-temporal state.
// Coordinates are integer-valued grid cells (float encoding to avoid
// a second int32 packed field; receiver casts to int for cell lookup).
message AMRState {
  string      amr_id            = 1;
  float       grid_x            = 2;  // Current cell X at snapshot time
  float       grid_y            = 3;  // Current cell Y at snapshot time
  float       next_grid_x       = 4;  // Next reserved cell X (4D matrix t+1 slice)
  float       next_grid_y       = 5;  // Next reserved cell Y (4D matrix t+1 slice)
  // movement_progress ∈ [0.0, 1.0]: transit progress from grid→next_grid at snapshot time.
  // 0.0 = just departed grid cell. 1.0 = arrived at next_grid cell.
  float       movement_progress = 6;
  AMRStatusEnum status          = 7;
  string      carrying_order_id = 8;  // Empty string if no order onboard
}

// Snapshot of a single manufacturing station's discrete logical state.
message StationState {
  string         station_id          = 1;
  StationStateEnum state             = 2;
  string         active_order_id     = 3;  // Stable OrderId UUID (empty if IDLE)
  // processing_progress ∈ [0.0, 1.0] only meaningful when state = BUSY_PROCESSING.
  // For Stations 1–4: elapsed_time / expected_proc_time.
  // For Station 5: fraction of polarization curve sweep points completed.
  float          processing_progress = 4;
}

// ═══════════════════════════════════════════════════════════
// TelemetryFrame: WEBSOCKET-ONLY SERIALIZATION MESSAGE
//
// NOT added to the SimBridge service definition.
// Assembled by JVM MainSimulator; transmitted exclusively over the
// WebSocket channel managed by TelemetryArtifact.
// Serialized via TelemetryFrame.toByteArray() in generated Java/Kotlin.
// Deserialized in the browser via protobufjs TelemetryFrame.decode().
// ═══════════════════════════════════════════════════════════

message TelemetryFrame {
  // ── Frame Identity ────────────────────────────────────────
  // Monotonic counter starting at 1. Gap detection: (seqNum - lastSeqNum) > 1
  // indicates dropped frame(s). Never resets within a simulation run.
  uint64 sequence_number             = 1;
  double sim_time_s                  = 2;   // Simulation clock (seconds)
  int32  schema_epoch                = 3;   // Must match AdvanceTime.schema_epoch
  string active_org_schema           = 4;   // "centralized" | "prosa" | "adacor"

  // ── Spatial State ─────────────────────────────────────────
  repeated AMRState     amr_states     = 5;  // One entry per registered AMR
  repeated StationState station_states = 6;  // One entry per station (S1–S5)

  // ── Thermodynamic State Passthrough ───────────────────────
  // Zero-copy passthrough of StepReady.state_vector from Python daemon.
  // Indices defined in ProtoIndex (§3.3). packed=true for binary efficiency.
  repeated double thermo_state_vector  = 7 [packed = true];

  // ── Station 5 Summary Fields ──────────────────────────────
  // Pre-extracted from thermo_state_vector for browser convenience.
  // Eliminates the need for the frontend to know raw array indices.
  double station5_stack_voltage_v       = 8;
  double station5_current_density_a_cm2 = 9;
  double station5_stack_temp_k          = 10;
  double station5_stack_core_temp_k     = 11;  // H1,1/H0,0 Hermite core temperature
  double station5_stack_skin_temp_k     = 12;  // H1,1/H0,0 Hermite skin temperature
  // Bitmask (matches BatchTestResponse.failure_flags, doc4 §2):
  // bit0=OHMIC_DEGRADATION, bit1=MASS_TRANSPORT_STARVATION,
  // bit2=THERMAL_SHUTDOWN, bit3=LOW_ACTIVATION, bit4=SOLVER_DID_NOT_CONVERGE
  uint32 station5_failure_flags         = 13;

  // ── Balance-of-Plant Summary ──────────────────────────────
  double h2_tank_pressure_bar           = 14;
  double h2_tank_fill_fraction          = 15;  // [0.0, 1.0]
  double chiller_temp_k                 = 16;
  double compressor_power_kw            = 17;

  // ── Telemetry Health Metrics (observable counters) ────────
  // droppedTelemetryFrameCount: cumulative since daemon start.
  // Mirrors the existing TelemetryArtifact.droppedTelemetryFrameCount metric.
  uint32 dropped_telemetry_frame_count  = 18;
  // droppedNerCount: forwarded from MainSimulator's NER quorum log (doc1 §2.3).
  uint32 dropped_ner_count              = 19;
  // runId: active Monte Carlo run index (0–29) under Phase 4 1:30 fan-out.
  uint32 run_id                         = 20;
}
```

### 3.2 JVM-Side Payload Assembly

`MainSimulator.onStepReady()` assembles a `TelemetryFrame` immediately after processing each `StepReady` gRPC response. All data sources are **local JVM reads** — no secondary RPCs to the Python daemon are initiated.

**Step 1 — Thermodynamic state (zero-copy):**
`StepReady.state_vector` is forwarded directly into `TelemetryFrame.thermo_state_vector`. The JVM does not deserialize the `repeated double` payload into a `double[]` array and re-serialize it; it copies the raw Protobuf field bytes using `TelemetryFrame.Builder.setThermoStateVectorBytes(stepReady.getStateVectorBytes())`. This preserves the packed encoding and avoids heap allocation of an intermediate `double[]`.

**Step 2 — AMR positions (wait-free volatile read):**
`AMRArtifact` maintains a `volatile AMRSnapshot[] currentPositions` field. At the conclusion of each `step()` invocation (triggered by the synchronization barrier), the artifact writes a freshly computed `AMRSnapshot[]` to this field atomically. `MainSimulator` reads it via `artifact.currentPositions` — a single volatile read, no lock acquisition, O(1) latency.

The `AMRSnapshot` is derived from the 4D Spatio-Temporal Reservation Matrix: for each AMR ID, the artifact reads the (x, y) cell at the current tick `t` and the reserved (x, y) cell at `t+1`. The fractional progress within the current cell is derived from `(sim_time_s - last_departure_time) / cell_transit_duration`. The transit duration is the scheduled time for one cell crossing, derived from the AMR's speed parameter.

> **Implementation constraint:** `AMRArtifact.currentPositions` must be written in a single `volatile` assignment to a fully constructed, immutable `AMRSnapshot[]` — never element-by-element. Element-by-element updates to a non-volatile array produce torn reads; a torn `AMRSnapshot` with stale `next_grid_x` but fresh `grid_x` will cause the frontend to animate an AMR toward the wrong cell.

**Step 3 — Station states (volatile read):**
Each `BaseStationArtifact` maintains a `volatile StationSummary currentSummary` field updated atomically at the end of every `@OPERATION` state transition (`-+station_state(...)` belief update in Jason). `MainSimulator` reads `artifact.currentSummary` for each station artifact via a direct volatile read.

> **Critical constraint:** `MainSimulator` must NOT query CArtAgO's internal belief base to extract station states. The CArtAgO belief-base lock is held during Jason inference cycles; contending on it from `MainSimulator`'s `StepReady` callback path introduces deadlock risk. The `volatile StationSummary` pattern is the only safe extraction mechanism.

**Step 4 — Summary field extraction:**
`MainSimulator` extracts the pre-defined indices from `thermo_state_vector` (defined in `ProtoIndex`, §3.3) and populates the typed summary fields (`station5_stack_voltage_v`, `h2_tank_pressure_bar`, etc.) for browser convenience.

**Step 5 — Immutable snapshot and publish:**
The assembled `TelemetryFrame` (as a byte array) is wrapped in an immutable `TelemetryFrameSnapshot(byte[] payload, double simTimeS)` record and published via `AtomicReference<TelemetryFrameSnapshot>.set()`. This is a wait-free write; it never blocks.

### 3.3 `thermo_state_vector` Index Manifest

A shared constant file must define all indices to prevent silent drift across deployment versions:

```python
# physical_engine/proto_index.py  (Python daemon side)
class ThermoStateIndex:
    H2_TANK_PRESSURE_BAR    = 0
    H2_TANK_FILL_FRACTION   = 1
    CHILLER_TEMP_K          = 2
    COMPRESSOR_POWER_KW     = 3
    STACK_VOLTAGE_V         = 4
    STACK_CURRENT_A_CM2     = 5
    STACK_TEMP_K            = 6
    STACK_CORE_TEMP_K       = 7   # H1,1/H0,0 Hermite submodel (doc2 §4.4)
    STACK_SKIN_TEMP_K       = 8   # H1,1/H0,0 Hermite submodel (doc2 §4.4)
    _VECTOR_LENGTH          = 9
```

```java
// src/java/factory/ProtoIndex.java  (JVM side)
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
    public static final int VECTOR_LENGTH           = 9;
}
```

On startup, `MainSimulator.onStepReady()` executes a one-time validation:

```java
if (firstStep && stepReady.getStateVectorCount() != ProtoIndex.VECTOR_LENGTH) {
    throw new ConfigurationException(
        "thermo_state_vector length mismatch: expected "
        + ProtoIndex.VECTOR_LENGTH + ", got " + stepReady.getStateVectorCount()
        + ". Check proto_index.py / ProtoIndex.java version skew."
    );
}
```

This guard prevents silent index corruption from version skew between the Python daemon and JVM deployments.

---

## 4. Strict Data Flow Constraints **[Status: Production-Verified (Phase 1 & 2)]**

### 4.1 Absolute Prohibition — Visualization Layer Direct RPCs

This constraint is elevated here with expanded scope covering all new dashboard components added by this document.

> **The visualization frontend and the JVM `TelemetryArtifact` are strictly and permanently forbidden from initiating any RPC, HTTP request, WebSocket connection, shared-memory segment, or stdout/pipe read directed at the Python physical daemon.**

This prohibition covers:

- Browser `fetch()` or XHR to any Python daemon port (50051–50080).
- Browser WebSocket to any Python daemon port.
- Any gRPC-Web transcoder or REST proxy fronting the Python daemon, queried by the browser.
- `TelemetryArtifact` opening a secondary gRPC channel for out-of-band state reads.
- Any Java thread reading `h2_tank.py`, `chiller.py`, or any Python component's state via process pipes or file-system polling.
- Any future dashboard extension (heat maps, replay mode, alarm panels) polling the Python daemon directly.

**Rationale:** Direct visualization reads create unsynchronized parallel read-locks on the Python daemon's `_physics_step_lock` (doc4 §4), race against `AdvanceTime` integration steps, and destroy the causal determinism of the synchronization barrier defined in doc1 §2.2. They also violate the Unary Synchronization Barrier invariant: a state read occurring between two `AdvanceTime` calls would capture a physical state that is decoupled from the JVM's internal simulation clock.

### 4.2 Canonical Unidirectional Data Flow Path

Every arrow in this pipeline is unidirectional and downstream-only. No component at any level initiates an upstream request.

```
╔══════════════════════════════════════════════════════════════════════╗
║  Python Physical Daemon                                              ║
║  AdvanceTime handler:                                                ║
║    integrates model by dt                                            ║
║    writes thermo_state_vector (proto_index.py indices)               ║
║    returns StepReady via gRPC                                        ║
╚══════════════════════════╤═══════════════════════════════════════════╝
                           │  gRPC unary response (binary Protobuf)
                           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  JVM — MainSimulator.onStepReady()                                   ║
║    ① AMRArtifact.currentPositions       [volatile read, O(1)]        ║
║    ② BaseStationArtifact[].currentSummary [volatile read, O(1)]      ║
║    ③ thermo summary fields extracted   [ProtoIndex constants]        ║
║    ④ TelemetryFrame.toByteArray()       [Protobuf serialization]     ║
║    ⑤ AtomicReference<Snapshot>.set()   [wait-free publish]           ║
╚══════════════════════════╤═══════════════════════════════════════════╝
                           │  AtomicReference read (wait-free)
                           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  JVM — TelemetryArtifact consumer thread                             ║
║    decimation gate: sim_time_s − lastPublishedSimTime ≥ 1/TARGET_HZ  ║
║    telemetryQueue.offer(snapshot)  [non-blocking; drop on overflow]  ║
║    WebSocket non-blocking binary send                                ║
║    onSuccess → lastPublishedSimTime = frame.sim_time_s               ║
║    onFailure → droppedTelemetryFrameCount++  (drop, never retry)     ║
╚══════════════════════════╤═══════════════════════════════════════════╝
                           │  WebSocket binary frame (TelemetryFrame bytes)
                           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  Browser — WebSocket.onmessage                                       ║
║    TelemetryFrame.decode(buffer)   [protobufjs]                      ║
║    VisualStateBuffer.write(frame)  [no lock, single JS thread]       ║
╚══════════════════════════╤═══════════════════════════════════════════╝
                           │  VisualStateBuffer read (rAF callback)
                           ▼
╔══════════════════════════════════════════════════════════════════════╗
║  Browser — requestAnimationFrame loop (60 fps)                       ║
║    interpolateAMRPositions()                                         ║
║    applyStationStates()                                              ║
║    ctx.drawImage() × N  [Canvas 2D]                                  ║
║    updateKPIPanel()                                                  ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 5. Network Transport & Backpressure **[Status: Production-Verified (Phase 1 & 2)]**

### 5.1 TelemetryArtifact Decimation — Simulation-Time Gate

The decimation gate introduced in doc3 §4.2 applies unchanged to the expanded `TelemetryFrame`. The gate condition is evaluated in simulation time, not wall-clock time:

```java
// Inside TelemetryArtifact consumer loop, invoked after each AtomicReference.get()
double simTimeSinceLast = snapshot.simTimeS - lastPublishedSimTimeS;
double frameIntervalS   = 1.0 / TARGET_HZ;  // TARGET_HZ ∈ [15, 20]

if (simTimeSinceLast >= frameIntervalS) {
    boolean enqueued = telemetryQueue.offer(snapshot);  // Non-blocking
    if (!enqueued) {
        droppedTelemetryFrameCount.incrementAndGet();
    }
    // NOTE: lastPublishedSimTimeS is NOT advanced here.
    // It advances only inside the WebSocket onSuccess callback (§5.3).
}
```

Decimating on simulation time (not wall-clock time) ensures the 15–20 Hz rate is relative to the simulated world's cadence. Under Phase 4 Monte Carlo runs where the simulation may execute faster than real-time, this prevents telemetry flooding the WebSocket with thousands of frames per wall-clock second.

> **Separation of queues:** The `TelemetryArtifact`'s `ArrayBlockingQueue<>` is **independent** of the `DatabaseArtifact`'s `ArrayBlockingQueue<>(300_000)` (doc3 §4.1). The `database_backpressure` signal from `DatabaseArtifact` must NOT throttle the telemetry path. Telemetry and historian share no queue, no executor, and no backpressure signal.

### 5.2 The `lastPublishedSimTime` Advancement Rule (Reiterated)

As originally specified in doc3 §4.2, `lastPublishedSimTimeS` must advance only upon **confirmed WebSocket delivery**:

```java
webSocketSession.sendBinary(ByteBuffer.wrap(frameBytes), new SendHandler() {
    @Override
    public void onResult(SendResult result) {
        if (result.isOK()) {
            // Advance the decimation baseline ONLY on successful delivery
            lastPublishedSimTimeS = snapshot.simTimeS;
        } else {
            // TCP write failed (client backpressure, disconnection, etc.)
            droppedTelemetryFrameCount.incrementAndGet();
            // lastPublishedSimTimeS is NOT advanced — the next eligible frame
            // will be at the same simulation-time slot, not the next one.
        }
    }
});
```

This rule ensures that a frame dropped at the network edge (due to client-side TCP backpressure) is not silently and permanently counted as "sent" for that decimation slot. The same simulation-time slot becomes eligible again for the next assembled snapshot, providing one retry opportunity without queueing.

### 5.3 WebSocket Consumer Thread — Non-Blocking Send Discipline

The WebSocket consumer thread must:

1. Poll `telemetryQueue` with `queue.poll()` — non-blocking.
2. Serialize the polled snapshot: `byte[] bytes = snapshot.payload`.
3. Issue the send via the WebSocket library's **async binary send** API.
4. Register an `onSuccess` / `onFailure` callback (see §5.2).
5. If the underlying TCP write buffer is full (synchronous check fails or async callback fires with failure), drop the frame immediately. **The consumer thread must never call `queue.take()`, `Thread.sleep()`, or any blocking wait on the network path.**

The WebSocket consumer thread and the gRPC `SimBridge` server must not share an executor. A saturated telemetry send path (e.g., slow browser client during a Monte Carlo burst) must not steal threads from the `AdvanceTime` gRPC handler. Both executors must be explicitly sized (see doc4 §4.6 for the bounded executor requirement).

### 5.4 Frontend: Gap Detection & Visual State Coherence

**Gap detection:** The browser tracks `lastReceivedSeqNum`. On each incoming frame:

```javascript
const gap = frame.sequenceNumber - (lastReceivedSeqNum + 1n);
if (gap > 0n) {
  clientDroppedFrameCount += Number(gap);
  HUD.droppedFrames.textContent = clientDroppedFrameCount;
  handleGapRecovery(frame, gap);  // §5.4 recovery logic
}
lastReceivedSeqNum = frame.sequenceNumber;
```

`sequenceNumber` is a `uint64`; use `BigInt` arithmetic in JavaScript to avoid 53-bit integer precision loss.

The dashboard also cross-validates `clientDroppedFrameCount` against `frame.dropped_telemetry_frame_count` (server-side counter). A persistent divergence between the two indicates frames being dropped before the WebSocket boundary (inside `TelemetryArtifact`) rather than at the TCP edge.

**Per-entity gap recovery strategy:**

| Entity Type | On Contiguous Frame | On Gap-Recovery Frame |
| :--- | :--- | :--- |
| AMR positions | Update `fromCell`, `toCell`, `baseProgress`, `receivedAt` | Rebase from current `renderX/Y` into new segment (§2.4). If displacement > 2 cells: fast-snap + 120ms CSS ease-out. |
| Station states | Snap immediately | Snap immediately; draw one-tick white border to signal inferred transition. |
| Thermodynamic KPIs | Apply new values | Apply new values; prefix display with `~` until next contiguous frame confirms them. |
| Failure flags | Render new bitmask | Render new bitmask; log inferred flag transitions to browser console. |

### 5.5 Sustained Telemetry Interruption (> 500 ms Wall-Clock Gap)

If no `TelemetryFrame` arrives within 500 ms wall-clock time:

1. **Freeze AMR extrapolation.** Set `vs.baseProgress = Math.min(vs.baseProgress, 1.0)` and stop advancing it. Extrapolating beyond one full server frame interval produces physically implausible positions.
2. **Overlay the interruption banner.** A semi-transparent `#212121` rectangle with centered white text `TELEMETRY INTERRUPTED` is drawn above the floor layer at 70% opacity.
3. **Dim the floor canvas.** Apply `ctx.globalAlpha = 0.4` to the factory floor canvas.
4. **Blank all KPI readouts.** Replace all numeric fields in the thermodynamic panel with `---` (grey foreground `#9E9E9E`).
5. **On resumption** (next frame received): remove the banner immediately, restore `globalAlpha = 1.0`, snap all entities to the received frame state, and accept the resulting visual discontinuity — when the gap is large enough to trigger the 500 ms freeze, linear extrapolation is no longer meaningful, and accuracy takes precedence over smoothness.

The 500 ms threshold deliberately exceeds three missed frames at 15 Hz (~200 ms), avoiding false positives from brief TCP jitter. The threshold must be configurable via `dashboard_config.json` alongside `TARGET_HZ`.

---

## 6. Dashboard WebSocket Endpoint Security **[Status: Planned / Proposed (Phase 4)]**

The WebSocket endpoint serving `TelemetryFrame` binary frames must be hardened before any production or Phase 4 deployment:

**Binding:** The endpoint must bind to `127.0.0.1` or an isolated internal network interface only. Public-facing exposure requires `wss://` (TLS) and token-based authentication (e.g., a short-lived JWT issued at dashboard load time by the JVM's HTTP server).

**Connection limit:** Enforce one concurrent WebSocket connection per dashboard session. A second connection attempt must close the first with WebSocket close code `4001 "SUPERSEDED"`. Under Phase 4's 1:30 fan-out, a HUD dropdown allows the operator to switch the monitored `run_id`; this triggers a graceful reconnect, not a second simultaneous connection.

**Inbound frame rejection:** The WebSocket channel is **publish-only**. Any binary or text frame received from the browser must be discarded and the connection closed with code `1003 "UNSUPPORTED_DATA"`. The browser must not be able to trigger state mutations via the WebSocket connection.

**Executor isolation:** The WebSocket server thread must not share an executor with the gRPC `SimBridge` server (doc4 §4.6). A saturated telemetry send must not reduce throughput for `AdvanceTime` responses.

---

## 7. Phase Integration & Verification Milestones

### Phase 2 (Core MAS Integration) Addenda **[Status: Production-Verified (Phase 1 & 2)]**

- `TelemetryArtifact` successfully transmits binary Protobuf `TelemetryFrame` over WebSocket with AMR and station state fields populated. Verified by inspecting binary WebSocket frames in browser DevTools → Network → WS → Binary.
- `AMRArtifact.currentPositions` volatile field is written atomically on every synchronization barrier tick and read without lock acquisition in `MainSimulator`.
- `BaseStationArtifact.currentSummary` volatile field correctly reflects the Jason belief-base state (`station_state/1`) within one CArtAgO operation cycle.
- `TelemetryFrame.sequence_number` increments monotonically with no duplicates across all transmitted frames; verified by logging `frame.sequenceNumber` in the browser console for 60 seconds of simulation.
- Canvas 2D floor layer sustains 60 fps (measured via `PerformanceObserver` with `type: "frame"` entry type). Per-rAF render time ≤ 2.5 ms.
- `ProtoIndex.VECTOR_LENGTH` startup validation fires correctly when a deliberately mismatched Python daemon is connected (regression test).
- `lastPublishedSimTimeS` advances only on WebSocket send confirmation; verified by injecting artificial TCP send failures and confirming the next eligible frame is offered at the same simulation-time slot rather than the following one.

### Phase 3 (Organizational Flexibility) Addenda **[Status: Production-Verified (Phase 3)]**

- `active_org_schema` field in `TelemetryFrame` transitions correctly between `"prosa"` and `"adacor"` during ADACOR schema switches. The HUD organizational schema label updates within one decimation interval.
- `schema_epoch` in `TelemetryFrame` matches the epoch in `AdvanceTime` responses throughout Phase 1 and Phase 2 of the two-phase commit (doc3 §3.1). The browser logs a warning if these ever diverge.
- During ADACOR Phase 1 (`suspend_intentions` broadcast), the `TelemetryArtifact` queue does not cross 300,000 records (the `DatabaseArtifact` ceiling) because both queues are independent. `database_backpressure` signals do not affect telemetry throughput.
- The browser correctly enters the 500 ms interruption state during a deliberately injected ADACOR Phase 1 pause that exceeds 500 ms wall-clock time; resumes cleanly when telemetry restores.

### Phase 4 (Monte Carlo Scale) Addenda **[Status: Planned / Proposed (Phase 4)]**

- `run_id` field in `TelemetryFrame` correctly identifies the active run (0–29) under 1:30 fan-out. The HUD run selector dropdown switches the monitored daemon without requiring a JVM restart.
- Under 30-daemon concurrent execution, `TelemetryArtifact` consumer thread CPU usage does not exceed `threads / 30` of a single core (i.e., the telemetry path does not inflate overall CPU footprint).
- The optional WebGL thermal overlay does not degrade Canvas 2D render latency. Measured by `performance.mark()` bracketing the WebGL `drawElements()` call: if WebGL frame time exceeds 4 ms on the monitoring machine, the overlay disables itself automatically and logs `[Dashboard] WebGL overlay disabled: budget exceeded`.
- `clientDroppedFrameCount` and `frame.dropped_telemetry_frame_count` are compared at simulation end for each Monte Carlo run and logged. A divergence > 0.5% between the two counters triggers a post-run diagnostic alert.

---

## 8. Key Design Decisions Rationale **[Status: Production-Verified (Phase 1 & 2)]**

**Why HTML5 Canvas 2D, not a DOM-based UI (React/Vue)?**
DOM diffing for 20+ moving sprites at 60 fps produces excessive layout reflows and style recalculations. Canvas 2D provides deterministic sub-millisecond per-frame render control with no layout engine involvement. The static station labels and KPI readout panel can be DOM elements because they do not need to move or redraw at 60 fps.

**Why client-side interpolation rather than server-side prediction?**
The server already holds the authoritative positional state via the 4D reservation matrix. Transmitting `next_grid_x/y` and `movement_progress` costs 12 bytes per AMR per frame and eliminates all client-side velocity estimation. The client does not need a Kalman filter or dead-reckoning model; it simply interpolates along the server-specified path segment.

**Why `TelemetryFrame` is not a `SimBridge` RPC message?**
The `SimBridge` service is a synchronous request-response pattern between the JVM and Python daemon. `TelemetryFrame` is a downstream push from the JVM to the browser; it has no Python involvement and must not introduce any coupling between the WebSocket pipeline and the `_physics_step_lock` on the Python side. Separating the message definitions enforces this structural decoupling at the schema level.

**Why simulation-time decimation rather than wall-clock decimation?**
Wall-clock-based decimation interacts unpredictably with Monte Carlo runs executing faster than real time. Simulation-time decimation guarantees that exactly `TARGET_HZ` simulation-seconds' worth of frames are published per simulated second, regardless of how quickly the JVM and Python daemon execute the physical model.
