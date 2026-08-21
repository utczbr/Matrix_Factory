// visualization/dashboard.js

let layout = null;
let TelemetryFrame = null;
const CLIENT_TOKEN = crypto.randomUUID();
const DEFAULT_RUN_COUNT = 30;

// ---- Canvas layers -------------------------------------------------------
const stage = document.getElementById('stage');
const gridCanvas = document.getElementById('gridCanvas');       // static: grid, no-go zones, docks, conveyors
const thermalCanvas = document.getElementById('thermalCanvas');   // dynamic: station5 heat glow
const sceneCanvas = document.getElementById('sceneCanvas');     // dynamic: stations, AMRs, animations
const gridCtx = gridCanvas.getContext('2d');
const thermalCtx = thermalCanvas.getContext('2d');
const sceneCtx = sceneCanvas.getContext('2d');

const runSelect = document.getElementById('runSelect');
const orgSchemaPill = document.getElementById('orgSchemaPill');
const stationTabsEl = document.getElementById('stationTabs');
const stationBodyEl = document.getElementById('stationBody');
const amrListEl = document.getElementById('amrList');
const orderTrackerEl = document.getElementById('orderTracker');

let CELL = 48; // nominal grid cell size in drawing units
let COLS = 20, ROWS = 12;

let lastAMRPositions = {};   // amrId -> {x,y,nextX,nextY,progress}
let currentAMRPositions = {};
let amrAngles = {};          // amrId -> current smooth angle
let lastFrameWallTime = 0;   // performance.now()
let currentFrameWallTime = 0;
let estFrameIntervalMs = 55.6; // ~18 Hz telemetry default
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
    if (!obj) return undefined;
    return obj[camel] !== undefined ? obj[camel] : obj[snake];
}

const STATION_STATE_NAMES = ["IDLE", "PROVISIONAL_LOCK", "BUSY_PROCESSING", "DEFECT_DETECTED", "OFFLINE"];
const STATE = { IDLE: 0, PROVISIONAL_LOCK: 1, BUSY_PROCESSING: 2, DEFECT_DETECTED: 3, OFFLINE: 4 };

const STATION_STATE_COLORS = {
    0: "#2ecc71",  // IDLE - green
    1: "#e8a521",  // PROVISIONAL_LOCK - amber
    2: "#2563eb",  // BUSY_PROCESSING - royal blue
    3: "#B71C1C",  // DEFECT_DETECTED - deep red
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

// ---- Setpoint parameters definition ------------------------------------
const SETPOINT_SPECS = {
    S1: [
        { param: 't_press_k', label: 'Press Temp [K]', default: 423.15 },
        { param: 'dwell_time_s', label: 'Dwell Time [s]', default: 12.0 }
    ],
    S2: [
        { param: 'v_coat_m_s', label: 'Coating Speed [m/s]', default: 0.05 },
        { param: 'mu_slurry_pa_s', label: 'Slurry Viscosity [Pa·s]', default: 1.2 }
    ],
    S3: [
        { param: 'press_force_kn', label: 'Press Force [kN]', default: 250.0 },
        { param: 'w0_initial_wear', label: 'Die Wear W0', default: 0.0 }
    ],
    S4: [
        { param: 'torque_bolt_0', label: 'Bolt Torque 0 [Nm]', default: 12.0 },
        { param: 'mu_friction_0', label: 'Friction Coeff 0', default: 0.15 }
    ],
    S5: [
        { param: 'operating_temp_k', label: 'Operating Temp [K]', default: 350.0 },
        { param: 'inlet_pressure_h2_bar', label: 'H2 Inlet Press [bar]', default: 2.0 },
        { param: 'inlet_pressure_o2_bar', label: 'O2 Inlet Press [bar]', default: 2.0 }
    ]
};

// ---- Boot -------------------------------------------------------------
async function init() {
    const res = await fetch('factory_layout.json');
    layout = await res.json();

    COLS = layout.grid.cols;
    ROWS = layout.grid.rows;
    CELL = layout.grid.cell_size_px;
    stage.style.setProperty('--grid-aspect', `${COLS} / ${ROWS}`);

    await Promise.all(Object.keys(ICON_SVGS).map(loadIcon));

    try {
        let root;
        try {
            root = await protobuf.load("sim_bridge.proto");
        } catch (e1) {
            root = await protobuf.load("../src/main/proto/sim_bridge.proto");
        }
        TelemetryFrame = root.lookupType("factory.TelemetryFrame");
    } catch (e) {
        console.error("Could not load sim_bridge.proto schema:", e);
        const wsStatus = document.getElementById('wsStatus');
        if (wsStatus) {
            wsStatus.textContent = 'SCHEMA LOAD FAILED';
            wsStatus.style.color = '#ef4444';
        }
        TelemetryFrame = {
            decode: () => ({ simTimeS: 0, stationStates: [], amrStates: [], droppedTelemetryFrameCount: 0 })
        };
    }

    resizeCanvases();
    new ResizeObserver(resizeCanvases).observe(stage);

    drawStaticGrid();
    buildStationTabs();

    populateRunSelector();
    setupControlForm();

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

function setupControlForm() {
    const stationSel = document.getElementById('ctrlStation');
    const paramSel = document.getElementById('ctrlParam');
    const valInput = document.getElementById('ctrlVal');

    if (!stationSel || !paramSel || !valInput) return;

    function updateParams() {
        const st = stationSel.value;
        const specs = SETPOINT_SPECS[st] || [];
        paramSel.innerHTML = '';
        specs.forEach(spec => {
            const opt = document.createElement('option');
            opt.value = spec.param;
            opt.textContent = spec.label;
            paramSel.appendChild(opt);
        });
        if (specs.length > 0) {
            valInput.value = specs[0].default;
        }
    }

    stationSel.addEventListener('change', updateParams);
    paramSel.addEventListener('change', () => {
        const st = stationSel.value;
        const spec = (SETPOINT_SPECS[st] || []).find(s => s.param === paramSel.value);
        if (spec) valInput.value = spec.default;
    });

    updateParams();

    document.getElementById('btnSendSetpoint')?.addEventListener('click', () => {
        const stationId = stationSel.value;
        const param = paramSel.value;
        const value = parseFloat(valInput.value);
        if (!isNaN(value)) {
            sendControlAction({ type: 'station_setpoint', stationId, param, value });
        }
    });

    document.getElementById('btnTriggerBreakdown')?.addEventListener('click', () => {
        const amrId = document.getElementById('ctrlAmr')?.value || 'AMR-1';
        sendControlAction({ type: 'amr_breakdown', amrId, downtimeSeconds: 60.0 });
    });
}

// ---- Responsive scaling -------------------------------------------------
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

    // High contrast no-go zones
    for (const zone of layout.no_go_zones || []) {
        const [[x0, y0], [x1, y1]] = zone;
        const minX = Math.min(x0, x1), minY = Math.min(y0, y1);
        const w = Math.abs(x1 - x0) + 1, h = Math.abs(y1 - y0) + 1;

        gridCtx.fillStyle = "rgba(220, 38, 38, 0.28)";
        gridCtx.fillRect(px(minX), px(minY), px(w), px(h));

        gridCtx.strokeStyle = "#ef4444";
        gridCtx.lineWidth = 1.5;
        gridCtx.strokeRect(px(minX) + 1, px(minY) + 1, px(w) - 2, px(h) - 2);
    }

    // High contrast cyan conveyor paths
    gridCtx.strokeStyle = "#06b6d4";
    gridCtx.lineWidth = 3;
    gridCtx.setLineDash([8, 5]);
    for (const path of layout.conveyor_paths || []) {
        const [[x0, y0], [x1, y1]] = path;
        gridCtx.beginPath();
        gridCtx.moveTo(px(x0) + CELL / 2, px(y0) + CELL / 2);
        gridCtx.lineTo(px(x1) + CELL / 2, px(y1) + CELL / 2);
        gridCtx.stroke();
    }
    gridCtx.setLineDash([]);

    // AMR Docks
    for (const dock of layout.amr_docks || []) {
        const [dx, dy] = dock.home;
        gridCtx.strokeStyle = "#3498db";
        gridCtx.lineWidth = 2;
        gridCtx.strokeRect(px(dx) + 4, px(dy) + 4, CELL - 8, CELL - 8);
        gridCtx.fillStyle = "#7ec8ff";
        gridCtx.font = "600 11px sans-serif";
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
    const host = window.location.hostname || '127.0.0.1';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let url = `${protocol}//${host}:8080/telemetry?run_id=${runId}&client=${CLIENT_TOKEN}`;
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

    const host = window.location.hostname || '127.0.0.1';
    const httpProtocol = window.location.protocol === 'https:' ? 'https:' : 'http:';

    let ticket = null;
    try {
        const response = await fetch(`${httpProtocol}//${host}:8081/telemetry/ticket?run_id=${runId}&client=${CLIENT_TOKEN}`);
        if (response.ok) {
            const data = await response.json();
            ticket = data.ticket;
        }
    } catch (e) {
        console.warn('[telemetry] ticket fetch failed', e);
    }

    if (myEpoch !== connectionEpoch) return;

    const url = telemetryUrl(runId, ticket);
    const ws = new WebSocket(url);
    activeWebSocket = ws;
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
        setConnectionStatus('connected');
    };

    ws.onerror = () => {
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
                    estFrameIntervalMs = estFrameIntervalMs * 0.8 + interval * 0.2;
                }
            }
            lastFrameWallTime = currentFrameWallTime;
            currentFrameWallTime = now;

            const seq = Number(field(frame, "sequenceNumber", "sequence_number") || 0);
            if (lastSequenceNumber !== null && seq > lastSequenceNumber + 1) {
                missedFrameFlashUntil = now + 180;
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
            renderOrderTracker();
            updateAuxiliaryTelemetry();
            updateDroppedFrameHud(field(frame, "droppedTelemetryFrameCount", "dropped_telemetry_frame_count"),
                field(frame, "simTimeS", "sim_time_s"));
        } catch (err) {
            console.error("Frame processing error", err);
        }
    };

    ws.onclose = (event) => {
        if (connectionEpoch !== myEpoch) return;
        if (activeWebSocket === ws) activeWebSocket = null;
        setConnectionStatus('disconnected');
        setTimeout(() => connect(currentRunId), 2000);
    };
}

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
    return states.find(x => field(x, "stationId", "station_id") === stationId);
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

        let fill = STATION_STATE_COLORS[stateNum] || "#555";
        if (stateNum === STATE.DEFECT_DETECTED) {
            const t = (Math.sin(now / (1000 / (2 * Math.PI * 2))) + 1) / 2;
            fill = lerpColor(STATION_STATE_COLORS[3], DEFECT_FLASH_COLOR, t);
        }
        sceneCtx.fillStyle = fill;
        roundRect(sceneCtx, x, y, w, h, 6);
        sceneCtx.fill();

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

        if (stateNum === STATE.BUSY_PROCESSING) {
            const cx = x + w / 2, cy = y + h / 2;
            const r = Math.min(w, h) / 2 - 4;
            const pulse = (Math.sin(now / 220) + 1) / 2;

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

        if (stateNum === STATE.PROVISIONAL_LOCK) {
            const t = (Math.sin(now / (1000 / (2 * Math.PI))) + 1) / 2;
            sceneCtx.strokeStyle = `rgba(255,255,255,${0.25 + t * 0.6})`;
            sceneCtx.lineWidth = 2;
            roundRect(sceneCtx, x + 1, y + 1, w - 2, h - 2, 6);
            sceneCtx.stroke();
        }

        if (missedFlash) {
            sceneCtx.strokeStyle = "#ffffff";
            sceneCtx.lineWidth = 3;
            roundRect(sceneCtx, x + 1, y + 1, w - 2, h - 2, 6);
            sceneCtx.stroke();
        }

        const icon = iconCache[st.icon];
        if (icon) {
            const iconSize = Math.min(w, h) * 0.45;
            sceneCtx.drawImage(icon, x + w / 2 - iconSize / 2, y + h / 2 - iconSize / 2 - 6, iconSize, iconSize);
        }

        // Dynamic text scaling to prevent overflow on cards S2, S3, S4
        sceneCtx.fillStyle = "#fff";
        let fontSize = 11;
        sceneCtx.font = `600 ${fontSize}px sans-serif`;
        const labelText = `${st.id} · ${st.label}`;
        const maxTextW = w - 8;
        while (fontSize > 8 && sceneCtx.measureText(labelText).width > maxTextW) {
            fontSize -= 0.5;
            sceneCtx.font = `600 ${fontSize}px sans-serif`;
        }
        sceneCtx.textAlign = "center";
        sceneCtx.fillText(labelText, x + w / 2, y + h - 6);
        sceneCtx.textAlign = "left";

        if (st.id === selectedStationId) {
            sceneCtx.strokeStyle = "#f1c40f";
            sceneCtx.lineWidth = 2;
            roundRect(sceneCtx, x - 3, y - 3, w + 6, h + 6, 8);
            sceneCtx.stroke();
        }
    }
}

function drawThermalGlow(now) {
    const s5 = layout.stations.find(s => s.id === "S5");
    if (!s5) return;
    const core = field(latestFrame, "station5StackCoreTempK", "station5_stack_core_temp_k");
    if (core === undefined) return;
    const b = stationCellBounds(s5);
    const cx = px(b.x0) + px(b.x1 - b.x0 + 1) / 2;
    const cy = px(b.y0) + px(b.y1 - b.y0 + 1) / 2;
    const heat = Math.max(0, Math.min(1, (core - 320) / (380 - 320)));
    const r = CELL * 3;
    const grad = thermalCtx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, `rgba(255,${Math.round(160 - heat * 120)},60,${0.35 * heat})`);
    grad.addColorStop(1, "rgba(255,80,0,0)");
    thermalCtx.fillStyle = grad;
    thermalCtx.beginPath();
    thermalCtx.arc(cx, cy, r, 0, Math.PI * 2);
    thermalCtx.fill();
}

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

function lerpAngle(a, b, t) {
    let diff = (b - a) % (2 * Math.PI);
    if (diff < -Math.PI) diff += 2 * Math.PI;
    if (diff > Math.PI) diff -= 2 * Math.PI;
    return a + diff * t;
}

function drawAMRs(now) {
    for (const id in currentAMRPositions) {
        const curr = currentAMRPositions[id];
        const prev = lastAMRPositions[id] || curr;

        const prevAbs = absPos(prev);
        const currAbs = absPos(curr);

        const dt = now - currentFrameWallTime;
        const alpha = estFrameIntervalMs > 0 ? Math.max(0, Math.min(1, dt / estFrameIntervalMs)) : 1;
        let gx = prevAbs.x + (currAbs.x - prevAbs.x) * alpha;
        let gy = prevAbs.y + (currAbs.y - prevAbs.y) * alpha;

        if (alpha >= 1 && (currAbs.dirX || currAbs.dirY)) {
            const overshootS = Math.min((dt - estFrameIntervalMs) / 1000, 0.3);
            const speedCellsPerSec = 1 / 1.4;
            gx += currAbs.dirX * speedCellsPerSec * Math.max(0, overshootS);
            gy += currAbs.dirY * speedCellsPerSec * Math.max(0, overshootS);
        }

        const cx = px(gx) + CELL / 2;
        const cy = px(gy) + CELL / 2;

        const dx = currAbs.x - prevAbs.x, dy = currAbs.y - prevAbs.y;
        const targetAngle = (Math.abs(dx) + Math.abs(dy) > 0.02) ? Math.atan2(dy, dx) : (amrAngles[id] ?? 0);
        const currentAngle = amrAngles[id] ?? targetAngle;
        const smoothAngle = lerpAngle(currentAngle, targetAngle, 0.15);
        amrAngles[id] = smoothAngle;

        const statusGlow = { AMR_MOVING: "#2563eb", AMR_BLOCKED: "#e74c3c", AMR_LOADING: "#e8a521", AMR_UNLOADING: "#e8a521" }[curr.status] || "#7f8c8d";

        sceneCtx.save();
        sceneCtx.translate(cx, cy);
        sceneCtx.shadowColor = statusGlow;
        sceneCtx.shadowBlur = 10;
        sceneCtx.rotate(smoothAngle);
        const icon = iconCache.amr;
        const size = CELL * 1.0;
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

    // Render station physical metrics
    if (s) {
        if (selectedStationId === "S1") {
            const alpha = field(s, "alphaFinal", "alpha_final");
            const delam = field(s, "delaminationRisk", "delamination_risk");
            const pinhole = field(s, "pinholeRisk", "pinhole_risk");
            html += `
                <div class="panel-row" style="margin-top:6px; border-top:1px solid var(--panel-border); padding-top:6px;">Alpha Final <strong>${alpha !== undefined ? alpha.toFixed(3) : "—"}</strong></div>
                <div class="panel-row">Delam. Risk <strong>${delam !== undefined ? (delam * 100).toFixed(1) + "%" : "—"}</strong></div>
                <div class="panel-row">Pinhole Risk <strong>${pinhole !== undefined ? (pinhole * 100).toFixed(1) + "%" : "—"}</strong></div>
            `;
        } else if (selectedStationId === "S2") {
            const ecsa = field(s, "ecsaRatio", "ecsa_ratio");
            html += `
                <div class="panel-row" style="margin-top:6px; border-top:1px solid var(--panel-border); padding-top:6px;">ECSA Ratio <strong>${ecsa !== undefined ? ecsa.toFixed(3) : "—"}</strong></div>
            `;
        } else if (selectedStationId === "S3") {
            const damage = field(s, "damageIndex", "damage_index");
            html += `
                <div class="panel-row" style="margin-top:6px; border-top:1px solid var(--panel-border); padding-top:6px;">Damage Index <strong>${damage !== undefined ? damage.toFixed(3) : "—"}</strong></div>
            `;
        } else if (selectedStationId === "S4") {
            const porosity = field(s, "gdlPorosity", "gdl_porosity");
            const pClamp = field(s, "pClampMpa", "p_clamp_mpa");
            const eTangent = field(s, "eTangentMpa", "e_tangent_mpa");
            html += `
                <div class="panel-row" style="margin-top:6px; border-top:1px solid var(--panel-border); padding-top:6px;">GDL Porosity <strong>${porosity !== undefined ? porosity.toFixed(3) : "—"}</strong></div>
                <div class="panel-row">Clamping Press <strong>${pClamp !== undefined ? pClamp.toFixed(2) + " MPa" : "—"}</strong></div>
                <div class="panel-row">Tangent Modulus <strong>${eTangent !== undefined ? eTangent.toFixed(1) + " MPa" : "—"}</strong></div>
            `;
        }
    }

    if (selectedStationId === "S5") {
        html += renderStation5Extra();
    }
    stationBodyEl.innerHTML = html;

    if (selectedStationId === "S5") {
        const voltages = field(latestFrame, "station5LastMeasuredVoltages", "station5_last_measured_voltages") || [];
        const currentDensities = field(latestFrame, "station5LastCurrentDensities", "station5_last_current_densities") || [];
        const canvas = document.getElementById('ivCanvas');
        if (canvas) drawIVCurve(canvas, voltages, currentDensities);
    }
}

function renderStation5Extra() {
    const voltage = field(latestFrame, "station5StackVoltageV", "station5_stack_voltage_v");
    const current = field(latestFrame, "station5CurrentDensityACm2", "station5_current_density_a_cm2");
    const tempCore = field(latestFrame, "station5StackCoreTempK", "station5_stack_core_temp_k");
    const tempSkin = field(latestFrame, "station5StackSkinTempK", "station5_stack_skin_temp_k");
    const hasRunTest = field(latestFrame, "station5HasRunTest", "station5_has_run_test");
    const flags = field(latestFrame, "station5FailureFlags", "station5_failure_flags") || 0;

    let html = `
        <div class="panel-row" style="margin-top:8px; border-top:1px solid var(--panel-border); padding-top:8px;">Stack voltage <strong>${voltage !== undefined ? voltage.toFixed(2) + " V" : "—"}</strong></div>
        <div class="panel-row">Current density <strong>${current !== undefined ? current.toFixed(3) + " A/cm²" : "—"}</strong></div>
        <div class="panel-row">Core temp <strong>${tempCore !== undefined ? tempCore.toFixed(1) + " K" : "—"}</strong></div>
        <div class="panel-row">Skin temp <strong>${tempSkin !== undefined ? tempSkin.toFixed(1) + " K" : "—"}</strong></div>
    `;

    if (hasRunTest) {
        const passed = field(latestFrame, "station5LastTestPassed", "station5_last_test_passed");
        const stackId = field(latestFrame, "station5LastTestedStackId", "station5_last_tested_stack_id");
        const resultColor = passed ? "#10b981" : "#ef4444";
        const flagNames = decodeFailureFlags(flags);

        html += `
            <div class="panel-row" style="margin-top:8px; border-top:1px solid var(--panel-border); padding-top:8px;">Last test stack <strong>${stackId || "—"}</strong></div>
            <div class="panel-row">Result <strong style="color:${resultColor}">${passed ? "PASSED" : "FAILED"}</strong></div>
            ${flagNames.length ? `<div class="panel-row">Flags <strong>${flagNames.join(", ")}</strong></div>` : ""}
            <div style="margin-top:8px;">
                <div style="font-size:11px; color:var(--text-dim); margin-bottom:4px;">Polarization IV Curve:</div>
                <canvas id="ivCanvas" width="290" height="120" style="background:#14161a; border:1px solid var(--panel-border); border-radius:4px; width:100%; display:block;"></canvas>
            </div>
        `;
    } else {
        html += `<div style="color:var(--text-dim); font-style:italic; margin-top:8px;">No test has run yet</div>`;
    }
    return html;
}

function drawIVCurve(canvas, voltages, currentDensities) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (!voltages || voltages.length === 0) {
        ctx.fillStyle = "#9aa0a8";
        ctx.font = "11px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("No curve data available", w / 2, h / 2);
        return;
    }

    const defaultJ = [0.05, 0.15, 0.25, 0.40, 0.55, 0.70, 0.85, 1.00, 1.15, 1.30, 1.40, 1.50];
    const jVals = (currentDensities && currentDensities.length === voltages.length) ? currentDensities : defaultJ;

    const padL = 35, padR = 15, padT = 15, padB = 25;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    const minJ = 0, maxJ = 1.6;
    const minV = 0, maxV = 1.0;

    // Gridlines
    ctx.strokeStyle = "#2c3038";
    ctx.lineWidth = 1;
    for (let v = 0; v <= 1.0; v += 0.25) {
        const y = padT + plotH * (1 - (v - minV) / (maxV - minV));
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke();
        ctx.fillStyle = "#9aa0a8";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(v.toFixed(1) + "V", padL - 4, y + 3);
    }
    for (let j = 0; j <= 1.5; j += 0.5) {
        const x = padL + plotW * ((j - minJ) / (maxJ - minJ));
        ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + plotH); ctx.stroke();
        ctx.fillStyle = "#9aa0a8";
        ctx.font = "9px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(j.toFixed(1), x, padT + plotH + 14);
    }

    // IV curve line
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < voltages.length; i++) {
        const j = jVals[i] || (i * 0.12);
        const v = voltages[i];
        const x = padL + plotW * ((j - minJ) / (maxJ - minJ));
        const y = padT + plotH * (1 - Math.max(0, Math.min(1, (v - minV) / (maxV - minV))));
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Data points
    for (let i = 0; i < voltages.length; i++) {
        const j = jVals[i] || (i * 0.12);
        const v = voltages[i];
        const x = padL + plotW * ((j - minJ) / (maxJ - minJ));
        const y = padT + plotH * (1 - Math.max(0, Math.min(1, (v - minV) / (maxV - minV))));
        ctx.fillStyle = "#0284c7";
        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
    }
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

function renderOrderTracker() {
    if (!orderTrackerEl) return;
    const orders = field(latestFrame, "orderStates", "order_states") || [];
    if (orders.length === 0) {
        orderTrackerEl.innerHTML = `<div style="color:var(--text-dim); font-style:italic; font-size:12px;">No active orders</div>`;
        return;
    }
    orderTrackerEl.innerHTML = orders.map(o => {
        const id = field(o, "orderId", "order_id");
        const loc = field(o, "currentLocation", "current_location");
        const status = field(o, "status", "status");
        const prog = field(o, "progress", "progress") || 0;
        return `
            <div class="order-item">
                <span><strong>${id}</strong> @ ${loc}</span>
                <span style="color:var(--accent-amber);">${status} (${(prog * 100).toFixed(0)}%)</span>
            </div>
        `;
    }).join('');
}

function updateAuxiliaryTelemetry() {
    if (!latestFrame) return;
    const pTank = field(latestFrame, "h2TankPressureBar", "h2_tank_pressure_bar");
    const fTank = field(latestFrame, "h2TankFillFraction", "h2_tank_fill_fraction");
    const tChiller = field(latestFrame, "chillerTempK", "chiller_temp_k");
    const pComp = field(latestFrame, "compressorPowerKw", "compressor_power_kw");
    const price = field(latestFrame, "energyPrice", "energy_price");
    const dNers = field(latestFrame, "droppedNerCount", "dropped_ner_count");

    document.getElementById('auxH2Press').textContent = pTank !== undefined ? pTank.toFixed(2) : "—";
    document.getElementById('auxH2Fill').textContent = fTank !== undefined ? (fTank * 100).toFixed(1) : "—";
    document.getElementById('auxChiller').textContent = tChiller !== undefined ? tChiller.toFixed(1) : "—";
    document.getElementById('auxCompressor').textContent = pComp !== undefined ? pComp.toFixed(2) : "—";
    document.getElementById('auxEnergyPrice').textContent = price !== undefined ? price.toFixed(4) : "—";
    document.getElementById('auxDroppedNers').textContent = dNers !== undefined ? dNers : "0";
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
    let c = hex.replace('#', '');
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    const num = parseInt(c, 16);
    return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
}

async function sendControlAction(actionData) {
    try {
        const host = window.location.hostname || '127.0.0.1';
        const httpProtocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        const ticketRes = await fetch(`${httpProtocol}//${host}:8081/control/ticket?run_id=${currentRunId}`);
        const { ticket } = await ticketRes.json();
        const res = await fetch(`${httpProtocol}//${host}:8081/control/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket, runId: currentRunId, ...actionData })
        });
        const data = await res.json();
        console.log("Control Action response:", data);
    } catch (e) {
        console.error("Failed to send control action:", e);
    }
}

init();
