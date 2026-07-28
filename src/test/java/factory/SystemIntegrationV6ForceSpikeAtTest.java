package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV6ForceSpikeAtTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV6_ForceSpikeAt() {
        SimRunHandle h = harness.run(JCM_FILE, 30, SEED, sim -> {
            sim.forceSpikeAt = 5.0;
        });
        assertTrue(h.completedCleanly(), "V6 should complete cleanly");
    }
}
