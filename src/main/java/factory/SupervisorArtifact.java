package factory;

import cartago.*;
import java.util.concurrent.ConcurrentHashMap;

public class SupervisorArtifact extends Artifact {

    /**
     * Maps OrderId (UUID string) → LockEntry(StationId, OrderHolonName).
     *
     * Populated by Resource Holons on accept_proposal (transition to
     * busy_processing),
     * so the supervisor knows which agent pair to abort or monitor.
     * The station agent name and order holon name are stored as atoms (un-quoted),
     * enabling direct use in Jason .send() calls and list membership checks.
     */
    private final ConcurrentHashMap<String, LockEntry> reservationRegistry = new ConcurrentHashMap<>();

    private record LockEntry(String stationAgentName, String orderHolonName) {
    }

    private MainSimulator mainSimulator;

    /** Injected by MainSimulator before the tick loop starts. Not an @OPERATION. */
    public void setMainSimulator(MainSimulator ms) {
        this.mainSimulator = ms;
    }

    private int runId;
    @OPERATION
    void init(int runId) {
        this.runId = runId;
        RunManager.getSimulator(runId).supervisorArtifact = this;

        // Always defined (not conditional like the test_hook_* properties
        // below) because supervisor_agent.asl's energy_price_spike plans
        // pattern-match on both adacor_enabled(true) and adacor_enabled(false)
        // — the guard must always resolve one way or the other.
        defineObsProperty("adacor_enabled", RunManager.getSimulator(runId).adacorEnabled);

        if (RunManager.getSimulator(runId).cnpSlowAccept) {
            defineObsProperty("test_hook_cnp_slow_accept", true);
        }
        if (RunManager.getSimulator(runId).ttl > 0) {
            defineObsProperty("test_hook_ttl", RunManager.getSimulator(runId).ttl);
        }
        if (RunManager.getSimulator(runId).blockAckFrom != null) {
            defineObsProperty("test_hook_block_ack_from", RunManager.getSimulator(runId).blockAckFrom);
        }
        if (RunManager.getSimulator(runId).injectEpochMismatchOn != null) {
            defineObsProperty("test_hook_inject_epoch_mismatch", RunManager.getSimulator(runId).injectEpochMismatchOn);
        }
    }

    // ── Lock Registry Operations ─────────────────────────────────────────

    /**
     * Register a confirmed lock when a Resource Holon transitions to
     * busy_processing.
     *
     * Called from resource_holon.asl's accept_proposal plan with three arguments:
     * - orderId: the stable UUID from the CFP (quoted Jason string)
     * - stationName: the Resource Holon's agent name atom (e.g., station_1)
     * - orderHolonName: the Order Holon's agent name atom (e.g., order_2)
     *
     * Storing the order holon name eliminates the need to derive it from the UUID
     * and prevents the type-mismatch that would cause the grid-saturation filter to
     * incorrectly suspend all order holons (including those with active locks).
     */
    @OPERATION
    void registerLock(String orderId, String stationName, String orderHolonName) {
        reservationRegistry.put(orderId, new LockEntry(stationName, orderHolonName));
        log("Registry: registered " + orderId + " → [" + stationName
                + ", " + orderHolonName + "]");
    }

    /**
     * Remove a lock on normal completion, defect, abort, or TTL expiry.
     * Idempotent — safe to call even if the orderId is no longer present.
     */
    @OPERATION
    void releaseLock(String orderId) {
        reservationRegistry.remove(orderId);
        log("Registry: released " + orderId);
    }

    /**
     * Returns the current registry snapshot as a Jason list of
     * lock(OrderId, StationAgentName, OrderHolonName) terms.
     *
     * Term format:
     * lock("f3a1-uuid", station_1, order_2)
     * ┌── quoted string: UUID may contain hyphens (invalid atom characters)
     * └── unquoted atoms: valid Jason identifiers
     *
     * Caller (supervisor_agent) uses this to:
     * 1. Grid saturation: filter Order Holons NOT in any lock → low-priority
     * candidates
     * 2. Phase 0 abort: extract (StationName, OrderHolonName) pairs for .send()
     * dispatch
     */
    @OPERATION
    void getActiveLocks(OpFeedbackParam<String> locks) {
        StringBuilder sb = new StringBuilder("[");
        reservationRegistry.forEach((oid, entry) -> sb.append("lock(\"").append(oid).append("\",")
                .append(entry.stationAgentName()).append(",") // unquoted atom
                .append(entry.orderHolonName()).append("),") // unquoted atom
        );
        if (sb.length() > 1 && sb.charAt(sb.length() - 1) == ',') {
            sb.deleteCharAt(sb.length() - 1);
        }
        sb.append("]");
        locks.set(sb.toString());
    }

    // ── Transition Operations ─────────────────────────────────────────────

    /**
     * Begins Phase 0 of the two-phase commit. Calls MainSimulator.beginTransition()
     * to reserve the next epoch. Returns the reserved epoch number for the
     * supervisor
     * to log and later verify at commit.
     */

    @OPERATION
    void initiateTransition(String targetSchema, double currentSimTimeS,
            OpFeedbackParam<Integer> reservedEpoch) {
        OrgSchemaTransition t = mainSimulator.beginTransition(targetSchema, currentSimTimeS);
        reservedEpoch.set(t.newEpoch());
        log("Transition initiated: target=" + targetSchema + " reservedEpoch="
                + t.newEpoch() + " simT=" + currentSimTimeS);
    }

    /**
     * Finalizes the two-phase commit. Calls MainSimulator.commitTransition(), which
     * atomically applies the new epoch and schema name. The very next AdvanceTime
     * RPC and TelemetryFrame will carry the new values.
     */
    @OPERATION
    void commitTransition(double currentSimTimeS) {
        OrgSchemaTransition t = mainSimulator.activeTransition;
        if (t == null || t.phase() == OrgSchemaTransition.TransitionPhase.COMMITTED) {
            log("commitTransition called with no active transition — ignoring");
            return;
        }
        mainSimulator.commitTransition(
                t.advanceTo(OrgSchemaTransition.TransitionPhase.COMMITTED, currentSimTimeS));
        log("Transition committed: schema=" + t.targetSchema()
                + " epoch=" + t.newEpoch() + " simT=" + currentSimTimeS);
    }
}
