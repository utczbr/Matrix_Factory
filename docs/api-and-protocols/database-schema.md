# Database Schema & Asynchronous Queue (Reference)

This document presents the relational database schema, SQLite Write-Ahead Logging (WAL) configuration, and non-blocking asynchronous writer queue implemented in `DatabaseArtifact.java`.

---

## SQLite WAL Mode & Performance Tuning

Matrix Factory Twin utilizes SQLite with Write-Ahead Logging (`WAL`) mode:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 30000000000;
```

This configuration permits non-blocking concurrent reads while `DatabaseArtifact.java` flushes telemetry and bidding logs asynchronously.

---

## Entity-Relationship Schema

```mermaid
erDiagram
    FACTORY_RUNS ||--o{ STATION_EVENTS : contains
    FACTORY_RUNS ||--o{ HOLON_BIDS : contains
    FACTORY_RUNS ||--o{ TOPOLOGY_SWITCHES : logs

    FACTORY_RUNS {
        text run_id PK
        integer seed
        text initial_topology
        integer max_ticks
        text created_at
    }

    STATION_EVENTS {
        integer event_id PK
        text run_id FK
        integer tick
        text station_id
        text state_json
        real execution_time_ms
    }

    HOLON_BIDS {
        integer bid_id PK
        text run_id FK
        integer tick
        text order_id
        text resource_id
        real bid_cost
        text status
    }

    TOPOLOGY_SWITCHES {
        integer switch_id PK
        text run_id FK
        integer tick
        text source_mode
        text target_mode
        text reason
    }
```

---

## Asynchronous Batch Queue Architecture

To prevent disk I/O bottlenecks from stalling the agent execution loop, `DatabaseArtifact.java` utilizes a `BlockingQueue<LogEntry>` with a dedicated background consumer thread:

```mermaid
graph LR
    A[CArtAgO Operation Thread] -->|log_event non-blocking offer| B[ConcurrentLinkedQueue]
    B -->|Batch Drain every 100ms or 50 items| C[Background Writer Thread]
    C -->|Execute Batch Statement| D[factory_history.db SQLite WAL]
```
