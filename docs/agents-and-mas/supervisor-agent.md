# Supervisor Agent & 2PC Coordinator (Reference)

This document presents belief structures, plan rules, and state machine specifications for `supervisor_agent.asl`.

---

## Agent Overview

The `supervisor_agent` acts as the central coordinator in Matrix Factory Twin. It monitors overall plant performance, grid energy spot prices, buffer capacities, and coordinates the Two-Phase Commit (2PC) protocol during control regime switching (PROSA $\leftrightarrow$ ADACOR).

---

## Belief Rules & Initial State

```jason
/* Initial Beliefs */
control_mode("prosa").
energy_price_threshold(0.25). // $/kWh
drain_phase_completed(0).
active_holons(0).

/* Dynamic Belief Rules */
energy_spike_detected :- energy_price(P) & energy_price_threshold(T) & P > T.
prosa_mode_active     :- control_mode("prosa").
adacor_mode_active    :- control_mode("adacor").
```

---

## Goal Transitions & Plan Logic

### 1. Triggering Control Regime Transition

```jason
+energy_price(P) : energy_spike_detected & prosa_mode_active
   <- .print("Energy price spike detected (", P, " $/kWh). Initiating 2PC switch to ADACOR.");
      !initiate_2pc_switch("adacor").

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
