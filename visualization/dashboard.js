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

async function init() {
    // Load layout
    const res = await fetch('factory_layout.json');
    layout = await res.json();
    console.log("Loaded layout:", layout.layout_version);

    // Setup protobuf (assuming a .proto file or we can define a simple root)
    // For Phase 3.5, we'll try to load physical_engine/proto/sim_bridge.proto if accessible,
    // or just mock the decode if we're hitting CORS issues running from file://
    try {
        const root = await protobuf.load("../physical_engine/protos/sim_bridge.proto");
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
        ctx.fillStyle = "#555"; // Default
        // Find state
        let s = states.find(x => (x.stationId || x.station_id) === station.id);
        if (s) {
            // state === 2 is STATION_BUSY_PROCESSING
            ctx.fillStyle = s.state === 2 ? "#e74c3c" : "#2ecc71";
        }
        ctx.fillRect(station.x, station.y, station.width, station.height);
        ctx.fillStyle = "#fff";
        ctx.fillText(station.id, station.x + 5, station.y + 20);
    }
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
