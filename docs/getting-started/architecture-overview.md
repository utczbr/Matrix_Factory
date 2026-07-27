# Architecture Overview (Tutorial)

This document provides a conceptual introduction to the hybrid architecture of **Matrix Factory Twin**, showing how cognitive belief-desire-intention (BDI) agents interact with high-fidelity numerical physics solvers.

---

## The Dual-Layer Architecture

Matrix Factory Twin separates manufacturing execution into two distinct layers:

```mermaid
graph LR
    subgraph Cognitive Layer [Cognitive Control Layer]
        A[Jason BDI Agents] -->|Artifact Actions| B[CArtAgO Shared Environment]
        B -->|Percepts & Beliefs| A
    end

    subgraph Physical Layer [Physical Numerical Layer]
        C[Numba JIT Kernels] -->|ODE Integration| D[Station Models 1-5]
        D -->|Thermodynamics & Kinetics| C
    end

    Cognitive Layer <== gRPC mTLS IPC ==> Physical Layer
```

1. **Cognitive Layer (Java / JaCaMo):**
   - **Jason BDI Reasoning:** Agents reason over beliefs, desires, and plans.
   - **Holonic Control Architecture:** Dynamic switching between hierarchical PROSA (Product-Resource-Order-Staff Architecture) and heterarchical ADACOR (Adaptive Holonic Control Architecture).
   - **CArtAgO Artifacts:** Enforces environment encapsulation, SQLite persistence, and WebSocket telemetry broadcasting.

2. **Physical Layer (Python / Numba JIT):**
   - High-performance, Numba-compiled ODE/PDE integrators for non-linear kinetic, mechanical, and electro-chemical processes across 5 manufacturing stations.
   - Deterministic lock-stepped synchronization via Next Event Request (NER).

---

## Key Design Principles

* **Deterministic Lock-Stepped Synchronization:** Time step updates are strictly event-driven (NER) rather than tied to system wall-clock sleep intervals.
* **Loose Coupling via gRPC:** The physical engine runs as an independent daemon, allowing seamless scaling and multi-language interoperability.
* **Two-Phase Commit (2PC) Regime Switching:** Control topologies transition safely without lost agent messages or state corruption.
* **Empirical Parameter Traceability:** Every physical parameter is calibrated against peer-reviewed experimental literature.

---

## What to Read Next

* Check out [C4 System Context](../architecture/c4-system-context.md) for detailed structural boundaries.
* Learn about [Time Synchronization Engine](../architecture/time-sync-engine.md) to dive into lock-stepped NER mechanics.
