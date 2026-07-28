package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationV4PriceSpikeTest {
    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L;

    @Test
    public void testV4_PriceSpike() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.priceSeriesFile = "price_series_spike_test.csv";
        });
        assertTrue(h.completedCleanly(), "V4 should complete cleanly");
    }
}
