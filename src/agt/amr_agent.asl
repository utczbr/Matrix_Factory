{ include("$jacamoJar/templates/common-cartago.asl") }
{ include("$jacamoJar/templates/common-moise.asl") }

// AMR Agent (Phase 2 + Phase 3)

!start.

+!start
  <-
     .my_name(Me);
     +my_name(Me); .print("AMR ", Me, " starting");
     +current_epoch(0).

// ROOT CAUSE FIX (double-dispatch after the atomic reserveTransport fix):
// order_holon.asl's request_transport now calls AMRArtifact.reserveTransport()
// itself, which already picks this AMR AND commits the job (startJob() or
// jobQueue, whichever applies) in one atomic call — that's precisely what
// closes the AMR-selection race (see order_holon.asl / AMRArtifact.java).
// This plan used to call requestTransport() again here, which — now that
// the job is already committed — would have looked "busy" and silently
// queued a second, duplicate copy of the exact same job behind itself.
// This plan is now purely local bookkeeping: record which order holon to
// notify on arrival/abort, and print for visibility.
+!transport(OrderId, From, To)[source(Sender)]
  : my_name(Me) & amr_id(AmrPhysicalId)
  <- .print("AMR ", Me, " transporting ", OrderId, " from ", From, " to ", To);
     !notify_grid_saturation(OrderId);
     +transporting(OrderId, Sender).

+amr_arrived(AmrPhysicalId, OrderId)
  : amr_id(AmrPhysicalId) & transporting(OrderId, Sender)
  <- -transporting(OrderId, Sender);
     .send(Sender, tell, transport_done(OrderId)).

// ROOT CAUSE FIX (repeated tell-messages silently swallowed): same class of
// bug as resource_holon.asl's accept_proposal/abort_current_operation and
// order_holon.asl's transport_done — abort_transport(OrderId)[source(Sender)]
// is the exact same literal every time the same order holon aborts this
// same AMR's transport for the same order, which is routine: reserveTransport's
// load-balancing frequently reassigns the same AMR to the same order's next
// retry, and each failed leg produces another identical abort_transport.
// Without retracting it, the second identical abort_transport for the same
// (OrderId, Sender) pair generates no event at all, in either branch below.
+abort_transport(OrderId)[source(Sender)]
  : transporting(OrderId, Sender) & my_name(Me) & amr_id(AmrPhysicalId)
  <- -abort_transport(OrderId)[source(Sender)];
     .drop_intention(transport(OrderId, _, _));
     cancelTimer(OrderId, Me);
     cancelTransport(AmrPhysicalId, OrderId)[artifact_name("amr_artifact"), wsp("factory_ws")];
     -transporting(OrderId, Sender);
     .print("Transport aborted for ", OrderId).

+abort_transport(OrderId)[source(Sender)]
  <- -abort_transport(OrderId)[source(Sender)].   // no matching in-flight transport — ignore

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
