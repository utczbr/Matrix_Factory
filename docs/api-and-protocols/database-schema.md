# Database Schema & Asynchronous Queue (Reference)

This document presents the relational database schema, SQLite Write-Ahead Logging (WAL) configuration, and non-blocking asynchronous writer queue implemented in `DatabaseArtifact.java`.

---

## SQLite WAL Mode & Performance Tuning

Matrix Factory Twin utilizes SQLite with Write-Ahead Logging (`WAL`) mode:

```sql
PRAGMA journal_mode = WAL;
PRAGMA wal_autocheckpoint = 100;
PRAGMA synchronous = NORMAL;
```

This configuration permits non-blocking concurrent reads while `DatabaseArtifact.java` flushes telemetry and quality logs asynchronously.

---

## Entity-Relationship Schema

```mermaid
erDiagram
    Orders {
        integer run_id
        text order_id
        text event_type
        real sim_time
    }

    StationQuality {
        integer run_id
        text stack_id
        text station_id
        integer defect
        real t_proc_s
        real t_mean_s
        real sim_time
    }

    EnergyTelemetry {
        integer run_id
        real sim_time
        real energy_price_eur_mwh
        real compressor_power_kw
    }
```

> **Not implemented note:** Bid-logging and topology-switch-logging tables (previously documented as `HOLON_BIDS` and `TOPOLOGY_SWITCHES`) are not implemented in `DatabaseArtifact.java`. Bid tenders and 2PC regime transitions occur dynamically in agent memory (`supervisor_agent.asl` and `order_holon.asl`) but are not persisted to SQLite.

---

## Asynchronous Batch Queue Architecture

To prevent disk I/O bottlenecks from stalling the agent execution loop, `DatabaseArtifact.java` utilizes three dedicated `ArrayBlockingQueue` buffers (capacity 300,000 records each: `queue`, `qualityQueue`, `energyQueue`) serviced by a background drain thread (`drainLoop()`):

```mermaid
graph LR
    A[CArtAgO Operation Thread] -->|offer, non-blocking| B["3× ArrayBlockingQueue&lt;Record&gt; (cap 300,000 each: Orders / StationQuality / EnergyTelemetry)"]
    B -->|drain every 500ms, batch up to 2,000| C[Background Writer Thread]
    C -->|executeBatch + commit| D[factory_history.db SQLite WAL]
    C -.->|on failed commit: requeue batch, signal database_batch_commit_failed| B
```

