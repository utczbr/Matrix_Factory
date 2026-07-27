# JaCaMo & CArtAgO Infrastructure (Explanation & Reference)

This document describes the multi-agent system (MAS) infrastructure uniting **Jason BDI agent reasoning**, **CArtAgO shared environment artifacts**, and **Moise organizational models** in **Matrix Factory Twin**.

---

## JaCaMo Project Organization (`factory.jcm`)

The JaCaMo application structure defines agent instances, workspace definitions, and artifact initializations:

```text
mas matrix_factory_twin {

    agent supervisor : supervisor_agent.asl {
        focus: factory_workspace.db_art
               factory_workspace.telemetry_art
    }

    agent order_1 : order_holon.asl {
        instances: 5
    }

    agent resource_station_1 : resource_holon.asl {
        beliefs: station_type("station_1_resin")
    }

    workspace factory_workspace {
        artifact db_art: env.DatabaseArtifact("factory_history.db")
        artifact telemetry_art: env.TelemetryHub(8081)
        artifact sim_bridge: env.SimBridgeArtifact("127.0.0.1", 50051)
    }

}
```

---

## CArtAgO Shared Environment Artifacts

CArtAgO artifacts encapsulate environment operations, exposing **Observable Properties**, **Signals**, and **Annotated Actions**:

```mermaid
graph TD
    subgraph CArtAgO Workspace
        DB["DatabaseArtifact<br>(SQLite WAL Queue)"]
        TEL["TelemetryHub<br>(WSS Port 8081)"]
        BRIDGE["SimBridgeArtifact<br>(gRPC IPC)"]
    end

    AGENT["Jason BDI Agent"] -->|@OPERATION log_event()| DB
    AGENT -->|@OPERATION broadcast_metric()| TEL
    AGENT -->|@OPERATION step_physics()| BRIDGE

    BRIDGE -.->|Observable Property: tick(T)| AGENT
    TEL -.->|Signal: client_connected| AGENT
```

### Artifact API Reference

1. **`DatabaseArtifact.java`:**
   - Operation: `log_event(String stationId, String eventType, double value)`
   - Operation: `log_bid(String orderId, String resourceId, double bidCost)`
2. **`TelemetryHub.java`:**
   - Operation: `broadcast_telemetry(String jsonPayload)`
   - Observable Property: `active_connections(int count)`
3. **`SimBridgeArtifact.java`:**
   - Operation: `step_station(String stationId, double dt)`
   - Observable Property: `station_state(String stationId, String jsonState)`
