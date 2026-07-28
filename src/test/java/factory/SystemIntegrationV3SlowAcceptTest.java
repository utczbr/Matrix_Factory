package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV3SlowAcceptTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV3_Part1_SlowAccept() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.maxOrders = 5;
            sim.cnpSlowAccept = true;
            sim.ttl = 2000;
        });
        assertTrue(h.completedCleanly(), "V3 Part 1 should complete cleanly");
    }
}
