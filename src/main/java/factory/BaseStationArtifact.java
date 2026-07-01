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

    void init(String stationId, int stationIndex, double tMean_s, double tStd_s, double defectRate, int runId) {
        this.stationId = stationId;
        this.tMean_s = tMean_s;
        this.tStd_s = tStd_s;
        this.defectRate = defectRate;
        this.runId = runId;
        long seed = stationId.hashCode() ^ runId;
        this.rng = new SplittableRandom(seed);
        
        MainSimulator.INSTANCE.stationArtifacts.add(this);
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
        if (MainSimulator.INSTANCE.forceAbortStation != null && agentName.equals(MainSimulator.INSTANCE.forceAbortStation) &&
            MainSimulator.INSTANCE.forceAbortOrder != null && orderId.contains(MainSimulator.INSTANCE.forceAbortOrder)) {
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
        double currentSimTime = MainSimulator.INSTANCE.getCurrentTime();
        double requestedNextTime = currentSimTime + tProc;
        
        MainSimulator.INSTANCE.submitNER(agentId, requestedNextTime);
        
        // Wait for time advance grant. 
        // For now, we will suspend the operation and wait for MainSimulator to resume it.
        // We will store the suspension id.
        String suspendId = "wait_" + agentId + "_" + requestedNextTime;
        // The await and resume mechanism will be handled by MainSimulator's TAG, 
        // but for now we'll do a simple await.
        // Note: Phase 2 doesn't implement the full TAG agent resumption yet.
        // We'll use a sleep for now if we can't do it, or just return immediately.
        // Wait, Phase2.md: "approximated by submitting a NER to MainSimulator with requestedNextTime = currentSimTime + tProc and await()-ing the TimeAdvanceGrant callback."
        // If we don't have TimeAdvanceGrant, we can just block on a CountDownLatch or use CArtAgO await.
        
        // Hack: block in a tight loop for sim time to advance
        while (MainSimulator.INSTANCE.getCurrentTime() < requestedNextTime) {
            try { Thread.sleep(10); } catch (InterruptedException e) {}
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
            execLinkedOp(timerArtifactId, "cancelTimer", orderId);
        } catch (Exception e) {}
        log("Station " + stationId + " released for order " + orderId + " — currentSummary reset to IDLE");
    }
}
