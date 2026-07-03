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
  : my_name(Me) & amr_id(AmrPhysicalId)
  <- .print("AMR ", Me, " transporting ", OrderId, " from ", From, " to ", To);
     !notify_grid_saturation(OrderId);
     requestTransport(AmrPhysicalId, From, To, OrderId)[artifact_name("amr_artifact")];
     +transporting(OrderId, Sender).

+amr_arrived(AmrPhysicalId, OrderId)
  : amr_id(AmrPhysicalId) & transporting(OrderId, Sender)
  <- -transporting(OrderId, Sender);
     .send(Sender, tell, transport_done(OrderId)).

+abort_transport(OrderId)[source(Sender)]
  : transporting(OrderId, Sender) & my_name(Me) & amr_id(AmrPhysicalId)
  <- .drop_intention(transport(OrderId, _, _));
     cancelTimer(OrderId, Me);
     cancelTransport(AmrPhysicalId, OrderId)[artifact_name("amr_artifact")];
     -transporting(OrderId, Sender);
     .print("Transport aborted for ", OrderId).

+abort_transport(OrderId)[source(Sender)]
  <- true.   // no matching in-flight transport — ignore

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

+timer_expired(OrderId, _)
  <- true.
