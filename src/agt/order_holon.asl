{ include("$jacamoJar/templates/common-cartago.asl") }
{ include("$jacamoJar/templates/common-moise.asl") }

// Order Holon (Phase 2 + Phase 3)

!start.

+!start
  <-
     .my_name(Me);
     +my_name(Me); .print("Order Holon ", Me, " starting");
     +current_epoch(0);
     !request_next_batch.

+!request_next_batch
  : my_name(Me)
  <- .print("Requesting next batch... Me=", Me);
     startTimer("batch_wait", 2000, Me).

+timer_expired("batch_wait", Me)
  : my_name(Me)
  <- .random(R);
     .concat("ORD-", Me, "-", R, OrderId);
     +my_order_id(OrderId);
     +order_random(OrderId, R);
     +recipe_remaining(OrderId, [2,3]);          // NEW — steps left after step 1
     .print("Spawning order: ", OrderId);
     !call_for_proposals(1, [station_1, station_2, station_3, station_4, station_5], OrderId).

+!request_transport(OrderId, From, To)
  <- .send(supervisor, askOne, active_transport_holons(Amrs), active_transport_holons(Amrs));
     .length(Amrs, N);
     .my_name(Me);
     ?order_random(OrderId, R);
     I = math.round(R * 10000) mod N;
     .nth(I, Amrs, Amr);
     -+dispatched_amr(OrderId, Amr);                        // NEW (overwrite)
     .print("Requesting transport for ", OrderId, " to ", To, " via ", Amr);
     .send(Amr, achieve, transport(OrderId, From, To)).

+transport_done(OrderId)[source(Amr)]
  <- .print("Transport done for ", OrderId).

+transport_blocked(OrderId)[source(Amr)]
  <- .print("Transport blocked for ", OrderId, " - signaling supervisor");
     .send(supervisor, tell, transport_blocked(OrderId)).

+step_complete(OrderId, Step)[source(Station)]
  : recipe_remaining(OrderId, Remaining)
  <- .print("Step ", Step, " complete for ", OrderId, " at ", Station);
     if (Remaining == []) {
         .print("Order ", OrderId, " fully complete");
         -recipe_remaining(OrderId, Remaining);
     } else {
         .nth(0, Remaining, NextStep);
         .delete(0, Remaining, Rest);
         -+recipe_remaining(OrderId, Rest);
         !call_for_proposals(NextStep, [station_1,station_2,station_3,station_4,station_5], OrderId);
     }.

+step_failed(OrderId, Step, Reason)[source(Station)]
  <- .print("Step ", Step, " failed for ", OrderId, " (", Reason, ") — retrying same step");
     !call_for_proposals(Step, [station_1,station_2,station_3,station_4,station_5], OrderId).

+!call_for_proposals(Step, Stations, OrderId)
  : my_name(Me)
  <- .print("Initiating CNP for ", OrderId);
     .send(Stations, achieve, call_for_proposal(Step, Stations, OrderId));
     +cnp_state(OrderId, Step, Stations);
     startTimer(OrderId, 3000, Me).

+timer_expired(OrderId, Me)
  : cnp_state(OrderId, Step, Stations) & my_name(Me)
  <- -cnp_state(OrderId, Step, Stations);
     !select_proposal(Step, Stations, OrderId).

+!select_proposal(Step, Stations, OrderId)
  : .findall(cost(C,W), propose(W,C)[source(W)], L) & L \== []
  <- .min(L, cost(BestCost,Winner));
     .print("Selected ", Winner, " for ", OrderId, " with cost ", BestCost);
     if (test_hook_cnp_slow_accept(true)[artifact_name("supervisor_artifact")]) {
         .print("Test Hook: CNP slow accept — waiting to simulate delay");
         startTimer(OrderId, 3000, Me);
     } else {
         !finish_select_proposal(OrderId, Winner);
     }.

+timer_expired(OrderId, Me)
  : propose(Winner, Cost)[source(Winner)] & test_hook_cnp_slow_accept(true)[artifact_name("supervisor_artifact")] & my_name(Me)
  <- !finish_select_proposal(OrderId, Winner).

+!finish_select_proposal(OrderId, Winner)
  <- .send(Winner, tell, accept_proposal(OrderId));
     for ( propose(Loser, _) ) {
         if (Loser \== Winner) {
             .send(Loser, tell, reject_proposal(OrderId));
         }
     }
     .abolish(propose(_, _));
     .abolish(refuse(_));
     !request_transport(OrderId, start, Winner);
     !await_station_start(OrderId, Winner).

+!select_proposal(Step, Stations, OrderId)
  <- .print("No proposals received for ", OrderId, " - retrying CNP");
     .abolish(propose(_, _));
     .abolish(refuse(_));
     .wait(1000);
     !call_for_proposals(Step, Stations, OrderId).

+!await_station_start(OrderId, Station)
  <- .my_name(Me);
     .concat(OrderId, "_await", AwaitKey);
     startTimer(AwaitKey, 10000, Me);
     .wait(inform_start(Station)[source(Station)] | timer_expired(AwaitKey, _), 15000, _);
     if (inform_start(Station)[source(Station)]) {
         cancelTimer(AwaitKey, Me);
         .print("Station ", Station, " started processing ", OrderId);
     } else {
         .print("Failed to get inform_start from ", Station, " - retrying CNP");
         ?dispatched_amr(OrderId, Amr);
         .send(Amr, tell, abort_transport(OrderId));
         !call_for_proposals(1, [station_1,station_2,station_3,station_4,station_5], OrderId);
     }.

// ── ADACOR Phase 0 Compensating Abort ────────────────────────────────────

+abort_current_operation(OrderId)
  : my_order_id(OrderId)
  <- .drop_intention(await_station_start(OrderId, _));
     .drop_intention(request_transport(OrderId, _, _));
     .print("ADACOR Phase0 abort: Order Holon dropping intentions for ", OrderId);
     !request_next_batch.

+abort_current_operation(_)   // Different order — ignore
  <- true.

// ── ADACOR Phase 1 Suspend / Resume ──────────────────────────────────────

// Correct placement: Order Holons DO initiate call_for_proposals.
+suspend_intention[source(supervisor)]
  : my_name(Me)
  <- .drop_intention(request_next_batch);
     .drop_intention(call_for_proposals(_, _, _));     // Order Holons initiate CFPs
     .drop_intention(await_station_start(_, _));
     .drop_intention(request_transport(_, _, _));
     .send(supervisor, tell, suspend_ack(Me));
     .print("Order Holon ", Me, " suspended by ADACOR Phase1").

+resume_intention[source(supervisor)]
  <- !start.

// ── Schema Epoch Validation ───────────────────────────────────────────────

+schema_epoch(E)[artifact_name("utility_system")]
  : current_epoch(OldE) & E \== OldE
  <- -current_epoch(OldE);
     +current_epoch(E);
     .print("Order Holon epoch: ", OldE, " → ", E);
     !reinitialize_schema.

+!reinitialize_schema
  <- .drop_all_intentions;
     !request_next_batch.
