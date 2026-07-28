package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV1Test {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV1_BasicRun() {
        SimRunHandle h = harness.run(JCM_FILE, 10, SEED, sim -> {});
        assertTrue(h.completedCleanly(), "V1 should complete cleanly");
    }
}
