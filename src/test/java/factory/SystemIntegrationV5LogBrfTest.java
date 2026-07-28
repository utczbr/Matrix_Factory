package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV5LogBrfTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV5_LogBrf() {
        SimRunHandle h = harness.run(JCM_FILE, 30, SEED, sim -> {
            sim.logBrfAgent = "supervisor";
        });
        assertTrue(h.completedCleanly(), "V5 should complete cleanly");
    }
}
