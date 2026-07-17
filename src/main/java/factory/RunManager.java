package factory;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class RunManager {
    private static final Map<Integer, MainSimulator> SIMULATORS = new ConcurrentHashMap<>();

    public static MainSimulator getSimulator(int runId) {
        MainSimulator sim = SIMULATORS.get(runId);
        if (sim == null) {
            throw new IllegalStateException("Unknown runId: " + runId);
        }
        return sim;
    }

    public static void registerSimulator(int runId, MainSimulator sim) {
        SIMULATORS.put(runId, sim);
    }

    public static void launchPhase4(int runStartId, int runCount, int basePort, String phase4JcmDir, int maxTicks, double maxSimTime) {
        List<MainSimulator> simulators = new ArrayList<>(runCount);
        for (int i = runStartId; i < runStartId + runCount; i++) {
            MainSimulator sim = new MainSimulator(i, basePort + (i - runStartId), phase4JcmDir + "/factory_phase4.jcm");
            sim.maxTicks = maxTicks;
            sim.maxSimTime = maxSimTime;
            SIMULATORS.put(i, sim);
            simulators.add(sim);
        }

        // Initialize global Telemetry Hub
        TelemetryHub.startServer(8080);

        // Start TMC Threads asynchronously
        for (MainSimulator sim : simulators) {
            sim.startTmcThreads();
        }

        // Boot JaCaMo in a background thread or wait after boot
        System.out.println("Booting JaCaMo mega-topology...");
        Thread jacamoThread = new Thread(() -> {
            try {
                jacamo.infra.JaCaMoLauncher.main(new String[] { 
                    phase4JcmDir + "/factory_phase4.jcm", 
                    "--log-conf", "src/main/resources/logging.properties" 
                });
            } catch (Throwable e) {
                e.printStackTrace();
            }
        });
        jacamoThread.start();
        
        // Wait for all simulators to complete
        for (MainSimulator sim : simulators) {
            try {
                sim.waitForShutdown(1, java.util.concurrent.TimeUnit.DAYS);
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        }
        
        System.out.println("[phase4] All simulators finished. Exiting JVM.");
        System.exit(0);
    }
}