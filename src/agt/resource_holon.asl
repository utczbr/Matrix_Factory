{ include("$jacamoJar/templates/common-cartago.asl") }
{ include("$jacamoJar/templates/common-moise.asl") }

// Resource Holon (Phase 2 + Phase 3)

!start.

+!start
  <-
     .my_name(Me);
     +my_name(Me); .print("Resource Holon ", Me, " starting");
     -+station_state(idle);
     +current_epoch(0);
     +my_station(Me).

// ── CNP Reservation State-Machine (Phase 2) ──────────────────────────────

// Plan: Respond to CFP with transactional reservation
+!call_for_proposal(Step, Stations, OrderId)[source(Sender)]
   : my_name(Me) & .member(Me, Stations) & station_state(idle) & my_recipe_step(Step)
   <- -+station_state(provisional_lock(OrderId)); 
      ?current_processing_cost(Cost);
      claimStation(OrderId, _);
      .send(Sender, tell, propose(Me, Cost));
      if (test_hook_ttl(TTL)[artifact_name("supervisor_artifact"), wsp("factory_ws")]) {
          startTimer(OrderId, TTL, Me);
      } else {
          startTimer(OrderId, 5000, Me);  // Discrete-event NER Timer
      }.

+!call_for_proposal(Step, Stations, OrderId)[source(Sender)]
   : my_name(Me) & .member(Me, Stations) & station_state(idle) & not my_recipe_step(Step)
   <- .send(Sender, tell, refuse(Me, "step_mismatch")).

+!call_for_proposal(Step, Stations, OrderId)[source(Sender)]
   : my_name(Me) & .member(Me, Stations) & not station_state(idle)
   <- .send(Sender, tell, refuse(Me, "station_busy")).

-!call_for_proposal(Step, Stations, OrderId)[source(Sender)]
   <- ?my_name(Me);
      if (station_state(provisional_lock(OrderId))) {
          releaseStation(OrderId);
          -+station_state(idle);
      };
      .print("CFP execution failed (artifact error?), sending refuse for ", OrderId);
      .send(Sender, tell, refuse(Me)).

// Phase 3 Amended accept_proposal plan
+accept_proposal(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId)) & my_name(Me) & my_recipe_step(Step)
  <- cancelTimer(OrderId, Me);
     registerLock(OrderId, Me, Sender);
     +active_order(OrderId, Sender, Step);      // NEW — remember who + what step
     .print("Accepted proposal for ", OrderId, ", waiting for item to arrive").

+item_arrived(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId)) & my_name(Me) & active_order(OrderId, Sender, Step)
  <- -+station_state(busy_processing(OrderId));
     .send(Sender, tell, inform_start(Me));
     !execute_physical_operation(OrderId).

// Plan: Catch-all rejection for delayed accept_proposal (superseded lock)
+accept_proposal(OrderId)[source(Sender)]
   : not station_state(provisional_lock(OrderId)) & my_name(Me)
   <- .send(Sender, tell, reject_proposal(Me, "lock_expired_or_superseded")).

// Phase 3 Amended reject_proposal plan
+reject_proposal(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId)) & my_name(Me)
  <- -+station_state(idle); // Update Jason synchronously before external action
     cancelTimer(OrderId, Me);
     releaseStation(OrderId); // Sync artifact volatile field
     .print("Proposal rejected for order ", OrderId, " (CNP lost), reverting to idle").

+reject_proposal(OrderId)[source(Sender)]
  : not station_state(provisional_lock(OrderId)) & my_name(Me)
  <- true.

// Phase 3 Amended execute_physical_operation plan
+!execute_physical_operation(OrderId)
  : station_state(busy_processing(OrderId)) & my_station(SId) & active_order(OrderId, OrderHolon, Step)
  <- processOrder(OrderId, ResultCode);
     releaseLock(OrderId);
     -active_order(OrderId, OrderHolon, Step);
     if (ResultCode == "defect") {
         releaseStation(OrderId);
         -+station_state(idle);
         .send(OrderHolon, tell, step_failed(OrderId, Step, "defect"));  // NEW
         !report_defect(OrderId);
     } else {
         -+station_state(idle);
         .send(OrderHolon, tell, step_complete(OrderId, Step));         // NEW
     }.

+!report_defect(OrderId)
  <- .print("Defect detected for order ", OrderId).

// Phase 3 Amended timer_expired plan
// Station reverts from provisional_lock on TTL expiry.
// releaseStation() is required to sync the Java artifact's volatile currentSummary
// field with the Jason belief revert. Without it, the dashboard reads
// STATION_PROVISIONAL_LOCK indefinitely after the timer fires.
+timer_expired(OrderId, Me)
  : station_state(provisional_lock(OrderId)) & my_name(Me)
  <- -+station_state(idle);
     releaseStation(OrderId);   // Sync artifact volatile field
     // releaseLock is a no-op here: lock is only registered on accept_proposal,
     // which has not yet arrived when the TTL fires (station still in provisional_lock).
     // Calling it anyway is safe (ConcurrentHashMap.remove on absent key is a no-op).
     releaseLock(OrderId);
     .print("Provisional lock expired for order ", OrderId).

+timer_expired(OrderId, _)
  <- true.

// ── Phase 0 Compensating Abort ────────────────────────────────────────────

// Identity guard (doc3 §3.1): fires only if this station holds the lock.
// Prevents corrupting a newer lock if the station naturally reverted first.
+abort_current_operation(OrderId)
  : station_state(provisional_lock(OrderId))
  <- -+station_state(idle);
     releaseStation(OrderId);   // Sync artifact volatile field — dashboard sees IDLE
     releaseLock(OrderId);      // No-op (lock not yet registered); safe to call
     .print("ADACOR Phase0 abort: provisional_lock revoked for ", OrderId).

// Lock already gone (natural revert or different order) — discard abort silently.
+abort_current_operation(OrderId)
  : not station_state(provisional_lock(OrderId))
  <- true.

// ── Phase 1 Suspend ───────────────────────────────────────────────────────

// Resource Holons drop only operations they can actually hold.
// .drop_intention(call_for_proposals) is NOT included: Resource Holons
// respond to CFPs — they never initiate them. That intention belongs to order_holon.asl.
+suspend_intentions[source(supervisor)]
  <- .drop_intention(execute_physical_operation(_));
     -+station_state(offline);
     setStationOffline; // Push offline state to the dashboard
     ?my_name(Me);
     if ((test_hook_block_ack_from(BlockMe)[artifact_name("supervisor_artifact"), wsp("factory_ws")] & Me == BlockMe) |
         (test_hook_inject_epoch_mismatch(BlockMe)[artifact_name("supervisor_artifact"), wsp("factory_ws")] & Me == BlockMe)) {
         .print("Test Hook: Blocking ACK from ", Me);
     } else {
         .send(supervisor, tell, suspend_ack(Me));
     };
     .print("Station ", Me, " suspended by ADACOR Phase1").

+resume_intention[source(supervisor)]
  <- !start.

// ── Schema Epoch Validation ───────────────────────────────────────────────

// schema_epoch(E) is published by UtilitySystemArtifact as an observable property
// (updated once per tick alongside h2_pressure_bar etc.).
// Resource Holons hold the epoch in a belief; any change triggers reinitialize.
+schema_epoch(E)[artifact_name("utility_system")]
  : current_epoch(OldE) & E \== OldE
  <- .print("Epoch mismatch: ", OldE, " → ", E, " — reinitializing schema binding");
     -current_epoch(OldE);
     +current_epoch(E);
     !reinitialize_schema.

+!reinitialize_schema
  <- .drop_all_intentions;
     ?station_state(State);
     if (State == provisional_lock(OrderId) | State == busy_processing(OrderId)) {
         releaseStation(OrderId); // Syncs the artifact so dashboard sees IDLE
     }
     -+station_state(idle);
     !start.
