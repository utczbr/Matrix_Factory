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

    public static void launchPhase4(int runCount, int basePort, String phase4JcmDir) {
        List<MainSimulator> simulators = new ArrayList<>(runCount);
        for (int i = 0; i < runCount; i++) {
            MainSimulator sim = new MainSimulator(i, basePort + i, phase4JcmDir + "/factory_phase4.jcm");
            SIMULATORS.put(i, sim);
            simulators.add(sim);
        }

        // Initialize global Telemetry Hub
        TelemetryHub.startServer(8080);

        // Start TMC Threads asynchronously
        for (MainSimulator sim : simulators) {
            sim.startTmcThreads();
        }

        // Boot JaCaMo exactly once
        System.out.println("Booting JaCaMo mega-topology...");
        try {
            jacamo.infra.JaCaMoLauncher.main(new String[] { phase4JcmDir + "/factory_phase4.jcm" });
        } catch (Throwable e) {
            e.printStackTrace();
        }
    }
}