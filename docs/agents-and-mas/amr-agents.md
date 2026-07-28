# AMR Fleet Agents & Logistics (Reference)

> **Implementation status note:** The state-machine `CHARGING` transitions and battery State of Charge (SoC) derating model detailed below represent design specifications for future work. Currently, `amr_agent.asl` and `AMRArtifact.java` handle dispatch, collision locking, and grid routing, but do not track battery depletion or perform charging cycles.

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
    IDLE -.-> CHARGING : SoC below 20% (Planned)
    CHARGING -.-> IDLE : SoC above 90% (Planned)
```

---

## Battery State of Charge (SoC) Derating Model (Design Specification)

Battery depletion during transport is specified to depend on payload mass $m_{\mathrm{load}}$ ($\mathrm{kg}$) and travel distance $d$ ($\mathrm{m}$):

$$\mathrm{SoC}_{t+1} = \mathrm{SoC}_t - \frac{\left( P_{\mathrm{idle}} + \mu_{\mathrm{roll}} (m_{\mathrm{robot}} + m_{\mathrm{load}}) g v_{\mathrm{amr}} \right) \cdot \Delta t}{E_{\mathrm{battery,max}}}$$

where:
* $m_{\mathrm{robot}} = 120\mathrm{kg}$.
* $v_{\mathrm{amr}} = 1.5\mathrm{m/s}$.
* $\mu_{\mathrm{roll}} = 0.015$ (rubber wheel on industrial epoxy floor).
* $E_{\mathrm{battery,max}} = 1.20\mathrm{kWh}$.

---

## Code Reference

* Agent Source File: [`src/agt/amr_agent.asl`](file:///home/stuart/Documentos/matrix_factory_twin/src/agt/amr_agent.asl)
* Java Artifact: [`src/main/java/factory/AMRArtifact.java`](file:///home/stuart/Documentos/matrix_factory_twin/src/main/java/factory/AMRArtifact.java)

