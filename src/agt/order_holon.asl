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
  <- .wait(2000);
     .random(R);
     .concat("ORD-", Me, "-", R, OrderId);
     +my_order_id(OrderId);
     .print("Spawning order: ", OrderId);
     !request_transport(OrderId, start, station_1).

+!request_transport(OrderId, From, To)
  <- .print("Requesting transport for ", OrderId, " to ", To);
     .send(amr_1, achieve, transport(OrderId, From, To)).

+transport_done(OrderId)[source(Amr)]
  <- .print("Transport done for ", OrderId);
     !call_for_proposals(1, [station_1, station_2, station_3, station_4, station_5], OrderId).

+transport_blocked(OrderId)[source(Amr)]
  <- .print("Transport blocked for ", OrderId, " - signaling supervisor");
     .send(supervisor, tell, transport_blocked(OrderId)).

+!call_for_proposals(Step, Stations, OrderId)
  <- .print("Initiating CNP for ", OrderId);
     .send(Stations, achieve, call_for_proposal(Step, Stations, OrderId));
     // Wait for proposals then select one
     .wait(3000);
     !select_proposal(Step, Stations, OrderId).

+!select_proposal(Step, Stations, OrderId)
  : propose(Winner, Cost)[source(Winner)]
  <- .print("Selected ", Winner, " for ", OrderId, " with cost ", Cost);
     .send(Winner, tell, accept_proposal(OrderId));
     for ( propose(Loser, _)[source(Loser)] ) {
         if (Loser \== Winner) {
             .send(Loser, tell, reject_proposal(OrderId));
         }
     }
     .abolish(propose(_, _));
     .abolish(refuse(_));
     !await_station_start(OrderId, Winner).

+!select_proposal(Step, Stations, OrderId)
  <- .print("No proposals received for ", OrderId, " - retrying CNP");
     .abolish(propose(_, _));
     .abolish(refuse(_));
     .wait(1000);
     !call_for_proposals(Step, Stations, OrderId).

+!await_station_start(OrderId, Station)
  <- .wait(inform_start(Station)[source(Station)], 10000, TimedOut);
     if (TimedOut >= 10000) {
          .print("Failed to get inform_start from ", Station, " - retrying CNP");
          !call_for_proposals(1, [station_1, station_2, station_3, station_4, station_5], OrderId);
      } else {
          .print("Station ", Station, " started processing ", OrderId);
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
