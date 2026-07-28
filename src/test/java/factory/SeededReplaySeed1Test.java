package factory;

import org.junit.jupiter.api.Test;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import static org.junit.jupiter.api.Assertions.*;

public class SeededReplaySeed1Test {
    private static final int TICK_BUDGET = 100;
    private static final long SEED = 1L;

    @Test
    void invariantsHoldForSeed() {
        SimulationTestHarness harness = new SimulationTestHarness();
        SimRunHandle h = harness.run("factory.jcm", TICK_BUDGET, SEED);

        assertTrue(h.completedCleanly(), "Simulation did not complete within " + TICK_BUDGET + " ticks for seed " + SEED);
        assertNotNull(h.amrArtifact(), "AMR artifact null for seed " + SEED);
        assertTrue(h.amrArtifact().currentPositions.length > 0, "AMR fleet empty for seed " + SEED);

        long[] ids = ManagementFactory.getThreadMXBean().findDeadlockedThreads();
        assertNull(ids, "Deadlocked threads for seed " + SEED + ": " + Arrays.toString(ids));
    }
}
