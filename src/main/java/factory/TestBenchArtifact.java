package factory;

import cartago.*;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.ClientCall;
import io.grpc.CallOptions;
import io.grpc.Metadata;
import io.grpc.Status;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import factory.SimBridgeProto.BatchTestRequest;
import factory.SimBridgeProto.BatchTestResponse;
import factory.SimBridgeProto.StationStateEnum;

public class TestBenchArtifact extends Artifact {
    private final ConcurrentHashMap<String, ClientCall<BatchTestRequest, BatchTestResponse>> activeCalls = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, java.util.concurrent.CountDownLatch> latches = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, AtomicBoolean> completedCalls = new ConcurrentHashMap<>();

    public volatile StationSummary currentSummary = StationSummary.IDLE;
    // Last RunBatchTest result — surfaced to telemetry (MainSimulator) instead
    // of being dropped after the CArtAgO operation returns. Deliberately
    // separate from currentSummary: currentSummary's DEFECT_DETECTED value is
    // reset to IDLE by releaseStation() almost immediately (required so the
    // station remains claimable for the next order), so it is not a reliable
    // channel for "what was the outcome of the last test". These fields are
    // the reliable channel and are never reset by releaseStation().
    public volatile int lastFailureFlags = 0;
    public volatile boolean lastTestPassed = false;
    public volatile boolean hasRunAnyTest = false;
    public volatile String lastTestedStackId = "";
    public volatile java.util.List<Double> lastMeasuredVoltages = java.util.List.of();
    public String stationId;
    private int runId;
    private int recipeStep;
    private double baseCost;

    @OPERATION
    void init(String stationId, int runId, int recipeStep, double baseCost) {
        this.stationId = stationId;
        this.runId = runId;
        this.recipeStep = recipeStep;
        this.baseCost = baseCost;
        
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
    }

    @OPERATION
    public void processOrder(String stackId, OpFeedbackParam<String> result) {
        if (currentSummary.state() != StationStateEnum.STATION_PROVISIONAL_LOCK ||
                !currentSummary.activeOrderId().equals(stackId)) {
            failed("Station not locked for this order");
            return;
        }
        currentSummary = new StationSummary(StationStateEnum.STATION_BUSY_PROCESSING, stackId, 0.0f);

        int numCells = 100;
        double tempK = 350.0;
        double pH2Bar = 2.0;
        double pO2Bar = 2.0;

        // --- Manufacturing-quality bridge -------------------------------
        // Fetch this stack's cumulative quality profile (defects + process
        // variance logged by Stations 1-4 via BaseStationArtifact) and
        // translate it into physical penalties carried on the request, so
        // the polarization sweep run by the Python physics engine actually
        // reflects what happened upstream instead of testing every stack
        // under identical, idealized conditions.
        double rInternalPenalty = 0.0;
        double activityDerate = 0.0;
        try {
            ArtifactId databaseArtifactId = lookupArtifact("database");
            OpFeedbackParam<Integer> defectCountParam = new OpFeedbackParam<>();
            OpFeedbackParam<Integer> stationsVisitedParam = new OpFeedbackParam<>();
            OpFeedbackParam<Double> varianceRatioParam = new OpFeedbackParam<>();
            execLinkedOp(databaseArtifactId, "getQualityProfile", stackId,
                    defectCountParam, stationsVisitedParam, varianceRatioParam);
            int defectCount = defectCountParam.get();
            double cumulativeVarianceRatio = varianceRatioParam.get();

            // Each logged defect is a meaningful manufacturing fault (bad MEA
            // seal, catalyst deposition miss, plate-stamping tolerance,
            // assembly misalignment, ...): +0.08 Ω·cm² each is enough on its
            // own to push a stack over the OHMIC_DEGRADATION_ETA_V=0.35V
            // threshold at high current density, matching how a single
            // serious defect can fail a real end-of-line test.
            rInternalPenalty += defectCount * 0.08;

            // Cumulative processing-time variance (stations that ran hot/cold
            // relative to their mean, even without tripping the boolean
            // defect flag) is a proxy for assembly imprecision: a smaller,
            // continuous resistance penalty.
            rInternalPenalty += cumulativeVarianceRatio * 0.02;

            // Defects concentrated in MEA prep / catalytic deposition
            // (Stations 1-2) plausibly reduce active catalyst area or clog
            // flow fields — modeled as reactant-activity derating so those
            // stacks can trip LOW_ACTIVATION instead of only ohmic failures.
            activityDerate = Math.min(0.6, defectCount * 0.15);
        } catch (Exception e) {
            log("Station " + stationId + ": failed to fetch quality profile for " + stackId
                    + " — testing with zero quality penalty: " + e);
        }

        BatchTestRequest req = BatchTestRequest.newBuilder()
                .setStackId(stackId).setNumCells(numCells)
                .setOperatingTempK(tempK)
                .setInletPressureH2Bar(pH2Bar)
                .setInletPressureO2Bar(pO2Bar)
                .setRInternalPenaltyOhmCm2(rInternalPenalty)
                .setActivityDerateFraction(activityDerate)
                .build();

        String corrId = UUID.randomUUID().toString();

        ClientCall<BatchTestRequest, BatchTestResponse> call = RunManager.getSimulator(runId).getGrpcBridge().getChannel()
                .newCall(SimBridgeGrpc.getRunBatchTestMethod(), CallOptions.DEFAULT);

        activeCalls.put(corrId, call);
        completedCalls.put(corrId, new AtomicBoolean(false));
        java.util.concurrent.CountDownLatch latch = new java.util.concurrent.CountDownLatch(1);
        latches.put(corrId, latch);

        call.start(new ClientCall.Listener<>() {
            @Override
            public void onMessage(BatchTestResponse resp) {
                // corrId may already have been evicted from completedCalls if
                // processOrder timed out and cleaned up before this stale
                // callback arrived — null-guard instead of assuming presence.
                AtomicBoolean completedFlag = completedCalls.get(corrId);
                if (completedFlag != null && completedFlag.compareAndSet(false, true)) {
                    boolean passed = resp.getPassed();
                    int flags = resp.getFailureFlags();
                    lastFailureFlags = flags;
                    lastTestPassed = passed;
                    hasRunAnyTest = true;
                    lastTestedStackId = stackId;
                    lastMeasuredVoltages = java.util.List.copyOf(resp.getMeasuredVoltagesList());
                    currentSummary = passed
                            ? new StationSummary(StationStateEnum.STATION_IDLE, "", 0.0f)
                            : new StationSummary(StationStateEnum.STATION_DEFECT_DETECTED, stackId, 1.0f);
                    try {
                        execInternalOp("handleResult", corrId, passed, flags);
                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                    java.util.concurrent.CountDownLatch l = latches.get(corrId);
                    if (l != null) l.countDown();
                }
            }

            @Override
            public void onClose(Status status, Metadata trailers) {
                activeCalls.remove(corrId);
                if (!status.isOk()) {
                    AtomicBoolean completedFlag = completedCalls.get(corrId);
                    if (completedFlag != null && completedFlag.compareAndSet(false, true)) {
                        currentSummary = new StationSummary(StationStateEnum.STATION_OFFLINE, stackId, 0.0f);
                        lastFailureFlags = 0x10; // SOLVER_DID_NOT_CONVERGE, reused as "comms failure"
                        lastTestPassed = false;
                        hasRunAnyTest = true;
                        lastTestedStackId = stackId;
                        try {
                            execInternalOp("handleResult", corrId, false, 0x10);
                        } catch (Exception e) {
                            e.printStackTrace();
                        }
                        java.util.concurrent.CountDownLatch l = latches.get(corrId);
                        if (l != null) l.countDown();
                    }
                }
            }
        }, new Metadata());

        call.sendMessage(req);
        call.halfClose();
        call.request(1);

        try {
            boolean completedInTime = latch.await(30, java.util.concurrent.TimeUnit.SECONDS);
            if (!completedInTime) {
                log("Station " + stationId + ": RunBatchTest timed out after 30s (corrId="
                        + corrId + ") — cancelling RPC instead of abandoning it");
                ClientCall<BatchTestRequest, BatchTestResponse> pending = activeCalls.get(corrId);
                if (pending != null) {
                    pending.cancel("client-side 30s timeout", null);
                }
                // Give cancellation a short window to land and drive onClose,
                // which performs its own map cleanup + latch countdown.
                latch.await(2, java.util.concurrent.TimeUnit.SECONDS);
                // If onClose still hasn't fired (e.g. cancel() itself was
                // swallowed), claim completion here so callback threads that
                // arrive later see the entry as already resolved rather than
                // finding it removed out from under them.
                AtomicBoolean completedFlag = completedCalls.get(corrId);
                if (completedFlag != null && completedFlag.compareAndSet(false, true)) {
                    currentSummary = new StationSummary(StationStateEnum.STATION_OFFLINE, stackId, 0.0f);
                    lastFailureFlags = 0x10;
                    lastTestPassed = false;
                    hasRunAnyTest = true;
                    lastTestedStackId = stackId;
                }
            }
        } catch (InterruptedException e) {
            log("ADACOR drop_intention received — cancelling pending gRPC call (Interrupted)");
            cancelPendingRpc();
            Thread.currentThread().interrupt();
        }

        activeCalls.remove(corrId);
        completedCalls.remove(corrId);
        latches.remove(corrId);

        result.set(currentSummary.state() == StationStateEnum.STATION_IDLE ? "ok" : "defect");
    }

    @INTERNAL_OPERATION
    void handleResult(String corrId, boolean passed, int flags) {
        signal("test_complete_" + corrId, passed, flags);
    }

    public void cancelPendingRpc() {
        activeCalls.forEach((corrId, call) -> {
            call.cancel("ADACOR suspend", null);
            AtomicBoolean completedFlag = completedCalls.get(corrId);
            if (completedFlag != null && completedFlag.compareAndSet(false, true)) {
                currentSummary = StationSummary.IDLE;
                try {
                    execInternalOp("handleResult", corrId, false, 0x10);
                } catch (Exception e) {
                }
                java.util.concurrent.CountDownLatch latch = latches.get(corrId);
                if (latch != null)
                    latch.countDown();
            }
        });
        activeCalls.clear();
        completedCalls.clear();
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
