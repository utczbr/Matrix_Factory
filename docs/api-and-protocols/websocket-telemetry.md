# WebSocket TelemetryHub & HMAC Security (Reference)

This document describes the real-time telemetry streaming service (`TelemetryHub.java`), WebSocket endpoints, JSON event payload structures, and HMAC SHA-256 client authentication flows.

---

## Authentication Ticket Flow

To connect to the live WebSocket telemetry stream (`ws://127.0.0.1:8081/telemetry`), dashboard clients must first request an authenticated ticket token:

```mermaid
sequenceDiagram
    autonumber
    participant Client as Dashboard Web Client
    participant Auth as TelemetryHub Auth API
    participant WS as WebSocket Endpoint (WSS)

    Client->>Auth: POST http://127.0.0.1:8081/telemetry/ticket (Secret Header)
    Auth->>Auth: Generate HMAC SHA-256 Token (Timestamp + Nonce + Key)
    Auth-->>Client: 200 OK { "ticket": "a8f9c1b...", "expires_in": 300 }
    Client->>WS: Connect ws://127.0.0.1:8081/telemetry?ticket=a8f9c1b...
    WS->>WS: Validate Ticket & HMAC Signature
    WS-->>Client: 101 Switching Protocols (Stream Active)
```

---

## WebSocket JSON Telemetry Payload Schema

Events are emitted in JSON format on every step tick:

```json
{
  "event_type": "STATION_STEP_COMPLETED",
  "timestamp": 1722089400123,
  "simulation_tick": 450,
  "station_id": "STATION_3_STAMPING",
  "data": {
    "press_force_kN": 450.2,
    "ductile_damage_NCL": 0.384,
    "die_wear_um": 1.24,
    "microcrack_flag": false,
    "cycle_time_s": 3.8
  },
  "control_mode": "ADACOR"
}
```

---

## Telemetry Stream Categories

| Event Type | Description | Emitting Component | Frequency |
| --- | --- | --- | --- |
| `STATION_STEP_COMPLETED` | Output state updates from station solvers 1-5. | `SimBridgeArtifact.java` | Every tick |
| `HOLON_BID_LOGGED` | Contract-Net proposals and award notifications. | `DatabaseArtifact.java` | On CFP events |
| `CONTROL_MODE_CHANGED` | 2PC regime switch commit notifications (PROSA $\leftrightarrow$ ADACOR). | `supervisor_agent.asl` | On topology switch |
| `AMR_POSITION_UPDATED` | Battery level, grid position, and route milestones. | `amr_agent.asl` | Periodic (5 ticks) |
