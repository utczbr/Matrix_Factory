package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV8ForceSpikeMaxOrdersTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV8_ForceSpikeWithMaxOrders() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.maxOrders = 5;
            sim.forceSpikeAt = 5.0;
        });
        assertTrue(h.completedCleanly(), "V8 should complete cleanly");
    }
}
