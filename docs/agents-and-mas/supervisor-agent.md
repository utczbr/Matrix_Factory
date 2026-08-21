# Supervisor Agent & Closed-Loop Control Coordinator (Reference)

This document presents belief structures, plan rules, and state machine specifications for `supervisor_agent.asl`.

---

## Agent Overview

The `supervisor_agent` acts as the central coordinator in Matrix Factory Twin. It monitors overall plant performance, grid energy spot prices, buffer capacities, closed-loop station defect drift rates, and coordinates the Two-Phase Commit (2PC) protocol during control regime switching (PROSA $\leftrightarrow$ ADACOR).

---

## Closed-Loop Station Defect Monitoring & Setpoint Control

The supervisor periodically queries recent defect rates across Stations 1–4 via `DatabaseArtifact.getRecentDefectRate(StationId, WindowSize, Rate)` and issues corrective setpoint adjustments to resource holons when drift exceeds quality thresholds:

```jason
+!monitor_defect_drift
  : true
  <- for ( .member(Station, ["S1","S2","S3","S4"]) ) {
        getRecentDefectRate(Station, 20, Rate);
        if (Rate > 0.30) {
            compute_corrective_setpoint(Station, Param, Value);
            .send(Station, tell, adjust_setpoint(Param, Value));
        }
     }.
```

---

## Belief Rules & Initial State

```jason
/* Initial Beliefs */
active_schema(prosa).
adacor_enabled(true).
suspended_holons([]).

/* Dynamic Belief Rules */
prosa_mode_active     :- active_schema(prosa).
adacor_mode_active    :- active_schema(adacor).
```

---

## Goal Transitions & Plan Logic

### 1. Triggering Control Regime Transition

When `EnergyPriceArtifact` detects a price exceeding $150.0\text{ EUR/MWh}$, it signals `+energy_price_spike(Price)`:

```jason
+energy_price_spike(Price)
  : active_schema(prosa) & not pending_transition(_, _) & adacor_enabled(true)
  <- .print("Energy spike: ", Price, " EUR/MWh — initiating ADACOR transition");
     getSimTime(SimT);
     initiateTransition("adacor", SimT, ReservedEpoch);
     +pending_transition(adacor, ReservedEpoch);
     !run_phase0.

+!initiate_2pc_switch(TargetMode)
   <- .broadcast(achieve, prepare_drain);
      +switch_in_progress(TargetMode);
      .concat("Phase 0 Drain started for ", TargetMode, LogMsg);
      log_event("SUPERVISOR", "2PC_PHASE_0", LogMsg).
```

### 2. Phase 0 Drain Acknowledgment & Phase 1 Commit

```jason
+drained_ack(AgentId) : switch_in_progress(TargetMode)
   <- ?active_holons(N);
      ?drain_phase_completed(K);
      -+drain_phase_completed(K + 1);
      !check_phase0_completion(TargetMode).

+!check_phase0_completion(TargetMode) : drain_phase_completed(K) & active_holons(N) & K >= N
   <- .print("Phase 0 Drain complete across all holons. Executing Phase 1 Commit.");
      .broadcast(tell, suspend_scheduler);
      -+control_mode(TargetMode);
      -switch_in_progress(_);
      -+drain_phase_completed(0);
      .broadcast(tell, resume_scheduler(TargetMode));
      log_event("SUPERVISOR", "2PC_PHASE_1_COMMIT", TargetMode).
```

---

## Code Reference

* Agent Source File: [`src/agt/supervisor_agent.asl`](file:///home/stuart/Documentos/matrix_factory_twin/src/agt/supervisor_agent.asl)
