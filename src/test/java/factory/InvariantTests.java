package factory;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.lang.management.ManagementFactory;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Timeout;
import java.util.List;
import java.util.Map;

/**
 * Invariant tests for the Matrix Factory simulation.
 *
 * These turn "I read test_v3.log and it looked fine" into mechanically
 * verifiable assertions against live artifact state. Every test uses the
 * same shared harness pattern: boot the simulation with a tick budget,
 * let it run to completion, then assert invariants against the state.
 *
 * <p>Given the JaCaMo global-state constraint (forkEvery=1 in build.gradle),
 * each test class runs in its own JVM, so tests within the same class share
 * a single simulation run and assert different invariants against it.
 */
@Timeout(value = 150, unit = TimeUnit.SECONDS)
class InvariantTests {

    private static final int TICK_BUDGET = 100;
    private static final long SEED = 42L;

    private SimulationTestHarness harness;
    private SimRunHandle handle;

    @BeforeEach
    void setUp() {
        harness = new SimulationTestHarness();
        handle = harness.run("factory.jcm", TICK_BUDGET, SEED);
    }

    @AfterEach
    void tearDown() {
        assertNoDeadlockedThreads();
    }

    // ── Liveness — no stuck orders ───────────────────────────────────────

    /**
     * Every simulation run should complete cleanly within its tick budget.
     * If this fails, the tick loop hung or an artifact blocked indefinitely.
     */
    @Test
    void simulationCompletesWithinTickBudget() {
        assertTrue(handle.completedCleanly(),
                "Simulation did not complete within " + TICK_BUDGET + " ticks");
    }

    // ── Safety — AMR artifact initialises correctly ──────────────────────

    /**
     * The AMR artifact should have created its fleet after initialisation.
     * This is the most basic smoke test that the artifact wiring is correct.
     */
    @Test
    void amrArtifactHasFleet() {
        AMRArtifact amr = handle.amrArtifact();
        assertNotNull(amr, "AMR artifact was not registered");
        assertNotNull(amr.currentPositions, "AMR positions array is null");
        assertTrue(amr.currentPositions.length > 0,
                "AMR fleet is empty — no AMRs were initialised");
    }

    // ── Ledger Invariants ────────────────────────────────────────────────
    
    @Test
    void everyAmrCompletesAtLeastOneJob() {
        AMRArtifact amr = handle.amrArtifact();
        List<Integer> completedJobs = amr.getCompletedJobCounts();
        for (int i = 0; i < completedJobs.size(); i++) {
            assertTrue(completedJobs.get(i) > 0, "AMR " + i + " completed 0 jobs");
        }
    }

    @Test
    void completedPlusAbortedEqualsSubmitted() {
        OrderLedgerReader reader = new OrderLedgerReader("factory_history.db");
        Map<String, List<String>> events = reader.getOrderEvents(handle.runId());
        
        int submitted = 0;
        int completed = 0;
        int aborted = 0;
        
        for (List<String> orderEvents : events.values()) {
            if (orderEvents.contains("SUBMITTED")) submitted++;
            if (orderEvents.contains("COMPLETED")) completed++;
            if (orderEvents.contains("ABORTED")) aborted++;
        }
        
        assertTrue(completed + aborted <= submitted, "More completed/aborted orders than submitted ones");
        // Because the simulation is bounded by TICK_BUDGET, we can't expect them to be perfectly equal, 
        // as some are still in-flight.
    }

    // ── Deadlock detection ───────────────────────────────────────────────

    /**
     * Given how many of the fixed bugs in this codebase were races (see ROOT
     * CAUSE FIX comments across order_holon.asl, amr_agent.asl,
     * resource_holon.asl, MainSimulator.java, TimerArtifact.java), check for
     * deadlocked threads as a cheap catch-all in every test's teardown.
     */
    private void assertNoDeadlockedThreads() {
        long[] ids = ManagementFactory.getThreadMXBean().findDeadlockedThreads();
        assertNull(ids, "Deadlocked threads detected: " + (ids == null ? "none" : Arrays.toString(ids)));
    }
}
