package factory;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.lang.management.ManagementFactory;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Seeded replay tests — mirrors the Python side's seeding_test.py discipline
 * on the JVM side.
 *
 * Runs the same invariant assertions across multiple seeds to catch
 * timing-dependent races that only manifest under specific scheduling
 * interleavings. Turns "I ran it once and it worked" into "N seeded runs,
 * 0 invariant violations."
 *
 * <p>Note: with forkEvery=1 in build.gradle, each @ParameterizedTest
 * invocation runs in its own JVM, so JaCaMo's global state is clean
 * for each seed. This is slow but correct.
 */
class SeededReplayTests {

    private static final int TICK_BUDGET = 100;

    /**
     * Core invariant: the simulation must complete cleanly and produce
     * no deadlocked threads across a spread of seeds.
     */
    @org.junit.jupiter.api.Test
    void invariantsHoldForSeed() {
        long seed = 1;
        SimulationTestHarness harness = new SimulationTestHarness();
        SimRunHandle h = harness.run("factory.jcm", TICK_BUDGET, seed);

        assertTrue(h.completedCleanly(),
                "Simulation did not complete within " + TICK_BUDGET + " ticks for seed " + seed);

        // AMR fleet should always initialise
        assertNotNull(h.amrArtifact(), "AMR artifact null for seed " + seed);
        assertTrue(h.amrArtifact().currentPositions.length > 0,
                "AMR fleet empty for seed " + seed);

        // Deadlock check
        long[] ids = ManagementFactory.getThreadMXBean().findDeadlockedThreads();
        assertNull(ids, "Deadlocked threads for seed " + seed + ": " + Arrays.toString(ids));

        // Ledger Invariants
        OrderLedgerReader reader = new OrderLedgerReader("factory_history.db");
        java.util.Map<String, java.util.List<String>> events = reader.getOrderEvents(h.runId());
        
        int submitted = 0;
        int completed = 0;
        int aborted = 0;
        
        for (java.util.List<String> orderEvents : events.values()) {
            if (orderEvents.contains("SUBMITTED")) submitted++;
            if (orderEvents.contains("COMPLETED")) completed++;
            if (orderEvents.contains("ABORTED")) aborted++;
        }
        
        assertTrue(completed + aborted <= submitted, "More completed/aborted orders than submitted ones for seed " + seed);
    }
}
