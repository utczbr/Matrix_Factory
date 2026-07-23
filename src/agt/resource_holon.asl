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
     +my_station(Me);
     releaseStation("").

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
          // ROOT CAUSE FIX (bid-TTL race against accept_proposal): this was
          // 5000ms against the order holon's 3000ms CNP-collection window —
          // only a ~2s margin for the winning station to actually receive
          // and process accept_proposal before its own bid TTL reverted it
          // to idle first. Once the simulation clock advances at its
          // intended (correct) speed instead of being accidentally
          // throttled by the NER-registration leak, that margin is blown
          // through routinely (measured: 60 CNP rounds picked a winner,
          // only 18 stations ever got to acknowledge it). order_holon.asl
          // now recovers immediately instead of stalling 60s when this
          // still happens (see await_station_start's reject_proposal
          // branch), but widening the margin here means it happens far
          // less often in the first place.
          startTimer(OrderId, 20000, Me);  // Discrete-event NER Timer
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

// ROOT CAUSE FIX (repeated tell-messages silently swallowed): Jason's
// belief revision function only fires a "+" event on an actual CHANGE to
// the belief base. accept_proposal(OrderId)[source(Sender)] is the exact
// same literal on every CNP retry for a given order — OrderId is the
// order's own id, unchanged across retries, and Sender is always the same
// order holon. Once this station processed accept_proposal for attempt 1
// and never retracted it, attempt 2's *identical* accept_proposal message
// was recognized by Jason as "no change" and never generated a new event
// at all — neither this plan nor the "already superseded" fallback below
// ever fired. Confirmed in a live trace: accept_proposal was provably sent
// (the caller's own "Requesting transport" print, which only runs after
// the send, appeared), station_state held provisional_lock(OrderId) for
// the entire 20s bid-TTL with nothing else touching it, and yet "Accepted
// proposal" never printed a second time — the bid-TTL simply expired on
// schedule instead. Retracting the belief here (and in the fallback below)
// means the next identical accept_proposal is a genuine change again.
+accept_proposal(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId)) & my_name(Me) & my_recipe_step(Step)
  <- -accept_proposal(OrderId)[source(Sender)];
     cancelTimer(OrderId, Me);
     registerLock(OrderId, Me, Sender);
     +active_order(OrderId, Sender, Step);      // NEW — remember who + what step
     .print("Accepted proposal for ", OrderId, ", waiting for item to arrive").

+item_arrived(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId)) & my_name(Me) & active_order(OrderId, Sender, Step)
  <- -item_arrived(OrderId)[source(Sender)];   // Same class of fix as accept_proposal above
     -+station_state(busy_processing(OrderId));
     .send(Sender, tell, inform_start(Me));
     !execute_physical_operation(OrderId).

// Catch-all so a stray item_arrived that doesn't match the guard (e.g. this
// station already moved on) doesn't linger unretracted and swallow a real,
// later one for the same OrderId+Sender.
+item_arrived(OrderId)[source(Sender)]
  <- -item_arrived(OrderId)[source(Sender)].

// Plan: Catch-all rejection for delayed accept_proposal (superseded lock)
+accept_proposal(OrderId)[source(Sender)]
   : not station_state(provisional_lock(OrderId)) & my_name(Me)
   <- -accept_proposal(OrderId)[source(Sender)];
      .send(Sender, tell, reject_proposal(Me, "lock_expired_or_superseded")).

// Phase 3 Amended reject_proposal plan
+reject_proposal(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId)) & my_name(Me)
  <- -reject_proposal(OrderId)[source(Sender)];   // Same class of fix as accept_proposal above
     -+station_state(idle); // Update Jason synchronously before external action
     cancelTimer(OrderId, Me);
     releaseStation(OrderId); // Sync artifact volatile field
     .print("Proposal rejected for order ", OrderId, " (CNP lost), reverting to idle").

+reject_proposal(OrderId)[source(Sender)]
  : not station_state(provisional_lock(OrderId)) & my_name(Me)
  <- -reject_proposal(OrderId)[source(Sender)].

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

// ROOT CAUSE FIX (stale bid-TTL timer corrupts the next retry's lock):
// accept_proposal (line 64) and reject_proposal (line 84) both cancelTimer()
// before/while leaving provisional_lock — this plan didn't. OrderId is the
// same literal string across every CNP retry for an order (it's the order's
// own id, not a per-attempt id), so the 20s bid-TTL timer registered when
// THIS station proposed to the attempt being aborted was never cancelled —
// it just kept sitting in TimerArtifact's queue. By the time it naturally
// fired, this station had very often already proposed again (same OrderId)
// for the retried CNP round and was sitting in a brand-new, legitimate
// provisional_lock(OrderId) — and timer_expired's guard only checks
// "is my current state provisional_lock for this OrderId", which the stale
// timer satisfies just as well as a fresh one. The result: the *next*
// attempt's lock got silently revoked before accept_proposal ever had a
// chance to land, over and over, for stations with heavy repeat contention
// on a single order (station_5, the sole stage-3 gate, being the worst
// case) — visible in the log as exactly two "Accepted proposal" /
// "provisional_lock revoked" cycles per order before it stops proposing
// (i.e. refuses as busy) to that order's CFP retries indefinitely.
// ROOT CAUSE FIX (retry CFP interleaves with this plan's own cleanup): the
// cancelTimer() fix above closes the *stale-timer* half of this bug, but
// there's a second, independent half — this plan and the retry CFP that
// follows it are two separate fire-and-forget .send()s from
// order_holon.asl with nothing enforcing that this plan finishes before
// the retry is broadcast. Confirmed in a live trace: this plan's own
// releaseStation() log line ("Station S5 released...") printed, then this
// SAME station's fresh startTimer for the *retried* CFP's new proposal
// printed, and only *after* that did this plan's own final print appear —
// i.e. Jason interleaved this plan's remaining steps with the brand-new
// provisional_lock this station had already granted the retry. Nothing
// after that point corrupts station_state itself (this plan touches
// station_state only in its very first line, above), but the two
// intentions racing at all here is exactly the kind of ambiguity that
// produces the two-attempts-then-stuck pattern seen in practice — the
// fix is to remove the ambiguity, not to reason about which interleaving
// happens to be harmless this time. Replying with an explicit ack and
// having the caller wait for it turns "fire two messages and hope they're
// processed in order" into a real rendezvous: the retry CFP now provably
// cannot be sent until this station has told us it's fully idle again.
// ROOT CAUSE FIX (repeated tell-messages silently swallowed — same class as
// accept_proposal above, and the most severe instance of it): every timeout
// cycle for a given order sends abort_current_operation(OrderId)[source(Sender)]
// with the exact same OrderId and the exact same Sender (the order holon
// never changes identity). Without retracting it here, the SECOND time an
// order times out and re-sends this same literal, Jason recognizes "no
// change" and never fires either plan below at all — meaning the station
// never sends back abort_ack(OrderId), and the caller's
// .wait(abort_ack(OrderId)[source(Station)]) in order_holon.asl (added to
// fix the retry-interleaving race below) would then block forever. Both
// branches must retract on every entry, including the "already idle"
// fallback — the fallback is exactly what a second, third, etc. abort for
// the same order hits once the first one has already reverted the lock.
+abort_current_operation(OrderId)[source(Sender)]
  : station_state(provisional_lock(OrderId)) & my_name(Me)
  <- -abort_current_operation(OrderId)[source(Sender)];
     -+station_state(idle);
     cancelTimer(OrderId, Me);
     releaseStation(OrderId);   // Sync artifact volatile field — dashboard sees IDLE
     releaseLock(OrderId);      // No-op (lock not yet registered); safe to call
     .print("ADACOR Phase0 abort: provisional_lock revoked for ", OrderId);
     .send(Sender, tell, abort_ack(OrderId)).

// Lock already gone (natural revert or different order) — discard abort
// silently, but still ack: the caller is waiting on this reply either way.
+abort_current_operation(OrderId)[source(Sender)]
  : not station_state(provisional_lock(OrderId))
  <- -abort_current_operation(OrderId)[source(Sender)];
     .send(Sender, tell, abort_ack(OrderId)).

// ── Phase 1 Suspend ───────────────────────────────────────────────────────

// Resource Holons drop only operations they can actually hold.
// .drop_intention(call_for_proposals) is NOT included: Resource Holons
// respond to CFPs — they never initiate them. That intention belongs to order_holon.asl.
+suspend_intentions[source(supervisor)]
  <- .drop_intention(execute_physical_operation(_));
     ?my_name(Me);
     if (station_state(busy_processing(OrderId)) | station_state(provisional_lock(OrderId))) {
         cancelTimer(OrderId, Me);
         releaseLock(OrderId);
         releaseStation(OrderId);
     }
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

// ROOT CAUSE FIX (same stale-timer gap as abort_current_operation above):
// a schema-epoch reinit can also cut a station out of provisional_lock
// without ever going through accept_proposal/reject_proposal's
// cancelTimer() call. busy_processing needs no cancel here — accept_proposal
// already cancelled the bid-TTL before busy_processing was ever entered —
// but the provisional_lock case is exactly the abort_current_operation gap.
+!reinitialize_schema
  <- .drop_all_intentions;
     ?station_state(State);
     ?my_name(Me);
     if (State == provisional_lock(OrderId)) {
         cancelTimer(OrderId, Me);
         releaseStation(OrderId); // Syncs the artifact so dashboard sees IDLE
     } else {
         if (State == busy_processing(OrderId)) {
             releaseStation(OrderId); // Syncs the artifact so dashboard sees IDLE
         }
     }
     -+station_state(idle);
     !start.
