# Order & Resource Holons — Contract-Net Bidding (Reference)

This document describes the holonic interaction patterns between **Order Holons** and **Resource Holons**, detailing the **Contract-Net Protocol** and bidding utility evaluation formulas.

---

## Holonic Roles & Responsibilities

1. **Order Holons (`order_holon.asl`):** Represent individual MEA/stack production batches. Responsible for negotiating task execution across manufacturing stations to minimize total completion time and energy cost.
2. **Resource Holons (`resource_holon.asl`):** Represent physical station machinery (Stations 1–5). Maintain local tool wear indicators, thermal states, and calculate cost bids.

---

## Contract-Net Bidding Sequence Flow

```mermaid
sequenceDiagram
    autonumber
    participant OH as Order Holon
    participant RH1 as Resource Holon 1 (Station A)
    participant RH2 as Resource Holon 2 (Station B)

    OH->>RH1: Call For Proposals (CFP: task_type, deadline, batch_size)
    OH->>RH2: Call For Proposals (CFP: task_type, deadline, batch_size)

    RH1->>RH1: Calculate Bid Cost B1 (Tool wear, Energy price)
    RH2->>RH2: Calculate Bid Cost B2 (Tool wear, Energy price)

    RH1-->>OH: Propose(Bid_1, Estimated_Time_1)
    RH2-->>OH: Propose(Bid_2, Estimated_Time_2)

    Note over OH: Evaluate bids: min(Utility = w1*Cost + w2*Time)
    OH->>RH1: Accept-Proposal(Contract_ID)
    OH->>RH2: Reject-Proposal(Contract_ID)

    RH1->>RH1: Reserve station capacity & execute physical step
    RH1-->>OH: Inform-Done(Quality_Metrics, Energy_Consumed)
```

---

## Bidding Utility Function

When receiving a Call for Proposals (CFP), a Resource Holon evaluates its bid cost $B_{\mathrm{res}}$ using:

$$B_{\mathrm{res}} = w_e \cdot E_{\mathrm{est}} \cdot P_{\mathrm{grid}} + w_w \cdot D_{\mathrm{wear}} + w_q \cdot (1 - Q_{\mathrm{historical}})$$

where:
* $E_{\mathrm{est}}$ is estimated energy consumption ($\mathrm{kWh}$).
* $P_{\mathrm{grid}}$ is current spot market energy price ($\$/\mathrm{kWh}$).
* $D_{\mathrm{wear}}$ is incremental tool wear or fracture risk (e.g., Archard wear or $C_{\mathrm{crit,NCL}}$ from Station 3).
* $Q_{\mathrm{historical}}$ is historical station quality metric yield $\in [0, 1]$.
* $w_e, w_w, w_q$ are weighting coefficients dynamically adjusted based on control topology (PROSA vs. ADACOR).

---

## Code Reference

* Order Holon: [`src/agt/order_holon.asl`](https://github.com/utczbr/Matrix_Factory/blob/main/src/agt/order_holon.asl)
* Resource Holon: [`src/agt/resource_holon.asl`](https://github.com/utczbr/Matrix_Factory/blob/main/src/agt/resource_holon.asl)
