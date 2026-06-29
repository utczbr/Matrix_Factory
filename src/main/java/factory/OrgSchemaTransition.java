package factory;

/**
 * Immutable snapshot of an in-flight organizational schema transition.
 * Written by MainSimulator.beginTransition() / commitTransition();
 * read by the tick loop for TelemetryFrame assembly and logging.
 * null → no transition currently in progress.
 */
public record OrgSchemaTransition(
    String          targetSchema,       // "prosa" or "adacor"
    int             newEpoch,           // schemaEpoch value applied at COMMITTED
    double          phaseStartSimTimeS, // Simulated time when current phase began
    TransitionPhase phase
) {
    public enum TransitionPhase {
        /** Phase 0: draining active negotiations; abort escrow armed. */
        DRAIN,
        /** Phase 1: suspend_intentions broadcast; force_commit deadline active. */
        SUSPEND,
        /** Transition committed; new schema active; epoch incremented. */
        COMMITTED
    }

    public static OrgSchemaTransition startDrain(String targetSchema, int newEpoch,
                                                  double simTimeS) {
        return new OrgSchemaTransition(targetSchema, newEpoch, simTimeS,
                                       TransitionPhase.DRAIN);
    }

    public OrgSchemaTransition advanceTo(TransitionPhase next, double simTimeS) {
        return new OrgSchemaTransition(targetSchema, newEpoch, simTimeS, next);
    }
}
