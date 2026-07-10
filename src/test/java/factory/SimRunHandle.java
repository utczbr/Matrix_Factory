package factory;

/**
 * Typed handle to a completed simulation run's live state.
 *
 * Returned by {@link SimulationTestHarness#run} so invariant tests can
 * assert directly against artifact state instead of re-parsing stdout.
 */
public record SimRunHandle(
        MainSimulator simulator,
        int runId,
        int tickBudget
) {
    /** The AMR fleet artifact — access fleet IDs, completed job counts, etc. */
    public AMRArtifact amrArtifact() {
        return simulator.getAmrArtifact();
    }

    /** The supervisor artifact. */
    public SupervisorArtifact supervisorArtifact() {
        return simulator.getSupervisorArtifact();
    }

    /** The timer artifact — access TTL evaluations. */
    public TimerArtifact timerArtifact() {
        return simulator.getTimerArtifact();
    }

    /** Whether the simulation completed within its tick budget. */
    public boolean completedCleanly() {
        return simulator.isShutdown();
    }
}
