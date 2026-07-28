package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV9EpochMismatchTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV9_EpochMismatch() {
        SimRunHandle h = harness.run(JCM_FILE, 40, SEED, sim -> {
            sim.injectEpochMismatchOn = "station_5";
        });
        assertTrue(h.completedCleanly(), "V9 should complete cleanly");
    }
}
