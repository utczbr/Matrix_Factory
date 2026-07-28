package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV3ForceAbortTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV3_Part2_ForceAbort() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.forceAbortStation = "station_1";
            sim.forceAbortOrder = "order_2";
        });
        assertTrue(h.completedCleanly(), "V3 Part 2 should complete cleanly");
    }
}
