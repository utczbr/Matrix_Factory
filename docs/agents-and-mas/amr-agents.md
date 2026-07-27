# AMR Fleet Agents & Logistics (Reference)

This document describes the dispatch, path routing, battery state-of-charge (SoC) modeling, and material movement logic of **Autonomous Mobile Robot (AMR)** fleet agents (`amr_agent.asl`).

---

## Agent Role & Transport Logistics

AMR Fleet Agents handle intralogistics transport of in-process MEAs, bipolar plate stacks, and finished fuel cell units between buffer storage racks and station processing cells (Stations 1 $\rightarrow$ 5).

---

## State Machine & Motion Dynamics

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> DISPATCHED : Transport Order Assigned
    DISPATCHED --> MOVING_TO_PICKUP : Path Calculated
    MOVING_TO_PICKUP --> LOADING : Arrived at Source Buffer
    LOADING --> MOVING_TO_DROP : Material Loaded
    MOVING_TO_DROP --> UNLOADING : Arrived at Destination Station
    UNLOADING --> IDLE : Material Transferred
    IDLE --> CHARGING : SoC < 20%
    CHARGING --> IDLE : SoC > 90%
```

---

## Battery State of Charge (SoC) Derating Model

Battery depletion during transport depends on payload mass $m_{\text{load}}$ ($\text{kg}$) and travel distance $d$ ($\text{m}$):

$$\text{SoC}_{t+1} = \text{SoC}_t - \frac{\left( P_{\text{idle}} + \mu_{\text{roll}} (m_{\text{robot}} + m_{\text{load}}) g v_{\text{amr}} \right) \cdot \Delta t}{E_{\text{battery,max}}}$$

where:
* $m_{\text{robot}} = 120\text{ kg}$.
* $v_{\text{amr}} = 1.5\text{ m/s}$.
* $\mu_{\text{roll}} = 0.015$ (rubber wheel on industrial epoxy floor).
* $E_{\text{battery,max}} = 1.20\text{ kWh}$.

---

## Code Reference

* Agent Source File: [`src/agt/amr_agent.asl`](file:///home/stuart/Documentos/matrix_factory_twin/src/agt/amr_agent.asl)
