// visualization/dashboard.js
//
// NOTE ON AMR VISIBILITY: if AMRs still don't appear after deploying this
// file, the cause is server-side, not here — see AMRArtifact.java's
// updatePositions(), which previously never populated currentPositions,
// so amr_states was always empty on the wire. That fix must be deployed
// alongside this file.

let layout = null;
let TelemetryFrame = null;
const CLIENT_TOKEN = crypto.randomUUID();
const DEFAULT_RUN_COUNT = 30;

// ---- Canvas layers -------------------------------------------------------
const stage = document.getElementById('stage');
const gridCanvas = document.getElementById('gridCanvas');     // static: grid, no-go zones, docks, conveyors
const thermalCanvas = document.getElementById('thermalCanvas'); // dynamic-but-sparse: station5 heat glow (only real thermal data we have)
const sceneCanvas = document.getElementById('sceneCanvas');   // dynamic: stations, AMRs, animations
const gridCtx = gridCanvas.getContext('2d');
const thermalCtx = thermalCanvas.getContext('2d');
const sceneCtx = sceneCanvas.getContext('2d');

const runSelect = document.getElementById('runSelect');
const orgSchemaPill = document.getElementById('orgSchemaPill');
const stationTabsEl = document.getElementById('stationTabs');
const stationBodyEl = document.getElementById('stationBody');
const amrListEl = document.getElementById('amrList');

let CELL = 48; // nominal grid cell size in drawing units (not CSS px — see resizeCanvases)
let COLS = 20, ROWS = 12;

let lastAMRPositions = {};   // amrId -> {x,y,nextX,nextY,progress}
let currentAMRPositions = {};
let lastFrameWallTime = 0;   // performance.now() at which the *previous* frame arrived
let currentFrameWallTime = 0;
let estFrameIntervalMs = 66; // ~15 Hz telemetry default, refined from real arrivals
let activeWebSocket = null;
let currentRunId = 0;
let connectionEpoch = 0;
let lastSequenceNumber = null;
let missedFrameFlashUntil = 0;
let lastOrgSchema = null;
let orgSchemaFlashTimer = null;
let latestFrame = null;
let selectedStationId = null;

function field(obj, camel, snake) {
    return obj[camel] !== undefined ? obj[camel] : obj[snake];
}

let frozenTestCurrent = null;
let frozenTestVoltage = null;

const STATION_STATE_NAMES = ["IDLE", "PROVISIONAL_LOCK", "BUSY_PROCESSING", "DEFECT_DETECTED", "OFFLINE"];
const STATE = { IDLE: 0, PROVISIONAL_LOCK: 1, BUSY_PROCESSING: 2, DEFECT_DETECTED: 3, OFFLINE: 4 };

// Colors as specified: Amber / bright-blue+arc / Deep-red<->light-red flash / Charcoal hatch
const STATION_STATE_COLORS = {
    0: "#2ecc71",  // IDLE - green
    1: "#e8a521",  // PROVISIONAL_LOCK - amber
    2: "#2563eb",  // BUSY_PROCESSING - bright royal blue (was navy #1b2a4a, which was
                   // nearly indistinguishable from the page's near-black background —
                   // that's why it looked like "stations never go busy": the state WAS
                   // firing, the color just didn't read against the dark UI)
    3: "#B71C1C",  // DEFECT_DETECTED - deep red (base; flashes toward #FF8A80)
    4: "#333333",  // OFFLINE - charcoal
};
const BUSY_ARC_COLOR = "#9fd3ff";      // light blue progress arc
const DEFECT_FLASH_COLOR = "#FF8A80";  // light red flash peak

const FAILURE_FLAG_NAMES = [
    [0x01, "OHMIC_DEGRADATION"],
    [0x02, "MASS_TRANSPORT_STARVATION"],
    [0x04, "THERMAL_SHUTDOWN"],
    [0x08, "LOW_ACTIVATION"],
    [0x10, "SOLVER_DID_NOT_CONVERGE"],
];

function decodeFailureFlags(flags) {
    if (!flags) return [];
    return FAILURE_FLAG_NAMES.filter(([bit]) => (flags & bit) !== 0).map(([, name]) => name);
}

function stationStateNumber(s) {
    const raw = field(s, "state", "state");
    if (typeof raw === "number") return raw;
    const idx = STATION_STATE_NAMES.indexOf(String(raw).replace("STATION_", ""));
    return idx >= 0 ? idx : 0;
}

// ---- SVG icon loading ------------------------------------------------------
// Icons are inlined SVGs rasterized once into <img> bitmaps and cached, so
// per-frame rendering is a cheap drawImage() rather than a Path2D replay.
const ICON_SVGS = {
    chip: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect x="14" y="14" width="20" height="20" rx="2" fill="none" stroke="white" stroke-width="2.5"/><rect x="19" y="19" width="10" height="10" fill="white" opacity="0.85"/>
      <g stroke="white" stroke-width="2.5"><line x1="14" y1="20" x2="8" y2="20"/><line x1="14" y1="28" x2="8" y2="28"/><line x1="34" y1="20" x2="40" y2="20"/><line x1="34" y1="28" x2="40" y2="28"/><line x1="20" y1="14" x2="20" y2="8"/><line x1="28" y1="14" x2="28" y2="8"/><line x1="20" y1="34" x2="20" y2="40"/><line x1="28" y1="34" x2="28" y2="40"/></g></svg>`,
    flask: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><path d="M19 8h10v10l9 18a3 3 0 0 1-3 4H13a3 3 0 0 1-3-4l9-18Z" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"/><line x1="17" y1="8" x2="31" y2="8" stroke="white" stroke-width="2.5"/><path d="M15 30h18" stroke="white" stroke-width="2" opacity="0.8"/></svg>`,
    stamp: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect x="10" y="34" width="28" height="6" rx="1" fill="white" opacity="0.85"/><path d="M16 34l2-12h12l2 12Z" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"/><rect x="20" y="8" width="8" height="14" rx="1.5" fill="none" stroke="white" stroke-width="2.5"/></svg>`,
    layers: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><path d="M24 8 6 18l18 10 18-10Z" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"/><path d="M6 26l18 10 18-10" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"/><path d="M6 34l18 10 18-10" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round" opacity="0.6"/></svg>`,
    gauge: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><path d="M8 30a16 16 0 1 1 32 0" fill="none" stroke="white" stroke-width="2.5"/><line x1="24" y1="30" x2="32" y2="20" stroke="white" stroke-width="2.5" stroke-linecap="round"/><circle cx="24" cy="30" r="2.5" fill="white"/></svg>`,
    amr: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
      <ellipse cx="24" cy="26" rx="17" ry="3.5" fill="black" opacity="0.25"/>
      <rect x="9" y="14" width="9" height="20" rx="3" fill="#dfe4ea"/>
      <rect x="30" y="14" width="9" height="20" rx="3" fill="#dfe4ea"/>
      <rect x="10" y="12" width="28" height="18" rx="5" fill="#f4f6f8" stroke="#8a94a3" stroke-width="1.5"/>
      <path d="M31 15 L40 21 L31 27 Z" fill="#2563eb"/>
      <circle cx="16" cy="21" r="2.6" fill="#2563eb"/>
      <rect x="14" y="26" width="18" height="2.4" rx="1.2" fill="#8a94a3"/>
      <rect x="14" y="30" width="12" height="2" rx="1" fill="#c3cad3"/>
    </svg>`,
};
const iconCache = {};

function loadIcon(name) {
    return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => { iconCache[name] = img; resolve(img); };
        img.onerror = () => resolve(null);
        img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(ICON_SVGS[name]);
    });
}

// ---- Boot -------------------------------------------------------------
async function init() {
    const res = await fetch('factory_layout.json');
    layout = await res.json();
    console.log("Loaded layout:", layout.layout_version);

    COLS = layout.grid.cols;
    ROWS = layout.grid.rows;
    CELL = layout.grid.cell_size_px;
    stage.style.setProperty('--grid-aspect', `${COLS} / ${ROWS}`);

    await Promise.all(Object.keys(ICON_SVGS).map(loadIcon));

    try {
        const root = await protobuf.load("../src/main/proto/sim_bridge.proto");
        TelemetryFrame = root.lookupType("factory.TelemetryFrame");
    } catch (e) {
        console.warn("Could not load .proto, using a mock decode", e);
        TelemetryFrame = {
            decode: () => ({ simTimeS: 0, stationStates: [], amrStates: [], droppedTelemetryFrameCount: 0 })
        };
    }

    resizeCanvases();
    new ResizeObserver(resizeCanvases).observe(stage);

    drawStaticGrid();
    buildStationTabs();

    populateRunSelector();
    const initialRunId = Number(new URLSearchParams(window.location.search).get('run_id') || '0');
    currentRunId = Number.isFinite(initialRunId) ? initialRunId : 0;
    runSelect.value = String(currentRunId);
    runSelect.addEventListener('change', () => switchRun(Number(runSelect.value)));

    connect(currentRunId);
    requestAnimationFrame(renderLoop);
}

function populateRunSelector() {
    runSelect.innerHTML = '';
    for (let i = 0; i < DEFAULT_RUN_COUNT; i++) {
        const option = document.createElement('option');
        option.value = String(i);
        option.textContent = `Run ${i}`;
        runSelect.appendChild(option);
    }
}

// ---- Responsive scaling -------------------------------------------------
// Internal drawing-buffer resolution is fixed at COLS*CELL x ROWS*CELL,
// scaled by devicePixelRatio for crispness. The CSS layer (#stage, with
// aspect-ratio set from the layout's cols/rows) does all the "fit the
// screen" work — from phone width up to ultrawide monitors — without ever
// distorting grid geometry, because every draw call below always works in
// fixed nominal grid units.
function resizeCanvases() {
    const dpr = window.devicePixelRatio || 1;
    const bufW = COLS * CELL;
    const bufH = ROWS * CELL;
    for (const c of [gridCanvas, thermalCanvas, sceneCanvas]) {
        c.width = bufW * dpr;
        c.height = bufH * dpr;
        c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    drawStaticGrid();
}

function px(cell) { return cell * CELL; }

// ---- Static layer: grid lines, no-go zones, docks, conveyors ------------
function drawStaticGrid() {
    if (!layout) return;
    gridCtx.clearRect(0, 0, COLS * CELL, ROWS * CELL);
    gridCtx.fillStyle = "#101216";
    gridCtx.fillRect(0, 0, COLS * CELL, ROWS * CELL);

    gridCtx.strokeStyle = "#242830";
    gridCtx.lineWidth = 1;
    for (let x = 0; x <= COLS; x++) {
        gridCtx.beginPath(); gridCtx.moveTo(px(x) + 0.5, 0); gridCtx.lineTo(px(x) + 0.5, px(ROWS)); gridCtx.stroke();
    }
    for (let y = 0; y <= ROWS; y++) {
        gridCtx.beginPath(); gridCtx.moveTo(0, px(y) + 0.5); gridCtx.lineTo(px(COLS), px(y) + 0.5); gridCtx.stroke();
    }

    for (const zone of layout.no_go_zones || []) {
        const [[x0, y0], [x1, y1]] = zone;
        gridCtx.fillStyle = "rgba(183,28,28,0.12)";
        gridCtx.fillRect(px(Math.min(x0, x1)), px(Math.min(y0, y1)),
            px(Math.abs(x1 - x0) + 1), px(Math.abs(y1 - y0) + 1));
    }

    gridCtx.strokeStyle = "#3a4048";
    gridCtx.lineWidth = 3;
    gridCtx.setLineDash([6, 4]);
    for (const path of layout.conveyor_paths || []) {
        const [[x0, y0], [x1, y1]] = path;
        gridCtx.beginPath();
        gridCtx.moveTo(px(x0) + CELL / 2, px(y0) + CELL / 2);
        gridCtx.lineTo(px(x1) + CELL / 2, px(y1) + CELL / 2);
        gridCtx.stroke();
    }
    gridCtx.setLineDash([]);

    for (const dock of layout.amr_docks || []) {
        const [dx, dy] = dock.home;
        gridCtx.strokeStyle = "#3498db";
        gridCtx.lineWidth = 2;
        gridCtx.strokeRect(px(dx) + 4, px(dy) + 4, CELL - 8, CELL - 8);
        gridCtx.fillStyle = "#7ec8ff";
        gridCtx.font = "10px sans-serif";
        gridCtx.fillText(dock.id, px(dx) + 6, px(dy) + CELL - 6);
    }
}

// ---- Station tabs / detail panel -----------------------------------------
function buildStationTabs() {
    stationTabsEl.innerHTML = '';
    for (const st of layout.stations) {
        const btn = document.createElement('button');
        btn.textContent = `${st.id} · ${st.label}`;
        btn.dataset.stationId = st.id;
        btn.addEventListener('click', () => { selectedStationId = st.id; renderStationPanel(); });
        stationTabsEl.appendChild(btn);
    }
    selectedStationId = layout.stations[0].id;
    renderStationPanel();
}

function stationCellBounds(st) {
    const [[x0, y0], [x1, y1]] = st.cells;
    return { x0: Math.min(x0, x1), y0: Math.min(y0, y1), x1: Math.max(x0, x1), y1: Math.max(y0, y1) };
}

// ---- WebSocket telemetry ---------------------------------------------
function telemetryUrl(runId, ticket) {
    let url = `ws://127.0.0.1:8080/telemetry?run_id=${runId}&client=${CLIENT_TOKEN}`;
    if (ticket) {
        url += `&ticket=${ticket}`;
    }
    return url;
}

async function connect(runId) {
    if (activeWebSocket) {
        const previousSocket = activeWebSocket;
        activeWebSocket = null;
        previousSocket.close(1000, 'run switch');
    }

    const myEpoch = ++connectionEpoch;
    setConnectionStatus('connecting');

    let ticket = null;
    try {
        const response = await fetch(`http://127.0.0.1:8081/telemetry/ticket?run_id=${runId}&client=${CLIENT_TOKEN}`);
        if (response.ok) {
            const data = await response.json();
            ticket = data.ticket;
            console.log('[telemetry] obtained auth ticket');
        } else {
            console.warn('[telemetry] ticket fetch failed', response.status, response.statusText);
        }
    } catch (e) {
        console.warn('[telemetry] could not fetch auth ticket (is ticket server running?)', e);
    }

    if (myEpoch !== connectionEpoch) return; // connection superseded

    const url = telemetryUrl(runId, ticket);
    console.log(`[telemetry] connecting to ${url}`);
    const ws = new WebSocket(url);
    activeWebSocket = ws;
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
        console.log(`[telemetry] connected (run_id=${runId})`);
        setConnectionStatus('connected');
    };

    ws.onerror = (err) => {
        console.error('[telemetry] socket error — is the Java MAS running and listening on :8080?', err);
        setConnectionStatus('error');
    };

    ws.onmessage = (event) => {
        let frame;
        try {
            frame = TelemetryFrame.decode(new Uint8Array(event.data));
        } catch (e) {
            console.error("Decode error", e);
            return;
        }

        try {
            const now = performance.now();
            if (currentFrameWallTime) {
                const interval = now - currentFrameWallTime;
                if (interval > 5 && interval < 2000) {
                    estFrameIntervalMs = estFrameIntervalMs * 0.8 + interval * 0.2; // smoothed
                }
            }
            lastFrameWallTime = currentFrameWallTime;
            currentFrameWallTime = now;

            const seq = Number(field(frame, "sequenceNumber", "sequence_number") || 0);
            if (lastSequenceNumber !== null && seq > lastSequenceNumber + 1) {
                missedFrameFlashUntil = now + 180; // brief, visible flash (vs. a literal single rAF frame)
            }
            lastSequenceNumber = seq;

            lastAMRPositions = currentAMRPositions;
            currentAMRPositions = {};
            const amrStates = field(frame, "amrStates", "amr_states") || [];
            for (const amr of amrStates) {
                const amrId = field(amr, "amrId", "amr_id");
                currentAMRPositions[amrId] = {
                    x: field(amr, "gridX", "grid_x"),
                    y: field(amr, "gridY", "grid_y"),
                    nextX: field(amr, "nextGridX", "next_grid_x"),
                    nextY: field(amr, "nextGridY", "next_grid_y"),
                    progress: field(amr, "movementProgress", "movement_progress") || 0,
                    status: field(amr, "status", "status"),
                    carryingOrderId: field(amr, "carryingOrderId", "carrying_order_id"),
                };
                if (!(amrId in lastAMRPositions)) lastAMRPositions[amrId] = currentAMRPositions[amrId];
            }

            const orgSchema = field(frame, "activeOrgSchema", "active_org_schema");
            if (orgSchema && orgSchema !== lastOrgSchema) {
                lastOrgSchema = orgSchema;
                orgSchemaPill.textContent = `SCHEMA: ${orgSchema}`;
                orgSchemaPill.classList.add('flash');
                clearTimeout(orgSchemaFlashTimer);
                orgSchemaFlashTimer = setTimeout(() => orgSchemaPill.classList.remove('flash'), 400);
            }

            latestFrame = frame;
            renderStationPanel();
            renderAMRList();
            updateDroppedFrameHud(field(frame, "droppedTelemetryFrameCount", "dropped_telemetry_frame_count"),
                field(frame, "simTimeS", "sim_time_s"));
        } catch (err) {
            console.error("Frame processing error", err);
        }
    };

    ws.onclose = (event) => {
        if (connectionEpoch !== myEpoch) return;
        if (activeWebSocket === ws) activeWebSocket = null;
        console.warn(`[telemetry] connection closed (code ${event.code}, reason "${event.reason}") — reconnecting in 2s`);
        setConnectionStatus('disconnected');
        setTimeout(() => connect(currentRunId), 2000);
    };
}

// Surfaces connection state next to the org-schema pill so "no data" is
// visibly distinguishable from "connected but the sim hasn't ticked yet".
function setConnectionStatus(status) {
    const el = document.getElementById('wsStatus');
    if (!el) return;
    const labels = {
        connecting: ['CONNECTING…', '#f1c40f'],
        connected: ['LIVE', '#2ecc71'],
        error: ['SOCKET ERROR', '#e74c3c'],
        disconnected: ['DISCONNECTED', '#7f8c8d'],
    };
    const [text, color] = labels[status] || ['—', '#7f8c8d'];
    el.textContent = text;
    el.style.color = color;
}

function switchRun(runId) {
    currentRunId = runId;
    runSelect.value = String(runId);
    connect(runId);
}

// ---- Per-frame scene rendering ------------------------------------------
function renderLoop(now) {
    sceneCtx.clearRect(0, 0, COLS * CELL, ROWS * CELL);
    thermalCtx.clearRect(0, 0, COLS * CELL, ROWS * CELL);

    if (layout && latestFrame) {
        drawStations(now);
        drawThermalGlow(now);
        drawAMRs(now);
    }
    requestAnimationFrame(renderLoop);
}

function stationStateFor(stationId) {
    const states = field(latestFrame, "stationStates", "station_states") || [];
    const mapped = stationId; // layout ids already "S1".."S5", matches wire format
    return states.find(x => field(x, "stationId", "station_id") === mapped);
}

function drawStations(now) {
    const missedFlash = now < missedFrameFlashUntil;

    for (const st of layout.stations) {
        const b = stationCellBounds(st);
        const x = px(b.x0), y = px(b.y0);
        const w = px(b.x1 - b.x0 + 1), h = px(b.y1 - b.y0 + 1);
        const s = stationStateFor(st.id);
        const stateNum = s ? stationStateNumber(s) : STATE.IDLE;
        const progress = s ? (field(s, "processingProgress", "processing_progress") || 0) : 0;

        // Base fill
        let fill = STATION_STATE_COLORS[stateNum] || "#555";
        if (stateNum === STATE.DEFECT_DETECTED) {
            const t = (Math.sin(now / (1000 / (2 * Math.PI * 2))) + 1) / 2; // 2 Hz
            fill = lerpColor(STATION_STATE_COLORS[3], DEFECT_FLASH_COLOR, t);
        }
        sceneCtx.fillStyle = fill;
        roundRect(sceneCtx, x, y, w, h, 6);
        sceneCtx.fill();

        // OFFLINE: diagonal hatch overlay
        if (stateNum === STATE.OFFLINE) {
            sceneCtx.save();
            roundRect(sceneCtx, x, y, w, h, 6);
            sceneCtx.clip();
            sceneCtx.strokeStyle = "rgba(255,255,255,0.15)";
            sceneCtx.lineWidth = 2;
            for (let i = -h; i < w; i += 8) {
                sceneCtx.beginPath();
                sceneCtx.moveTo(x + i, y + h);
                sceneCtx.lineTo(x + i + h, y);
                sceneCtx.stroke();
            }
            sceneCtx.restore();
        }

        // BUSY_PROCESSING: glowing light-blue progress arc + pulsing halo,
        // so an active station is unmistakable rather than blending into
        // the background (the old navy fill was the actual bug here).
        if (stateNum === STATE.BUSY_PROCESSING) {
            const cx = x + w / 2, cy = y + h / 2;
            const r = Math.min(w, h) / 2 - 4;
            const pulse = (Math.sin(now / 220) + 1) / 2; // gentle ~1.4Hz breathing halo

            sceneCtx.save();
            sceneCtx.shadowColor = BUSY_ARC_COLOR;
            sceneCtx.shadowBlur = 10 + pulse * 10;

            sceneCtx.strokeStyle = "rgba(255,255,255,0.18)";
            sceneCtx.lineWidth = 5;
            sceneCtx.beginPath(); sceneCtx.arc(cx, cy, r, 0, Math.PI * 2); sceneCtx.stroke();

            sceneCtx.strokeStyle = BUSY_ARC_COLOR;
            sceneCtx.lineWidth = 5;
            sceneCtx.lineCap = "round";
            sceneCtx.beginPath();
            sceneCtx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2);
            sceneCtx.stroke();
            sceneCtx.restore();
        }

        // PROVISIONAL_LOCK: 1 Hz thin white border pulse
        if (stateNum === STATE.PROVISIONAL_LOCK) {
            const t = (Math.sin(now / (1000 / (2 * Math.PI))) + 1) / 2; // 1 Hz
            sceneCtx.strokeStyle = `rgba(255,255,255,${0.25 + t * 0.6})`;
            sceneCtx.lineWidth = 2;
            roundRect(sceneCtx, x + 1, y + 1, w - 2, h - 2, 6);
            sceneCtx.stroke();
        }

        // Missed-frame indicator: white border flash across all stations
        if (missedFlash) {
            sceneCtx.strokeStyle = "#ffffff";
            sceneCtx.lineWidth = 3;
            roundRect(sceneCtx, x + 1, y + 1, w - 2, h - 2, 6);
            sceneCtx.stroke();
        }

        // Icon
        const icon = iconCache[st.icon];
        if (icon) {
            const iconSize = Math.min(w, h) * 0.5;
            sceneCtx.drawImage(icon, x + w / 2 - iconSize / 2, y + h / 2 - iconSize / 2 - 6, iconSize, iconSize);
        }

        // Label
        sceneCtx.fillStyle = "#fff";
        sceneCtx.font = "600 11px sans-serif";
        sceneCtx.textAlign = "center";
        sceneCtx.fillText(`${st.id} · ${st.label}`, x + w / 2, y + h - 8);
        sceneCtx.textAlign = "left";

        if (st.id === selectedStationId) {
            sceneCtx.strokeStyle = "#f1c40f";
            sceneCtx.lineWidth = 2;
            roundRect(sceneCtx, x - 3, y - 3, w + 6, h + 6, 8);
            sceneCtx.stroke();
        }
    }
}

// Real thermal data is only available for Station 5's stack (core/skin
// temp) — the physics engine does not model a per-cell floor-wide thermal
// field, so a true grid heatmap (Phase-4 WebGL goal) would currently have
// to invent numbers for every other cell. Instead this draws an honest,
// data-backed heat glow scoped to Station 5 only. See docs/phases_archive
// /Phase4.md and ProtoIndex.java (thermo_state_vector is a fixed 9-slot
// utility/stack vector, not a spatial field) — extending the backend to
// publish a real per-cell vector is a prerequisite for the full overlay.
function drawThermalGlow(now) {
    const s5 = layout.stations.find(s => s.id === "S5");
    if (!s5) return;
    const core = field(latestFrame, "station5StackCoreTempK", "station5_stack_core_temp_k");
    if (core === undefined) return;
    const b = stationCellBounds(s5);
    const cx = px(b.x0) + px(b.x1 - b.x0 + 1) / 2;
    const cy = px(b.y0) + px(b.y1 - b.y0 + 1) / 2;
    const heat = Math.max(0, Math.min(1, (core - 320) / (380 - 320))); // 320-380K mapped to 0-1
    const r = CELL * 3;
    const grad = thermalCtx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, `rgba(255,${Math.round(160 - heat * 120)},60,${0.35 * heat})`);
    grad.addColorStop(1, "rgba(255,80,0,0)");
    thermalCtx.fillStyle = grad;
    thermalCtx.beginPath();
    thermalCtx.arc(cx, cy, r, 0, Math.PI * 2);
    thermalCtx.fill();
}

// Predictive AMR rendering.
//
// BUG THIS FIXES (teleport/flicker on every cell crossing): the previous
// version blended `prev.progress` -> `curr.progress` directly. But the
// server only updates (x,y) and (nextX,nextY) once per grid edge — mid-edge
// frames repeat the same edge with progress climbing 0->1, and the frame
// where it *crosses* 1.0 snaps x/y to the new cell and resets progress to
// ~0 while nextX/nextY jumps to a *new* target. Blending "0.95 on edge A"
// toward "0.05 on edge B" is meaningless — they're progress values along
// two different line segments — so every single cell crossing produced a
// brief but visible jump.
//
// Fix: convert each sample to an absolute (x,y) position first (still valid
// even across an edge change, since it's just "where the AMR physically
// is"), then interpolate/extrapolate in absolute space using wall-clock
// time against the measured telemetry interval.
function absPos(sample) {
    if (!sample) return null;
    const hasEdge = sample.nextX !== undefined && sample.nextY !== undefined &&
        (sample.nextX !== sample.x || sample.nextY !== sample.y);
    const p = sample.progress || 0;
    return {
        x: hasEdge ? sample.x + (sample.nextX - sample.x) * p : sample.x,
        y: hasEdge ? sample.y + (sample.nextY - sample.y) * p : sample.y,
        dirX: hasEdge ? Math.sign(sample.nextX - sample.x) : 0,
        dirY: hasEdge ? Math.sign(sample.nextY - sample.y) : 0,
    };
}

function drawAMRs(now) {
    for (const id in currentAMRPositions) {
        const curr = currentAMRPositions[id];
        const prev = lastAMRPositions[id] || curr;

        const prevAbs = absPos(prev);
        const currAbs = absPos(curr);

        // Time-based blend between the two most recent *known* absolute
        // positions — always spatially valid, never crosses edges.
        const dt = now - currentFrameWallTime;
        const alpha = estFrameIntervalMs > 0 ? Math.max(0, Math.min(1, dt / estFrameIntervalMs)) : 1;
        let gx = prevAbs.x + (currAbs.x - prevAbs.x) * alpha;
        let gy = prevAbs.y + (currAbs.y - prevAbs.y) * alpha;

        // Mild predictive overshoot once we've caught up to the latest
        // frame, continuing along the AMR's current edge direction so
        // motion doesn't visibly stall if the next telemetry tick is late.
        if (alpha >= 1 && (currAbs.dirX || currAbs.dirY)) {
            const overshootS = Math.min((dt - estFrameIntervalMs) / 1000, 0.3);
            const speedCellsPerSec = 1 / 1.4; // matches AMRArtifact's secPerCell
            gx += currAbs.dirX * speedCellsPerSec * Math.max(0, overshootS);
            gy += currAbs.dirY * speedCellsPerSec * Math.max(0, overshootS);
        }

        const cx = px(gx) + CELL / 2;
        const cy = px(gy) + CELL / 2;

        const dx = currAbs.x - prevAbs.x, dy = currAbs.y - prevAbs.y;
        const angle = (Math.abs(dx) + Math.abs(dy) > 0.02) ? Math.atan2(dy, dx) : (drawAMRs._lastAngle?.[id] ?? 0);
        (drawAMRs._lastAngle ??= {})[id] = angle;

        const statusGlow = { AMR_MOVING: "#2563eb", AMR_BLOCKED: "#e74c3c", AMR_LOADING: "#e8a521", AMR_UNLOADING: "#e8a521" }[curr.status] || "#7f8c8d";

        sceneCtx.save();
        sceneCtx.translate(cx, cy);
        sceneCtx.shadowColor = statusGlow;
        sceneCtx.shadowBlur = 10;
        sceneCtx.rotate(angle);
        const icon = iconCache.amr;
        const size = CELL * 1.0; // was 0.8 and using a plain white box — bigger + a proper AGV silhouette now
        if (icon) sceneCtx.drawImage(icon, -size / 2, -size / 2, size, size);
        sceneCtx.restore();

        sceneCtx.fillStyle = "#cfe8ff";
        sceneCtx.font = "600 11px sans-serif";
        sceneCtx.textAlign = "center";
        sceneCtx.fillText(id, cx, cy + CELL / 2 + 13);
        if (curr.carryingOrderId) {
            sceneCtx.fillStyle = "#9aa0a8";
            sceneCtx.font = "10px sans-serif";
            sceneCtx.fillText(curr.carryingOrderId, cx, cy + CELL / 2 + 25);
        }
        sceneCtx.textAlign = "left";
    }
}

// ---- Side-panel rendering -------------------------------------------------
function renderStationPanel() {
    if (!selectedStationId) return;
    for (const btn of stationTabsEl.children) {
        btn.classList.toggle('active', btn.dataset.stationId === selectedStationId);
    }
    if (!latestFrame) { stationBodyEl.innerHTML = "Waiting for telemetry…"; return; }

    const s = stationStateFor(selectedStationId);
    const stateNum = s ? stationStateNumber(s) : STATE.IDLE;
    const stateName = STATION_STATE_NAMES[stateNum];
    const orderId = s ? field(s, "activeOrderId", "active_order_id") : null;
    const progress = s ? (field(s, "processingProgress", "processing_progress") || 0) : 0;

    let html = `
        <div class="panel-row">State <strong style="color:${STATION_STATE_COLORS[stateNum]}">${stateName}</strong></div>
        <div class="panel-row">Active order <strong>${orderId || "—"}</strong></div>
        <div class="panel-row">Progress <strong>${(progress * 100).toFixed(0)}%</strong></div>
    `;

    if (selectedStationId === "S5") {
        html += renderStation5Extra();
    }
    stationBodyEl.innerHTML = html;
}

function renderStation5Extra() {
    const voltage = field(latestFrame, "station5StackVoltageV", "station5_stack_voltage_v");
    const current = field(latestFrame, "station5CurrentDensityACm2", "station5_current_density_a_cm2");
    const tempCore = field(latestFrame, "station5StackCoreTempK", "station5_stack_core_temp_k");
    const tempSkin = field(latestFrame, "station5StackSkinTempK", "station5_stack_skin_temp_k");
    const hasRunTest = field(latestFrame, "station5HasRunTest", "station5_has_run_test");
    const flags = field(latestFrame, "station5FailureFlags", "station5_failure_flags") || 0;

    const s5 = stationStateFor("S5");
    const liveStateNum = s5 ? stationStateNumber(s5) : STATE.IDLE;

    if (liveStateNum === STATE.BUSY_PROCESSING && current > 0.0) {
        frozenTestCurrent = current;
        frozenTestVoltage = voltage;
    } else if (liveStateNum !== STATE.BUSY_PROCESSING) {
        frozenTestCurrent = null;
        frozenTestVoltage = null;
    }
    const displayCurrent = (liveStateNum === STATE.BUSY_PROCESSING && frozenTestCurrent !== null) ? frozenTestCurrent : current;
    const displayVoltage = (liveStateNum === STATE.BUSY_PROCESSING && frozenTestVoltage !== null) ? frozenTestVoltage : voltage;

    let html = `
        <div class="panel-row" style="margin-top:8px; border-top:1px solid var(--panel-border); padding-top:8px;">Stack voltage <strong>${displayVoltage !== undefined ? displayVoltage.toFixed(2) + " V" : "—"}</strong></div>
        <div class="panel-row">Current density <strong>${displayCurrent !== undefined ? displayCurrent.toFixed(3) + " A/cm²" : "—"}</strong></div>
        <div class="panel-row">Core temp <strong>${tempCore !== undefined ? tempCore.toFixed(1) + " K" : "—"}</strong></div>
        <div class="panel-row">Skin temp <strong>${tempSkin !== undefined ? tempSkin.toFixed(1) + " K" : "—"}</strong></div>
    `;

    if (hasRunTest) {
        const passed = field(latestFrame, "station5LastTestPassed", "station5_last_test_passed");
        const stackId = field(latestFrame, "station5LastTestedStackId", "station5_last_tested_stack_id");
        const voltages = field(latestFrame, "station5LastMeasuredVoltages", "station5_last_measured_voltages") || [];
        const resultColor = passed ? "#10b981" : "#ef4444";
        const flagNames = decodeFailureFlags(flags);

        html += `
            <div class="panel-row" style="margin-top:8px; border-top:1px solid var(--panel-border); padding-top:8px;">Last test stack <strong>${stackId || "—"}</strong></div>
            <div class="panel-row">Result <strong style="color:${resultColor}">${passed ? "PASSED" : "FAILED"}</strong></div>
            ${flagNames.length ? `<div class="panel-row">Flags <strong>${flagNames.join(", ")}</strong></div>` : ""}
            <div style="font-size:11px; color:var(--text-dim); margin-top:6px; word-break:break-all;">
                ${voltages.map(v => v.toFixed(2) + "V").join(", ") || "—"}
            </div>
        `;
    } else {
        html += `<div style="color:var(--text-dim); font-style:italic; margin-top:8px;">No test has run yet</div>`;
    }
    return html;
}

function renderAMRList() {
    const amrStates = field(latestFrame, "amrStates", "amr_states") || [];
    if (amrStates.length === 0) {
        amrListEl.innerHTML = `<div style="color:var(--text-dim); font-style:italic;">No AMR telemetry received yet</div>`;
        return;
    }
    amrListEl.innerHTML = amrStates.map(a => {
        const id = field(a, "amrId", "amr_id");
        const status = field(a, "status", "status");
        const order = field(a, "carryingOrderId", "carrying_order_id");
        return `<div class="amr-list-item"><span>${id}</span><span>${status}${order ? " · " + order : ""}</span></div>`;
    }).join('');
}

function updateDroppedFrameHud(count, simTimeS) {
    document.getElementById('droppedFrames').innerText = count || 0;
    if (simTimeS !== undefined) {
        document.getElementById('simTime').innerText = simTimeS.toFixed(2);
    }
}

// ---- small drawing helpers ------------------------------------------------
function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
}

function lerpColor(hexA, hexB, t) {
    const a = hexToRgb(hexA), b = hexToRgb(hexB);
    const r = Math.round(a.r + (b.r - a.r) * t);
    const g = Math.round(a.g + (b.g - a.g) * t);
    const bl = Math.round(a.b + (b.b - a.b) * t);
    return `rgb(${r},${g},${bl})`;
}
function hexToRgb(hex) {
    const n = parseInt(hex.replace('#', ''), 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

init();
