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
     // Simulate grid routing
     .wait(3000);
     .send(Sender, tell, transport_done(OrderId)).

// ── ADACOR Phase 1 Suspend / Resume ──────────────────────────────────────

+suspend_intention[source(supervisor)]
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
