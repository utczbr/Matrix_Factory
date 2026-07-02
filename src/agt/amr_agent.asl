{ include("$jacamoJar/templates/common-cartago.asl") }
{ include("$jacamoJar/templates/common-moise.asl") }

// AMR Agent (Phase 2 + Phase 3)

!start.

+!start
  <-
     .my_name(Me);
     +my_name(Me); .print("AMR ", Me, " starting");
     +current_epoch(0).

+!transport(OrderId, From, To)[source(Sender)]
  : my_name(Me)
  <- .print("AMR ", Me, " transporting ", OrderId, " from ", From, " to ", To);
     !notify_grid_saturation(OrderId);
     // Simulate grid routing
     +transporting(OrderId, Sender);
     startTimer(OrderId, 3000, Me).

+timer_expired(OrderId, Me)
  : transporting(OrderId, Sender)
  <- -transporting(OrderId, Sender);
     .send(Sender, tell, transport_done(OrderId)).

+!notify_grid_saturation(OrderId)
  <- getGridUtilization(Util);
     if (Util > 0.85) {
         .print("Grid saturation detected (", Util, ") - signaling transport_blocked for ", OrderId);
         .send(supervisor, tell, transport_blocked(OrderId));
     }.

// ── ADACOR Phase 1 Suspend / Resume ──────────────────────────────────────

+suspend_intentions[source(supervisor)]
  : my_name(Me)
  <- .drop_intention(transport(_, _, _));
     .send(supervisor, tell, suspend_ack(Me));
     .print("AMR ", Me, " suspended by ADACOR Phase1").

+resume_intention[source(supervisor)]
  <- !start.

// ── Schema Epoch Validation ───────────────────────────────────────────────

+schema_epoch(E)[artifact_name("utility_system")]
  : current_epoch(OldE) & E \== OldE
  <- -current_epoch(OldE);
     +current_epoch(E);
     .print("AMR epoch: ", OldE, " → ", E);
     !reinitialize_schema.

+!reinitialize_schema
  <- .drop_all_intentions;
     !start.
