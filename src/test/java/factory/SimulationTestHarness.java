package factory;

import java.util.concurrent.TimeUnit;

/**
 * Thin harness that boots the simulation in-process for JUnit tests.
 *
 * Instead of shelling out via {@code ./gradlew run} and scraping logs,
 * this creates a {@link MainSimulator} programmatically, runs it to a
 * tick budget, and returns a {@link SimRunHandle} with typed access to
 * live CArtAgO artifact state — so tests can assert directly against
 * the simulation's own data structures.
 *
 * <p>Usage:
 * <pre>{@code
 * SimulationTestHarness harness = new SimulationTestHarness();
 * SimRunHandle h = harness.run("factory.jcm", 100, 42L);
 * assertTrue(h.completedCleanly());
 * }</pre>
 */
public class SimulationTestHarness {

    private static final long DEFAULT_TIMEOUT_SECONDS = 120;

    /**
     * Boots a simulation in-process, runs it for {@code tickBudget} ticks,
     * and returns a handle to the live state.
     *
     * @param jcmPath    path to the JaCaMo configuration file
     * @param tickBudget maximum ticks before the simulator shuts down cleanly
     * @param seed       random seed for reproducible runs (currently used by
     *                   the Python side's seeding_test.py discipline — wired
     *                   through here for future JVM-side seeded replay)
     * @return a handle to the completed simulation's live artifacts
     */
    public SimRunHandle run(String jcmPath, int tickBudget, long seed) {
        // Use a unique runId per invocation to avoid RunManager collisions
        // across tests running in the same JVM (forkEvery=1 prevents this
        // in practice, but belt-and-suspenders).
        int runId = (int) (seed & 0x7FFFFFFF);

        MainSimulator sim = new MainSimulator(runId, 50051 + (runId % 1000), jcmPath);
        sim.maxTicks = tickBudget;
        // TODO: wire seed into the simulator's RNG sources once the JVM
        // side has a unified seeding mechanism (currently only Python has
        // this via seeding_test.py).

        RunManager.registerSimulator(runId, sim);
        TelemetryHub.startServer(8080);

        // Start the TMC tick loop (runs on a daemon thread)
        sim.startTmcThreads();

        // Boot JaCaMo on a daemon thread so it doesn't block the test thread.
        java.util.concurrent.atomic.AtomicReference<Throwable> bootFailure = new java.util.concurrent.atomic.AtomicReference<>();
        Thread jacamoThread = new Thread(() -> {
            try {
                jacamo.infra.JaCaMoLauncher.main(new String[]{jcmPath});
            } catch (Throwable t) {
                bootFailure.set(t);
            }
        }, "JaCaMo-Launcher-" + runId);
        jacamoThread.setDaemon(true);
        jacamoThread.start();

        // Wait for the tick loop to reach its budget
        try {
            boolean completed = sim.waitForShutdown(DEFAULT_TIMEOUT_SECONDS, java.util.concurrent.TimeUnit.SECONDS);
            if (bootFailure.get() != null) {
                throw new RuntimeException("JaCaMo failed to boot", bootFailure.get());
            }
            if (!completed) {
                System.err.println("[SimulationTestHarness] WARNING: Simulation did not complete within "
                        + DEFAULT_TIMEOUT_SECONDS + "s timeout");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Test interrupted while waiting for simulation", e);
        }

        return new SimRunHandle(sim, runId, tickBudget);
    }
}
