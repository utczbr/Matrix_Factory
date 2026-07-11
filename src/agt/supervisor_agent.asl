{ include("$jacamoJar/templates/common-cartago.asl") }
{ include("$jacamoJar/templates/common-moise.asl") }

// ── Initialization ──────────────────────────────────────────────────────

!start.

+!start
  <- .print("Supervisor agent started");
     +active_schema(prosa);
     +suspended_holons([]);
     !register_active_holons.

+!register_active_holons
  <- +active_order_holons([order_1, order_2, order_3, order_4, order_5]);
     +active_resource_holons([station_1, station_2, station_3, station_4, station_5]);
     +active_transport_holons([amr_1, amr_2]);
     // NEW — pairs each transport-holon agent name with the physical AMR id
     // AMRArtifact knows it by (factory.jcm: amr_1 carries amr_id("AMR-1"),
     // amr_2 carries amr_id("AMR-2")). order_holon.asl's load-aware AMR
     // selection needs both halves of this pairing to turn
     // AMRArtifact.getFleetStatus()'s per-physical-AMR load figures back
     // into an agent name it can actually .send() an achieve-goal to.
     +amr_physical_ids([amr(amr_1, "AMR-1"), amr(amr_2, "AMR-2")]).

// ── Energy Price Disturbance — ADACOR Trigger ────────────────────────────

+energy_price(P)
  <- .print("Energy price is now: ", P).

+energy_price_spike(Price)
  : active_schema(prosa) & not pending_transition(_, _)
  <- .print("Energy spike: ", Price, " EUR/MWh — initiating ADACOR transition");
     getSimTime(SimT);                                   // Synchronous @OPERATION query
     initiateTransition("adacor", SimT, ReservedEpoch);
     +pending_transition(adacor, ReservedEpoch);
     !run_phase0.

+energy_price_spike(P)
  <- .print("FALLBACK CATCH: Energy spike event received: ", P);
     ?active_schema(S);
     .print("Current active schema is: ", S).

+energy_price_normal(Price)
  : active_schema(adacor) & not pending_transition(_, _)
  <- .print("Energy normal: ", Price, " EUR/MWh — reverting to PROSA");
     !revert_to_prosa(Price).

+energy_price_normal(Price)
  : pending_transition(adacor, _)
  <- .print("Energy normal received while transitioning to ADACOR. Reverting after commit.");
     +pending_revert(Price).

+!revert_to_prosa(Price)
  <- getSimTime(SimT);
     initiateTransition("prosa", SimT, ReservedEpoch);
     +pending_transition(prosa, ReservedEpoch);
     !run_phase0.

// ── Two-Phase Commit: Phase 0 (Drain Active Negotiations) ────────────────

+!run_phase0
  <- .print("Phase0 DRAIN begin — TTL_phase0=15000ms simulated");
     startTimer("phase0_transition", 15000, self);
     !await_phase0_drain.

+!await_phase0_drain
  <- getActiveLocks(LocksStr);
     .term2string(Locks, LocksStr);
     if (Locks == []) {
         cancelTimer("phase0_transition");
         .print("Phase0: all negotiations drained — advancing to Phase1");
         !run_phase1;
     } else {
         startTimer("phase0_poll", 500, self);
     }.

+timer_expired("phase0_poll", _)
  <- !await_phase0_drain.

// Phase 0 TTL expired — compensating abort for all active locks.
// The supervisor iterates the registry directly and sends to each pair.
// No Java broadcast helper is used: .send() in Jason is the correct mechanism.
+timer_expired("phase0_transition", _)
  <- .print("Phase0 TTL expired — executing compensating abort");
     getActiveLocks(LocksStr);
     .term2string(Locks, LocksStr);
     !abort_all_locks(Locks);
     !run_phase1.

+!abort_all_locks([]).
+!abort_all_locks([lock(OrderId, StationName, OrderHolonName)|Rest])
  <- // Send to the Resource Holon: revokes provisional_lock if still held
     .send(StationName,    tell, abort_current_operation(OrderId));
     // Send to the Order Holon: drops awaiting intentions
     .send(OrderHolonName, tell, abort_current_operation(OrderId));
     recordEvent(OrderId, "ABORTED")[artifact_name("database"), wsp("factory_ws")];
     !abort_all_locks(Rest).

// ── Two-Phase Commit: Phase 1 (Suspend with Timeout) ────────────────────

+!run_phase1
  <- .print("Phase1 SUSPEND begin — TTL_phase1=10000ms simulated");
     ?active_order_holons(Orders);
     ?active_resource_holons(Stations);
     ?active_transport_holons(AMRs);
     .concat(Orders, Stations, All0);
     .concat(All0, AMRs, AllHolons);
     -+suspended_holons(AllHolons);
     // Send suspend_intentions individually via .send() — no broadcast helper.
     !send_suspend_to_all(AllHolons);
     startTimer("phase1_transition", 10000, self);
     !await_phase1_acks(AllHolons).

+!send_suspend_to_all([]).
+!send_suspend_to_all([H|Rest])
  <- .send(H, tell, suspend_intentions);
     !send_suspend_to_all(Rest).

+!await_phase1_acks([])
  <- cancelTimer("phase1_transition");
     .print("Phase1: unanimous ACK — clean commit");
     !do_commit.

+!await_phase1_acks(Pending)
  : Pending \== []
  <- .wait(suspend_ack(Who)[source(_)]);
     .delete(Who, Pending, NewPending);
     !await_phase1_acks(NewPending).

+timer_expired("phase1_transition", _)
  <- .print("Phase1 TTL expired — issuing force_commit decree");
     .drop_intention(await_phase1_acks(_));
     !do_commit.

// ── Commit ───────────────────────────────────────────────────────────────

+!do_commit
  : pending_transition(TargetSchema, Epoch)
  <- getSimTime(SimT);
     commitTransition(SimT);
     -+active_schema(TargetSchema);
     -pending_transition(TargetSchema, Epoch);
     .print("Schema committed: ", TargetSchema, " epoch=", Epoch);
     if (pending_revert(P)) {
         -pending_revert(P);
         .print("Executing pending revert to prosa!");
         !revert_to_prosa(P);
     }.

// ── AMR Grid Saturation: Deadlock Resolution (PROSA mode) ────────────────

+transport_blocked(BatchId)[source(_)]
  : active_schema(prosa)
  <- getGridUtilization(Util);
     if (Util > 0.85) {
         .print("Grid saturated (", Util, ") — suspending low-priority Order Holons");
         !suspend_low_priority_holons;
         clearExpiredReservations;
     }.

// Identify Order Holons with NO active lock — lowest priority for suspension.
//
// getActiveLocks returns: [lock(OrderId, StationName, OrderHolonName), ...]
// Orders is a list of agent name atoms: [order_1, order_2, ...]
//
// The filter checks the THIRD element of each lock term (OrderHolonName atom)
// against the agent names in Orders. This is now type-correct because the
// registry explicitly stores the order holon agent name, not the UUID.
+!suspend_low_priority_holons
  <- ?active_order_holons(Orders);
     getActiveLocks(LocksStr);
     .term2string(Locks, LocksStr);
     .findall(O,
         (.member(O, Orders) & not .member(lock(_, _, O), Locks)),
         LowPri);
     -+suspended_holons(LowPri);
     !send_suspend_to_all(LowPri).

// Resume suspended holons when grid utilization falls below 0.60.
// Symmetric: un-suspends exactly the holons stored in suspended_holons.
+!check_grid_resume
  : suspended_holons(Suspended) & Suspended \== []
  <- getGridUtilization(Util);
     if (Util < 0.60) {
         .print("Grid normal (", Util, ") — resuming suspended holons");
         !resume_suspended_holons;
     }.

+!resume_suspended_holons
  : suspended_holons(Suspended)
  <- for ( .member(H, Suspended) ) {
         .send(H, tell, resume_intention);
     };
     -+suspended_holons([]).
