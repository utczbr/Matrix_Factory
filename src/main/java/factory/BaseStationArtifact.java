package factory;

import cartago.*;
import java.util.SplittableRandom;
import factory.SimBridgeProto.StationStateEnum;

public class BaseStationArtifact extends Artifact {
    public String stationId;
    public volatile StationSummary currentSummary = StationSummary.IDLE;

    private double tMean_s;
    private double tStd_s;
    private double defectRate;
    private SplittableRandom rng;
    private int runId;
    private int recipeStep;
    private double baseCost;

    @OPERATION
    void init(String stationId, int stationIndex, double tMean_s, double tStd_s, double defectRate, int runId, int recipeStep, double baseCost) {
        this.stationId = stationId;
        this.tMean_s = tMean_s;
        this.tStd_s = tStd_s;
        this.defectRate = defectRate;
        this.runId = runId;
        this.recipeStep = recipeStep;
        this.baseCost = baseCost;
        long seed = stationId.hashCode() ^ runId;
        this.rng = new SplittableRandom(seed);
        
        defineObsProperty("my_recipe_step", recipeStep);
        defineObsProperty("current_processing_cost", baseCost);

        RunManager.getSimulator(runId).stationArtifacts.add(this);
    }

    @OPERATION
    public void claimStation(String orderId, OpFeedbackParam<String> result) {
        if (currentSummary.state() != StationStateEnum.STATION_IDLE) {
            failed("Station is not idle");
            return;
        }
        currentSummary = new StationSummary(StationStateEnum.STATION_PROVISIONAL_LOCK, orderId, 0.0f);
        result.set("claimed");

        String agentName = getOpUserName();
        if (RunManager.getSimulator(runId).forceAbortStation != null
                && agentName.equals(RunManager.getSimulator(runId).forceAbortStation) &&
                RunManager.getSimulator(runId).forceAbortOrder != null
                && orderId.contains(RunManager.getSimulator(runId).forceAbortOrder)) {
            signal("abort_current_operation", orderId);
            log("Test Hook: injected abort_current_operation for " + orderId + " at " + agentName);
        }
    }

    @OPERATION
    public void processOrder(String orderId, OpFeedbackParam<String> result) {
        if (currentSummary.state() != StationStateEnum.STATION_PROVISIONAL_LOCK ||
                !currentSummary.activeOrderId().equals(orderId)) {
            failed("Station not locked for this order");
            return;
        }
        currentSummary = new StationSummary(StationStateEnum.STATION_BUSY_PROCESSING, orderId, 0.0f);

        double tProc = tMean_s + rng.nextGaussian() * tStd_s;
        tProc = Math.max(tMean_s * 0.1, Math.min(tProc, tMean_s * 3.0));

        boolean defect = rng.nextDouble() < defectRate;

        String agentId = getOpUserName();
        double currentSimTime = RunManager.getSimulator(runId).getCurrentTime();
        double requestedNextTime = currentSimTime + tProc;

        RunManager.getSimulator(runId).submitNER(agentId, requestedNextTime);

        // Wait for time advance grant.
        // For now, we will suspend the operation and wait for MainSimulator to resume
        // it.
        // We will store the suspension id.
        String suspendId = "wait_" + agentId + "_" + requestedNextTime;
        // The await and resume mechanism will be handled by MainSimulator's TAG,
        // but for now we'll do a simple await.
        // Note: Phase 2 doesn't implement the full TAG agent resumption yet.
        // We'll use a sleep for now if we can't do it, or just return immediately.
        // Wait, Phase2.md: "approximated by submitting a NER to MainSimulator with
        // requestedNextTime = currentSimTime + tProc and await()-ing the
        // TimeAdvanceGrant callback."
        // If we don't have TimeAdvanceGrant, we can just block on a CountDownLatch or
        // use CArtAgO await.

        // Hack: block in a tight loop for sim time to advance
        while (RunManager.getSimulator(runId).getCurrentTime() < requestedNextTime) {
            try {
                Thread.sleep(10);
            } catch (InterruptedException e) {
            }
        }
        RunManager.getSimulator(runId).removeNER(agentId);

        // Log this station's process variation to the manufacturing-quality
        // bridge so Station 5 can later reconstruct the stack's cumulative
        // quality profile (doc2 §2 / digital-twin fidelity requirement).
        // Best-effort: a lookup/log failure here must not fail the order.
        try {
            ArtifactId databaseArtifactId = lookupArtifact("database");
            execLinkedOp(databaseArtifactId, "recordStationQuality",
                    runId, orderId, stationId, defect, tProc, tMean_s, currentSimTime);
        } catch (Exception e) {
            log("Station " + stationId + ": failed to log quality profile for " + orderId + ": " + e);
        }

        currentSummary = new StationSummary(StationStateEnum.STATION_IDLE, "", 0.0f);
        result.set(defect ? "defect" : "ok");
    }

    @OPERATION
    public void setStationOffline() {
        currentSummary = StationSummary.OFFLINE;
        log("Station " + stationId + " set to OFFLINE (Phase 1 Suspend)");
    }

    @OPERATION
    public void releaseStation(String orderId) {
        currentSummary = StationSummary.IDLE;
        try {
            ArtifactId timerArtifactId = lookupArtifact("timer_artifact");
            execLinkedOp(timerArtifactId, "cancelTimer", orderId, getOpUserName());
        } catch (Exception e) {
        }
        log("Station " + stationId + " released for order " + orderId + " — currentSummary reset to IDLE");
    }
}
