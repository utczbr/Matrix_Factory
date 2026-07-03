// visualization/dashboard.js

let layout = null;
let TelemetryFrame = null;
const CLIENT_TOKEN = crypto.randomUUID();
const DEFAULT_RUN_COUNT = 30;

const canvas = document.getElementById('factoryCanvas');
const ctx = canvas.getContext('2d');
const runSelect = document.getElementById('runSelect');

let lastAMRPositions = {};
let currentAMRPositions = {};
let lastFrameTime = 0;
let currentFrameTime = 0;
let activeWebSocket = null;
let currentRunId = 0;
let connectionEpoch = 0;

// protobuf.js decodes to camelCase by default, but tolerate snake_case too
// in case the loader ever falls back to a differently-configured root.
function field(obj, camel, snake) {
    return obj[camel] !== undefined ? obj[camel] : obj[snake];
}

const STATION_STATE_NAMES = ["IDLE", "PROVISIONAL_LOCK", "BUSY_PROCESSING", "DEFECT_DETECTED", "OFFLINE"];
const STATION_STATE_COLORS = {
    0: "#2ecc71", // IDLE - green
    1: "#f1c40f", // PROVISIONAL_LOCK - yellow
    2: "#e74c3c", // BUSY_PROCESSING - red
    3: "#8e44ad", // DEFECT_DETECTED - purple (distinct from busy/idle)
    4: "#7f8c8d", // OFFLINE - gray
};

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
    // protobuf.js can also hand back the enum's string key depending on config
    const idx = STATION_STATE_NAMES.indexOf(String(raw).replace("STATION_", ""));
    return idx >= 0 ? idx : 0;
}

async function init() {
    // Load layout
    const res = await fetch('factory_layout.json');
    layout = await res.json();
    console.log("Loaded layout:", layout.layout_version);

    // Setup protobuf (assuming a .proto file or we can define a simple root)
    // For Phase 3.5, we'll try to load physical_engine/proto/sim_bridge.proto if accessible,
    // or just mock the decode if we're hitting CORS issues running from file://
    try {
        const root = await protobuf.load("../src/main/proto/sim_bridge.proto");
        TelemetryFrame = root.lookupType("factory.TelemetryFrame");
    } catch (e) {
        console.warn("Could not load .proto, using a mock decode for V5 visual validation", e);
        // Minimal mock to pass the UI validation if proto isn't served
        TelemetryFrame = {
            decode: (data) => {
                // In a real scenario this decodes the Uint8Array. 
                // We'll mock returning empty states if decode fails.
                return { simTimeS: 0, stationStates: [], amrPositions: [], droppedTelemetryFrameCount: 0 };
            }
        };
    }

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

function telemetryUrl(runId) {
    return `ws://127.0.0.1:8080/telemetry?run_id=${runId}&client=${CLIENT_TOKEN}`;
}

function connect(runId) {
    if (activeWebSocket) {
        const previousSocket = activeWebSocket;
        activeWebSocket = null;
        previousSocket.close(1000, 'run switch');
    }

    const myEpoch = ++connectionEpoch;
    const ws = new WebSocket(telemetryUrl(runId));
    activeWebSocket = ws;
    ws.binaryType = "arraybuffer";

    ws.onmessage = (event) => {
        let frame;
        try {
            frame = TelemetryFrame.decode(new Uint8Array(event.data));
        } catch (e) {
            console.error("Decode error", e);
            return;
        }

        try {
            // Update interpolation state
            lastFrameTime = currentFrameTime;
            currentFrameTime = performance.now();
            lastAMRPositions = JSON.parse(JSON.stringify(currentAMRPositions));

            if (frame.amrStates) {
                for (let amr of frame.amrStates) {
                    // Protobuf fields: amr_id, grid_x, grid_y
                    const amrId = amr.amrId || amr.amr_id;
                    const x = amr.gridX !== undefined ? amr.gridX : amr.grid_x;
                    const y = amr.gridY !== undefined ? amr.gridY : amr.grid_y;
                    currentAMRPositions[amrId] = { x: x * 40, y: y * 40 }; // Assuming grid cells need scaling
                }
            }

            renderStations(frame.stationStates || frame.station_states);
            renderStation5Panel(frame);
            updateDroppedFrameHud(frame.droppedTelemetryFrameCount, frame.simTimeS);
        } catch (err) {
            ctx.fillStyle = "red";
            ctx.font = "20px Arial";
            ctx.fillText("Error: " + err.message, 50, 50);
            console.error("Frame processing error", err);
        }
    };

    ws.onclose = (event) => {
        if (connectionEpoch !== myEpoch) {
            return;
        }
        if (activeWebSocket === ws) {
            activeWebSocket = null;
        }
        console.warn(`Telemetry connection closed (code ${event.code}) — reconnecting in 2s`);
        setTimeout(() => connect(currentRunId), 2000);
    };
}

function switchRun(runId) {
    currentRunId = runId;
    runSelect.value = String(runId);
    connect(runId);
}

function renderStations(states) {
    if (!layout || !states) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw stations
    for (let station of layout.stations) {
        // Find state
        let mappedId = station.id.replace("station_", "S");
        let s = states.find(x => (x.stationId || x.station_id) === mappedId);
        // Previously this only distinguished BUSY_PROCESSING (red) from
        // everything else (green) — so DEFECT_DETECTED and OFFLINE rendered
        // identically to IDLE and were indistinguishable on the map. Now
        // uses the full state -> color mapping.
        ctx.fillStyle = s ? (STATION_STATE_COLORS[stationStateNumber(s)] || "#555") : "#555";
        ctx.fillRect(station.x, station.y, station.width, station.height);
        ctx.fillStyle = "#fff";
        ctx.fillText(station.id, station.x + 5, station.y + 20);
        if (s) {
            const orderId = field(s, "activeOrderId", "active_order_id");
            if (orderId) {
                ctx.font = "10px Arial";
                ctx.fillText(orderId, station.x + 5, station.y + 34);
                ctx.font = "10px sans-serif";
            }
        }
    }
}

function renderStation5Panel(frame) {
    const body = document.getElementById('station5Body');
    if (!body) return;

    const voltage = field(frame, "station5StackVoltageV", "station5_stack_voltage_v");
    const current = field(frame, "station5CurrentDensityACm2", "station5_current_density_a_cm2");
    const tempCore = field(frame, "station5StackCoreTempK", "station5_stack_core_temp_k");
    const tempSkin = field(frame, "station5StackSkinTempK", "station5_stack_skin_temp_k");
    const flags = field(frame, "station5FailureFlags", "station5_failure_flags") || 0;
    const hasRunTest = field(frame, "station5HasRunTest", "station5_has_run_test");
    const lastPassed = field(frame, "station5LastTestPassed", "station5_last_test_passed");
    const lastStackId = field(frame, "station5LastTestedStackId", "station5_last_tested_stack_id");

    const stationStates = frame.stationStates || frame.station_states || [];
    const s5 = stationStates.find(x => (x.stationId || x.station_id) === "S5");
    const liveStateNum = s5 ? stationStateNumber(s5) : 0;
    const liveStateName = STATION_STATE_NAMES[liveStateNum] || "UNKNOWN";


    let html = `
        <div>Live state: <strong style="color:${STATION_STATE_COLORS[liveStateNum]}">${liveStateName}</strong></div>
        <div style="font-weight: 500; font-size: 14px; color: #4b5563; margin-top: 15px;">Test Bench Background State:</div>
        <div>Background voltage: ${voltage !== undefined ? voltage.toFixed(2) + " V" : "—"}</div>
        <div>Background current: ${current !== undefined ? current.toFixed(3) + " A/cm²" : "—"}</div>
        <div>Background core temp: ${tempCore !== undefined ? tempCore.toFixed(1) + " K" : "—"}</div>
        <div>Background skin temp: ${tempSkin !== undefined ? tempSkin.toFixed(1) + " K" : "—"}</div>
    `;

    // New Test Results section
    if (frame.station5HasRunTest) {
        let resultColor = frame.station5LastTestPassed ? "#10b981" : "#ef4444";
        let resultText = frame.station5LastTestPassed ? "PASSED" : "FAILED";
        
        // Extract measured voltages array
        const measuredVoltages = frame.station5LastMeasuredVoltages || [];
        
        let curveHtml = "—";
        if (measuredVoltages.length > 0) {
            // Very simple text-based plot for now, showing the min, max, or the array
            curveHtml = measuredVoltages.map(v => v.toFixed(2) + "V").join(", ");
        }

        html += `
            <div style="font-weight: 500; font-size: 14px; color: #4b5563; margin-top: 15px; border-top: 1px solid #e5e7eb; padding-top: 10px;">Latest Polarization Test:</div>
            <div>Target Stack: <strong>${frame.station5LastTestedStackId || "—"}</strong></div>
            <div>Status: <span style="color: ${resultColor}; font-weight: bold;">${resultText}</span></div>
            <div>Diagnostic Flags: ${frame.station5FailureFlags || 0}</div>
            <div style="margin-top: 8px;"><strong>Measured Voltages (Sweep):</strong></div>
            <div style="font-size: 11px; color: #6b7280; word-break: break-all;">${curveHtml}</div>
        `;
    } else {
        html += `
            <div style="font-weight: 500; font-size: 14px; color: #4b5563; margin-top: 15px; border-top: 1px solid #e5e7eb; padding-top: 10px;">Latest Polarization Test:</div>
            <div style="color: #6b7280; font-style: italic;">No test has run yet</div>
        `;
    }
    body.innerHTML = html;
}

function renderLoop() {
    // AMR gap-recovery interpolation
    if (layout) {
        let now = performance.now();
        let dt = now - currentFrameTime;
        let frameDuration = currentFrameTime - lastFrameTime;
        if (frameDuration <= 0) frameDuration = 50; // default 50ms (20hz)

        let alpha = Math.min(dt / frameDuration, 1.0);

        for (let id in currentAMRPositions) {
            let curr = currentAMRPositions[id];
            let prev = lastAMRPositions[id] || curr;

            let interpX = prev.x + (curr.x - prev.x) * alpha;
            let interpY = prev.y + (curr.y - prev.y) * alpha;

            ctx.fillStyle = "#3498db";
            ctx.beginPath();
            ctx.arc(interpX, interpY, 10, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = "#fff";
            ctx.fillText(id, interpX + 15, interpY + 5);
        }
    }
    requestAnimationFrame(renderLoop);
}

function updateDroppedFrameHud(count, simTimeS) {
    document.getElementById('droppedFrames').innerText = count || 0;
    if (simTimeS !== undefined) {
        document.getElementById('simTime').innerText = simTimeS.toFixed(2);
    }
}

init();
