{ include("$jacamoJar/templates/common-cartago.asl") }
{ include("$jacamoJar/templates/common-moise.asl") }

// Order Holon (Phase 2 + Phase 3)

!start.

+!start
  <-
     .my_name(Me);
     +my_name(Me); .print("Order Holon ", Me, " starting");
     +current_epoch(0);
     // Fix for Defect D follow-up: !start runs both at initial boot (no-op,
     // nothing to clean up yet) and at resume from ADACOR Phase1 suspend
     // (real cleanup). Any order this holon had in flight when suspended was
     // abandoned — its beliefs (my_order_id, recipe_remaining, etc.) are left
     // as-is for now (a separate, broader cleanup than this fix's scope —
     // see the near-zero-completion writeup), but the watchdog specifically
     // must be cleared here: otherwise a stale timer for that abandoned
     // order can still fire later, after resume, once is_suspended is gone,
     // and would incorrectly retry CNP for an order nobody is tracking
     // anymore.
     -is_suspended;
     .findall(step_watchdog(O,S,St,K), step_watchdog(O,S,St,K), StaleWatchdogs);
     for ( .member(step_watchdog(O,S,St,K), StaleWatchdogs) ) {
         cancelTimer(K, Me);
         -step_watchdog(O,S,St,K);
     }
     !request_next_batch.

+!request_next_batch
  : my_name(Me)
  <- .print("Requesting next batch... Me=", Me);
     startTimer("batch_wait", 2000, Me).

+timer_expired("batch_wait", Me)
  : my_name(Me) & is_suspended
  <- true.

+timer_expired("batch_wait", Me)
  : my_name(Me) & not is_suspended
  <- .random(R);
     .concat("ORD-", Me, "-", R, OrderId);
     +my_order_id(OrderId);
     +order_random(OrderId, R);
     +recipe_remaining(OrderId, [2,3]);          // NEW — steps left after step 1
     +current_location(OrderId, start);
     .print("Spawning order: ", OrderId);
     recordEvent(OrderId, "SUBMITTED")[artifact_name("database"), wsp("factory_ws")];
     !call_for_proposals(1, [station_1, station_2, station_3, station_4, station_5], OrderId).

// ROOT CAUSE FIX (blind AMR selection, take 2): the previous fix replaced
// the pseudo-random hash pick with a getFleetStatus()-informed .min(), but
// that read and the eventual commit were still two separate steps on two
// separate agents — this plan called getFleetStatus() and then merely
// .send()'d an achieve(transport(...)) to whichever AMR looked best; the
// actual state mutation (requestTransport()) only happened later, inside
// that AMR agent's own reasoning cycle. Nothing prevented a second order
// holon from calling getFleetStatus() in that gap and seeing the exact same
// "free" snapshot — and with 5 order holons whose CNP timers routinely
// expire in the same evaluateTTLs batch, that gap is hit on essentially
// every dispatch: every "via amrX (load=N)" line ever logged reported
// load=0, even for an AMR that had just been committed elsewhere. One AMR's
// jobQueue piled up while the other sat idle at its dock — exactly the
// failure this was supposed to prevent — and a deep enough queue behind a
// 2-leg station-to-station transport routinely exceeds the 60s
// await_station_start patience even though the AMR itself works correctly.
// reserveTransport() folds the read and the commit into one CArtAgO
// operation call, so no other agent's call can land in between; it returns
// the PHYSICAL id it committed to, which we map back to the agent name to
// notify (bookkeeping only — the job is already running).
+!request_transport(OrderId, From, To)
  <- .my_name(Me);
     .send(supervisor, askOne, amr_physical_ids(AmrIds), amr_physical_ids(AmrIds));
     reserveTransport(From, To, OrderId, ChosenPhysicalId, BestLoad)[artifact_name("amr_artifact"), wsp("factory_ws")];
     .member(amr(Amr, ChosenPhysicalId), AmrIds);
     -+dispatched_amr(OrderId, Amr);                        // NEW (overwrite)
     .print("Requesting transport for ", OrderId, " to ", To, " via ", Amr, " (load=", BestLoad, ")");
     .send(Amr, achieve, transport(OrderId, From, To)).

// ROOT CAUSE FIX (repeated tell-messages silently swallowed): same class
// of bug as resource_holon.asl's accept_proposal/abort_current_operation —
// transport_done(OrderId)[source(Amr)] is the exact same literal whenever
// the same physical AMR is dispatched again for this order (routine: the
// same order needs multiple legs — dock→stage1, stage1→stage2,
// stage2→stage3 — and reserveTransport's load-balancing frequently picks
// the same AMR back-to-back). Without retracting it, the second time the
// same AMR finishes a job for this order, Jason sees "no change" to the
// belief base and never fires this plan at all — the order holon just
// silently never learns the transport finished.
+transport_done(OrderId)[source(Amr)]
  <- -transport_done(OrderId)[source(Amr)];
     .print("Transport done for ", OrderId);
     ?cnp_winner(OrderId, Winner);
     .send(Winner, tell, item_arrived(OrderId)).

+transport_blocked(OrderId)[source(Amr)]
  <- -transport_blocked(OrderId)[source(Amr)];   // Same class of fix as transport_done above
     .print("Transport blocked for ", OrderId, " - signaling supervisor");
     .send(supervisor, tell, transport_blocked(OrderId)).

+step_complete(OrderId, Step)[source(Station)]
  : recipe_remaining(OrderId, Remaining) & step_watchdog(OrderId, Step, Station, WatchdogKey)
  <- .my_name(Me);
     cancelTimer(WatchdogKey, Me);
     -step_watchdog(OrderId, Step, Station, WatchdogKey);
     .print("Step ", Step, " complete for ", OrderId, " at ", Station);
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
         recordEvent(OrderId, "COMPLETED")[artifact_name("database"), wsp("factory_ws")];
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

// Fallback: recipe_remaining or the watchdog belief is already gone (e.g. the
// watchdog already fired and this step_complete arrived just after the retry
// was issued). Same-class fix as the tell-message plans above: still cancel
// whatever's left so nothing lingers.
+step_complete(OrderId, Step)[source(Station)]
  <- .print("Step ", Step, " complete for ", OrderId, " at ", Station, " (stale — watchdog or retry already superseded it)").

+step_failed(OrderId, Step, Reason)[source(Station)]
  : step_watchdog(OrderId, Step, Station, WatchdogKey)
  <- .my_name(Me);
     cancelTimer(WatchdogKey, Me);
     -step_watchdog(OrderId, Step, Station, WatchdogKey);
     -step_failed(OrderId, Step, Reason)[source(Station)];   // Same class of fix as transport_done above
     .print("Step ", Step, " failed for ", OrderId, " (", Reason, ") — retrying same step");
     !call_for_proposals(Step, [station_1,station_2,station_3,station_4,station_5], OrderId).

+step_failed(OrderId, Step, Reason)[source(Station)]
  <- -step_failed(OrderId, Step, Reason)[source(Station)];
     .print("Step ", Step, " failed for ", OrderId, " (", Reason, ") — retrying same step (stale watchdog)");
     !call_for_proposals(Step, [station_1,station_2,station_3,station_4,station_5], OrderId).

// ROOT CAUSE FIX (near-zero-completion investigation, continued): fires only
// if 120s of simulated time pass after inform_start with neither
// step_complete nor step_failed arriving — the station-side intention that
// was supposed to send one of those was dropped (ADACOR Phase1 suspend
// landing mid-processing being the confirmed mechanism; any other silent
// station-side failure would hit the same gap). Recovery mirrors
// await_station_start's own timeout branch exactly: release whatever lock
// the station still holds, wait for its ack so the retry can't race the
// cleanup, then re-issue CFP for the same step.
//
// Suspend-aware guard added on review: an earlier version of this fix had
// no guard at all, so a watchdog firing while THIS order holon is itself
// suspended (ADACOR Phase1) would start a fresh CNP round while it's
// supposed to be quiescent. `station_state` was suggested as the guard, but
// that belief belongs to resource_holon.asl, not this file — order holons
// never hold it, so that guard would silently never match anything. The
// actual mechanism here is `is_suspended`, set by +suspend_intention below
// and cleared by !start on resume.
+timer_expired(WatchdogKey, Me)
  : step_watchdog(OrderId, Step, Station, WatchdogKey) & my_name(Me) & not is_suspended
  <- -step_watchdog(OrderId, Step, Station, WatchdogKey);
     .print("No step_complete/step_failed from ", Station, " for ", OrderId,
            " after 120s (watchdog) — station-side intention likely dropped; retrying CNP for step ", Step);
     .send(Station, tell, abort_current_operation(OrderId));
     .wait(abort_ack(OrderId)[source(Station)]);
     -abort_ack(OrderId)[source(Station)];
     !call_for_proposals(Step, [station_1,station_2,station_3,station_4,station_5], OrderId).

// Suspended: don't retry CNP while quiescent. The belief is left in place —
// !start's cleanup on resume (see below) retracts it and cancels the timer
// explicitly, rather than letting a stale watchdog silently re-fire later
// against an order this holon has already abandoned.
+timer_expired(WatchdogKey, Me)
  : step_watchdog(OrderId, Step, Station, WatchdogKey) & my_name(Me) & is_suspended
  <- .print("Watchdog for ", OrderId, " at ", Station, " expired while suspended — deferring to resume cleanup").

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
  : is_suspended
  <- .print("No proposals received for ", OrderId, ", but suspended — aborting CNP");
     .abolish(propose(_, _));
     .abolish(refuse(_)).

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
         // ROOT CAUSE FIX (near-zero-completion investigation): every other
         // phase of the order lifecycle has a timeout — the 3s CNP window,
         // the 20s/60s bid-TTL and await_station_start guards above — but
         // once inform_start arrives, the order holon has NO active wait at
         // all for step_complete/step_failed; it just sits as a passive
         // listener with no recovery path if that message never comes. It
         // can legitimately never come: resource_holon.asl's
         // execute_physical_operation intention is unconditionally dropped
         // by ADACOR Phase1's suspend_intentions, and if that lands while
         // processOrder() is still blocked waiting for simulated time to
         // elapse (a wide window — up to 72s at station S4's 3x-mean clip),
         // the plan's final step_complete/step_failed send never executes.
         // This order holon would then never call !request_next_batch again
         // for the rest of the run (recipe_remaining never reaches []) —
         // exactly the low-submitted/low-completed signature seen in
         // results_360_10.csv. 120s clears S4's 72s worst case with margin
         // for AMR transport + CNP overhead already spent getting here.
         .concat(OrderId, "_stepwatch", WatchdogKey);
         +step_watchdog(OrderId, Step, Station, WatchdogKey);
         startTimer(WatchdogKey, 120000, Me);
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
             //
             // ROOT CAUSE FIX (retry CFP raced this same abort): this used to
             // fire the retry's call_for_proposals immediately after sending
             // abort_current_operation, with nothing guaranteeing Station
             // finished processing the abort first. A live trace showed
             // Station proposing fresh to the retry's CFP *while* its own
             // abort_current_operation plan was still mid-cleanup — visible
             // as the retry's new bid-TTL startTimer line landing between
             // that plan's releaseStation() log line and its own final
             // print. Waiting for an explicit ack turns this into a real
             // rendezvous instead of two independently-scheduled messages:
             // the retry CFP now provably cannot go out until Station has
             // told us it's actually idle again.
             .send(Station, tell, abort_current_operation(OrderId));
             .wait(abort_ack(OrderId)[source(Station)]);
             -abort_ack(OrderId)[source(Station)];
             !call_for_proposals(Step, [station_1,station_2,station_3,station_4,station_5], OrderId);
         }
     }.

+timer_expired(AwaitKey, Me)
  : .substring("_await", AwaitKey)
  <- +sim_timeout(AwaitKey).

// ── ADACOR Phase 0 Compensating Abort ────────────────────────────────────

+abort_current_operation(OrderId)
  : my_order_id(OrderId)
  <- -abort_current_operation(OrderId);   // Same class of fix as the tell-message plans above
     .drop_intention(await_station_start(OrderId, _, _));
     .drop_intention(request_transport(OrderId, _, _));
     .print("ADACOR Phase0 abort: Order Holon dropping intentions for ", OrderId);
     !request_next_batch.

+abort_current_operation(OrderId)   // Different order — ignore
  <- -abort_current_operation(OrderId).

// ── ADACOR Phase 1 Suspend / Resume ──────────────────────────────────────

// Correct placement: Order Holons DO initiate call_for_proposals.
+suspend_intentions[source(supervisor)]
  : my_name(Me)
  <- +is_suspended;
     cancelTimer("batch_wait", Me);
     .drop_intention(request_next_batch);
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
