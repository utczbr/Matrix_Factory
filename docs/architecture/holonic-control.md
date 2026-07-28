# Holonic Control & Two-Phase Commit Switching (Explanation)

This document details the control theory behind **PROSA** and **ADACOR** holonic control architectures, and explains how `supervisor_agent.asl` dynamically switches between control topologies using a **Two-Phase Commit (2PC)** protocol.

---

## PROSA vs. ADACOR Control Theories

Matrix Factory Twin supports dual control paradigms for industrial manufacturing lines:

1. **PROSA (Product-Resource-Order-Staff Architecture):**
   - **Characteristics:** Hierarchical, predictable, optimized for steady-state throughput under nominal energy prices.
   - **Structure:** Order Holons delegate tasks down to Resource Holons strictly following static schedule trees created by Staff Holons.

2. **ADACOR (Adaptive Holonic Control Architecture):**
   - **Characteristics:** Heterarchical, decentralized, dynamically reconfigurable during energy price spikes, machine breakdowns, or buffer saturation.
   - **Structure:** Resource Holons gain autonomous decision authority, directly negotiating with Order Holons using local Contract-Net protocols.

---

## Two-Phase Commit (2PC) Transition Protocol

When external triggers occur (e.g., energy price exceeds threshold $P_{\text{grid}} > \$0.25/\text{kWh}$), the `supervisor_agent` coordinates a seamless transition from PROSA to ADACOR without message loss or state corruption:

```mermaid
sequenceDiagram
    autonumber
    participant Sup as Supervisor Agent (Coordinator)
    participant OH as Order Holons
    participant RH as Resource Holons
    participant DB as Database Artifact

    Note over Sup: Trigger: Energy Price Spike / Machine Fault
    rect rgb(240, 240, 255)
        Note over Sup, RH: Phase 0: Drain & Prepare
        Sup->>OH: Broadcast PREPARE_DRAIN
        OH->>OH: Complete in-flight task bids; block new bidding
        OH-->>Sup: DRAINED_ACK
    end

    rect rgb(255, 240, 240)
        Note over Sup, RH: Phase 1: Suspend & Commit Topology
        Sup->>RH: Broadcast SUSPEND_SCHEDULER
        RH->>RH: Freeze local state variables & queue buffers
        RH-->>Sup: SUSPENDED_ACK
        Sup->>DB: Log topology switch commit (PROSA to ADACOR)
        Sup->>OH: Broadcast COMMIT_SWITCH(ADACOR_MODE)
        Sup->>RH: Broadcast COMMIT_SWITCH(ADACOR_MODE)
    end

    Note over OH, RH: Resuming execution under heterarchical ADACOR rules
```

---

## State Transition Verification

The `supervisor_agent.asl` verifies the completion of Phase 0 before issuing Phase 1 commit commands:

1. **Drain Guarantee:** All pending Contract-Net tenders are finalized or aborted.
2. **Buffer Safety:** In-flight AMR transport orders reach safe staging areas before topology reconfiguration.
3. **Audit Logging:** Every commit event records system ticks, active batch IDs, and cost metrics to SQLite via `DatabaseArtifact`.
