package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV7GridStressTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV7_GridStressLockHold() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.maxOrders = 5;
            sim.gridStress = true;
            sim.lockHoldOrders = "order_1,order_2,order_3";
        });
        assertTrue(h.completedCleanly(), "V7 should complete cleanly");
    }
}
