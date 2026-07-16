package factory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class SystemIntegrationTests {

    private final SimulationTestHarness harness = new SimulationTestHarness();
    private static final String JCM_FILE = "factory.jcm";
    private static final long SEED = 42L; // Arbitrary seed for deterministic runs

    @Test
    public void testV1_BasicRun() {
        SimRunHandle h = harness.run(JCM_FILE, 10, SEED, sim -> {
            // --log-epochs is logged via other means but we can just let it run
        });
        assertTrue(h.completedCleanly(), "V1 should complete cleanly");
    }

    @Test
    public void testV2_LongerRunWithMaxOrders() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.maxOrders = 5;
        });
        assertTrue(h.completedCleanly(), "V2 should complete cleanly");
    }

    @Test
    public void testV3_Part1_SlowAccept() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.maxOrders = 5;
            sim.cnpSlowAccept = true;
            sim.ttl = 2000;
        });
        assertTrue(h.completedCleanly(), "V3 Part 1 should complete cleanly");
    }

    @Test
    public void testV3_Part2_ForceAbort() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.forceAbortStation = "station_1";
            sim.forceAbortOrder = "order_2";
        });
        assertTrue(h.completedCleanly(), "V3 Part 2 should complete cleanly");
    }

    @Test
    public void testV4_PriceSpike() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.priceSeriesFile = "price_series_spike_test.csv";
        });
        assertTrue(h.completedCleanly(), "V4 should complete cleanly");
    }

    @Test
    public void testV5_LogBrf() {
        SimRunHandle h = harness.run(JCM_FILE, 30, SEED, sim -> {
            sim.logBrfAgent = "supervisor";
        });
        assertTrue(h.completedCleanly(), "V5 should complete cleanly");
    }

    @Test
    public void testV6_ForceSpikeAt() {
        SimRunHandle h = harness.run(JCM_FILE, 30, SEED, sim -> {
            sim.forceSpikeAt = 5.0;
        });
        assertTrue(h.completedCleanly(), "V6 should complete cleanly");
    }

    @Test
    public void testV7_GridStressLockHold() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.maxOrders = 5;
            sim.gridStress = true;
            sim.lockHoldOrders = "order_1,order_2,order_3";
        });
        assertTrue(h.completedCleanly(), "V7 should complete cleanly");
    }

    @Test
    public void testV8_ForceSpikeWithMaxOrders() {
        SimRunHandle h = harness.run(JCM_FILE, 100, SEED, sim -> {
            sim.maxOrders = 5;
            sim.forceSpikeAt = 5.0;
        });
        assertTrue(h.completedCleanly(), "V8 should complete cleanly");
    }

    @Test
    public void testV9_EpochMismatch() {
        SimRunHandle h = harness.run(JCM_FILE, 40, SEED, sim -> {
            sim.injectEpochMismatchOn = "station_5";
        });
        assertTrue(h.completedCleanly(), "V9 should complete cleanly");
    }
}
