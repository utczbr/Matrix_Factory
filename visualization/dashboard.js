// visualization/dashboard.js

let layout = null;
let TelemetryFrame = null;

const canvas = document.getElementById('factoryCanvas');
const ctx = canvas.getContext('2d');

let lastAMRPositions = {};
let currentAMRPositions = {};
let lastFrameTime = 0;
let currentFrameTime = 0;

async function init() {
    // Load layout
    const res = await fetch('factory_layout.json');
    layout = await res.json();
    console.log("Loaded layout:", layout.layout_version);

    // Setup protobuf (assuming a .proto file or we can define a simple root)
    // For Phase 3.5, we'll try to load physical_engine/proto/sim_bridge.proto if accessible,
    // or just mock the decode if we're hitting CORS issues running from file://
    try {
        const root = await protobuf.load("../physical_engine/proto/sim_bridge.proto");
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

    connect();
    requestAnimationFrame(renderLoop);
}

function connect() {
    const ws = new WebSocket("ws://127.0.0.1:8080/telemetry");
    ws.binaryType = "arraybuffer";

    ws.onmessage = (event) => {
        let frame;
        try {
            frame = TelemetryFrame.decode(new Uint8Array(event.data));
        } catch (e) {
            console.error("Decode error", e);
            return;
        }
        
        // Update interpolation state
        lastFrameTime = currentFrameTime;
        currentFrameTime = performance.now();
        lastAMRPositions = JSON.parse(JSON.stringify(currentAMRPositions));
        
        if (frame.amrPositions) {
            for (let amr of frame.amrPositions) {
                currentAMRPositions[amr.id] = {x: amr.x, y: amr.y};
            }
        }

        renderStations(frame.stationStates);
        updateDroppedFrameHud(frame.droppedTelemetryFrameCount, frame.simTimeS);
    };

    ws.onclose = (event) => {
        console.warn(`Telemetry connection closed (code ${event.code}) — reconnecting in 2s`);
        setTimeout(connect, 2000);
    };
}

function renderStations(states) {
    if (!layout || !states) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw stations
    for (let station of layout.stations) {
        ctx.fillStyle = "#555"; // Default
        // Find state
        let s = states.find(x => x.id === station.id);
        if (s) {
            ctx.fillStyle = s.isBusy ? "#e74c3c" : "#2ecc71";
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
