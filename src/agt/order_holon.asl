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
     +current_location(OrderId, start);
     .print("Spawning order: ", OrderId);
     !call_for_proposals(1, [station_1, station_2, station_3, station_4, station_5], OrderId).

// ROOT CAUSE FIX (blind AMR selection): this used to pick a transport AMR
// by hashing the order's own random id (I = round(R*10000) mod N) with zero
// regard for which AMRs were actually busy. With 5 concurrent order holons
// and only 2 physical AMRs, that routinely piled several jobs onto one
// AMR's jobQueue while the other sat idle at the dock — and a deep enough
// queue behind a 2-leg station-to-station transport can exceed the 60s
// await_station_start patience even though the AMR itself works correctly.
// Ask AMRArtifact which AMR is least loaded (amr_load: queued jobs + 1 if
// currently committed/carrying, so 0 == genuinely idle) and dispatch there.
+!request_transport(OrderId, From, To)
  <- .my_name(Me);
     .send(supervisor, askOne, amr_physical_ids(AmrIds), amr_physical_ids(AmrIds));
     getFleetStatus(StatusStr)[artifact_name("amr_artifact"), wsp("factory_ws")];
     .term2string(Statuses, StatusStr);
     .findall(load(Load, AgentName),
              (.member(amr(AgentName, PhysicalId), AmrIds) & .member(amr_load(PhysicalId, Load), Statuses)),
              Loads);
     .min(Loads, load(BestLoad, Amr));
     -+dispatched_amr(OrderId, Amr);                        // NEW (overwrite)
     .print("Requesting transport for ", OrderId, " to ", To, " via ", Amr, " (load=", BestLoad, ")");
     .send(Amr, achieve, transport(OrderId, From, To)).

+transport_done(OrderId)[source(Amr)]
  <- .print("Transport done for ", OrderId);
     ?cnp_winner(OrderId, Winner);
     .send(Winner, tell, item_arrived(OrderId)).

+transport_blocked(OrderId)[source(Amr)]
  <- .print("Transport blocked for ", OrderId, " - signaling supervisor");
     .send(supervisor, tell, transport_blocked(OrderId)).

+step_complete(OrderId, Step)[source(Station)]
  : recipe_remaining(OrderId, Remaining)
  <- .print("Step ", Step, " complete for ", OrderId, " at ", Station);
     -+current_location(OrderId, Station);
     if (Remaining == []) {
         // FIX: this branch previously just printed and stopped — no new
         // order was ever spawned afterwards. Since each order holon only
         // ever creates one order (in +timer_expired("batch_wait", Me)),
         // that meant every order holon produced exactly one order for the
         // entire run and then sat idle forever once it finished, which is
         // why AMRs return to their dock and stay there ("stopping at
         // base") instead of continuing to work. Clean up this order's
         // beliefs and request the next batch so production continues.
         .print("Order ", OrderId, " fully complete");
         -recipe_remaining(OrderId, Remaining);
         -my_order_id(OrderId);
         -order_random(OrderId, _);
         -current_location(OrderId, _);
         -dispatched_amr(OrderId, _);
         -cnp_winner(OrderId, _);
         !request_next_batch;
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
     // FIX: order_1..order_5 are likewise players in factory_prosa_org and
     // factory_adacor_org on top of their explicit factory_ws focus, so
     // artifact_name("supervisor_artifact") alone is the same ambiguous
     // CArtAgO lookup described in amr_agent.asl -- pin it with wsp().
     if (test_hook_cnp_slow_accept(true)[artifact_name("supervisor_artifact"), wsp("factory_ws")]) {
         .print("Test Hook: CNP slow accept — waiting to simulate delay");
         +pending_accept_step(OrderId, Step);        // NEW — preserve Step; cnp_state is already gone by the time this timer fires
         startTimer(OrderId, 3000, Me);
     } else {
         !finish_select_proposal(OrderId, Winner, Step);
     }.

+timer_expired(OrderId, Me)
  : propose(Winner, Cost)[source(Winner)] & test_hook_cnp_slow_accept(true)[artifact_name("supervisor_artifact"), wsp("factory_ws")] & my_name(Me) & pending_accept_step(OrderId, Step)
  <- -pending_accept_step(OrderId, Step);
     !finish_select_proposal(OrderId, Winner, Step).

+!finish_select_proposal(OrderId, Winner, Step)
  <- -+cnp_winner(OrderId, Winner);
     .send(Winner, tell, accept_proposal(OrderId));
     for ( propose(Loser, _) ) {
         if (Loser \== Winner) {
             .send(Loser, tell, reject_proposal(OrderId));
         }
     }
     .abolish(propose(_, _));
     .abolish(refuse(_));
     ?current_location(OrderId, CurrentLoc);
     !request_transport(OrderId, CurrentLoc, Winner);
     !await_station_start(OrderId, Winner, Step).

+!select_proposal(Step, Stations, OrderId)
  <- .print("No proposals received for ", OrderId, " - retrying CNP");
     .abolish(propose(_, _));
     .abolish(refuse(_));
     .wait(1000);
     !call_for_proposals(Step, Stations, OrderId).

// ROOT CAUSE FIX (silent 60s stall on a station-side lock-TTL race):
// resource_holon.asl's provisional-lock bid TTL (started when it proposes)
// only had a ~2s margin over this order's 3s CNP-collection window. When
// the discrete-event clock advances in large jumps (as it now correctly
// does after the NER-leak fix), that margin is regularly blown through —
// the station's own bid TTL fires and reverts it to idle before it has
// processed our accept_proposal. It then correctly detects the mismatch
// (station_state no longer provisional_lock) and replies with
// reject_proposal(Me, "lock_expired_or_superseded") instead of ever
// starting — but that plan has no .print, and nothing here was listening
// for it, so the order holon just sat out the full 60s await timeout
// waiting for an inform_start that had already been refused. Confirmed
// empirically: 60 CNP rounds picked a winner in one run, only 18 stations
// ever printed "Accepted proposal" — the other 42 hit this silent path.
// Wait for the rejection too and recover immediately instead of stalling.
+!await_station_start(OrderId, Station, Step)
  <- .my_name(Me);
     .concat(OrderId, "_await", AwaitKey);
     // Wait for up to 60 seconds of SIMULATED time (using TimerArtifact)
     startTimer(AwaitKey, 60000, Me);
     .wait(inform_start(Station)[source(Station)] | sim_timeout(AwaitKey) | reject_proposal(Station, _)[source(Station)]);
     if (inform_start(Station)[source(Station)]) {
         cancelTimer(AwaitKey, Me);
         // Retract so a future await on this same station (very likely —
         // the same order retries the same winning station, or a later
         // order picks it again) can't be satisfied instantly by this
         // stale belief before anything has actually happened this time.
         -inform_start(Station)[source(Station)];
         .print("Station ", Station, " started processing ", OrderId);
     } else {
         if (reject_proposal(Station, _)[source(Station)]) {
             cancelTimer(AwaitKey, Me);
             -reject_proposal(Station, _)[source(Station)];
             .print("Proposal to ", Station, " for ", OrderId, " was superseded before it could start (lock-TTL race) - retrying CNP for step ", Step);
             ?dispatched_amr(OrderId, Amr);
             .send(Amr, tell, abort_transport(OrderId));
             !call_for_proposals(Step, [station_1,station_2,station_3,station_4,station_5], OrderId);
         } else {
             -sim_timeout(AwaitKey);
             .print("Failed to get inform_start from ", Station, " (simulated timeout) - retrying CNP for step ", Step);
             ?dispatched_amr(OrderId, Amr);
             .send(Amr, tell, abort_transport(OrderId));
             // ROOT CAUSE FIX (station self-deadlock on retry): Station was
             // never told to release the provisional_lock it still holds for
             // this exact OrderId. Every retried CNP for the same order then
             // reached its own abandoned lock at Station and got refused as
             // "station_busy" — the retry could only ever succeed on a
             // different Stage-2 station (or never, if that one was also
             // legitimately locked). Release the lock before re-issuing the
             // CFP; resource_holon.asl's abort_current_operation already
             // handles this safely (no-ops if Station has already moved on).
             .send(Station, tell, abort_current_operation(OrderId));
             !call_for_proposals(Step, [station_1,station_2,station_3,station_4,station_5], OrderId);
         }
     }.

+timer_expired(AwaitKey, Me)
  : .substring("_await", AwaitKey)
  <- +sim_timeout(AwaitKey).

// ── ADACOR Phase 0 Compensating Abort ────────────────────────────────────

+abort_current_operation(OrderId)
  : my_order_id(OrderId)
  <- .drop_intention(await_station_start(OrderId, _, _));
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
     .drop_intention(await_station_start(_, _, _));
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
