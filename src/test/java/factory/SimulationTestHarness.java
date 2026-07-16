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
        return run(jcmPath, tickBudget, seed, null);
    }

    public SimRunHandle run(String jcmPath, int tickBudget, long seed, java.util.function.Consumer<MainSimulator> config) {
        // Ensure clean ledger state by deleting existing DB files
        try {
            java.nio.file.Files.deleteIfExists(java.nio.file.Paths.get("factory_history.db"));
            java.nio.file.Files.deleteIfExists(java.nio.file.Paths.get("factory_history.db-shm"));
            java.nio.file.Files.deleteIfExists(java.nio.file.Paths.get("factory_history.db-wal"));
        } catch (java.io.IOException e) {
            System.err.println("Warning: failed to delete old ledger DB: " + e.getMessage());
        }

        // Use a unique runId per invocation to avoid RunManager collisions
        // across tests running in the same JVM (forkEvery=1 prevents this
        // in practice, but belt-and-suspenders).
        int runId = (int) (seed & 0x7FFFFFFF);
        int port = 50051 + (runId % 1000);

        Process pythonProcess = null;
        try {
            pythonProcess = new ProcessBuilder(
                ".venv/bin/python3", "-m", "physical_engine.sim_bridge_server", 
                "--port", String.valueOf(port), 
                "--run-id", String.valueOf(runId)
            ).inheritIO().start();
        } catch (Exception e) {
            System.err.println("Failed to start Python gRPC server: " + e.getMessage());
        }

        String activeJcmPath = jcmPath;
        try {
            java.nio.file.Path template = java.nio.file.Paths.get(jcmPath + ".template");
            if (java.nio.file.Files.exists(template)) {
                String content = new String(java.nio.file.Files.readAllBytes(template), java.nio.charset.StandardCharsets.UTF_8);
                content = content.replace("{{RUN_ID}}", String.valueOf(runId));
                java.nio.file.Path activeJcm = java.nio.file.Paths.get("factory_" + runId + ".jcm");
                java.nio.file.Files.write(activeJcm, content.getBytes(java.nio.charset.StandardCharsets.UTF_8));
                activeJcmPath = activeJcm.toString();
            }
        } catch (java.io.IOException e) {
            throw new RuntimeException("Failed to render JCM template", e);
        }

        MainSimulator sim = new MainSimulator(runId, port, activeJcmPath);
        sim.maxTicks = tickBudget;
        if (config != null) {
            config.accept(sim);
        }
        // TODO: wire seed into the simulator's RNG sources once the JVM
        // side has a unified seeding mechanism (currently only Python has
        // this via seeding_test.py).

        RunManager.registerSimulator(runId, sim);
        TelemetryHub.startServer(8080);
        try {
            TicketHttpServer.start(8081);
        } catch (java.io.IOException e) {
            e.printStackTrace();
        }

        // Start the TMC tick loop (runs on a daemon thread)
        sim.startTmcThreads();

        // Boot JaCaMo on a daemon thread so it doesn't block the test thread.
        java.util.concurrent.atomic.AtomicReference<Throwable> bootFailure = new java.util.concurrent.atomic.AtomicReference<>();
        final String finalJcmPath = activeJcmPath;
        Thread jacamoThread = new Thread(() -> {
            try {
                jacamo.infra.JaCaMoLauncher.main(new String[]{finalJcmPath});
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
                System.err.println("WARNING: Simulation did not complete within " + DEFAULT_TIMEOUT_SECONDS + "s timeout");
            }
            // Allow time for DatabaseArtifact's drainThread (500ms cadence) to flush to SQLite
            Thread.sleep(600);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("Test interrupted", e);
        } finally {
            if (pythonProcess != null) {
                pythonProcess.destroyForcibly();
            }
        }

        return new SimRunHandle(sim, runId, tickBudget);
    }
}
