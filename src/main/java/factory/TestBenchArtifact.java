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
    private final ConcurrentHashMap<String, ClientCall<BatchTestRequest, BatchTestResponse>>
        activeCalls = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, java.util.concurrent.CountDownLatch> latches = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, AtomicBoolean> completedCalls = new ConcurrentHashMap<>();

    public volatile StationSummary currentSummary = StationSummary.IDLE;
    public String stationId;

    void init(String stationId, int runId) {
        this.stationId = stationId;
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

        BatchTestRequest req = BatchTestRequest.newBuilder()
            .setStackId(stackId).setNumCells(numCells)
            .setOperatingTempK(tempK)
            .setInletPressureH2Bar(pH2Bar)
            .setInletPressureO2Bar(pO2Bar)
            .build();

        String corrId = UUID.randomUUID().toString();
        
        ClientCall<BatchTestRequest, BatchTestResponse> call =
            MainSimulator.INSTANCE.getGrpcBridge().getChannel().newCall(SimBridgeGrpc.getRunBatchTestMethod(), CallOptions.DEFAULT);
            
        activeCalls.put(corrId, call);
        completedCalls.put(corrId, new AtomicBoolean(false));
        java.util.concurrent.CountDownLatch latch = new java.util.concurrent.CountDownLatch(1);
        latches.put(corrId, latch);

        call.start(new ClientCall.Listener<>() {
            @Override
            public void onMessage(BatchTestResponse resp) {
                if (completedCalls.get(corrId).compareAndSet(false, true)) {
                    boolean passed = resp.getPassed();
                    int flags = resp.getFailureFlags();
                    currentSummary = passed
                        ? new StationSummary(StationStateEnum.STATION_IDLE, "", 0.0f)
                        : new StationSummary(StationStateEnum.STATION_DEFECT_DETECTED, stackId, 1.0f);
                    try {
                        execInternalOp("handleResult", corrId, passed, flags);
                    } catch(Exception e) { e.printStackTrace(); }
                    latch.countDown();
                }
            }
            @Override
            public void onClose(Status status, Metadata trailers) {
                activeCalls.remove(corrId);
                if (!status.isOk()) {
                    if (completedCalls.get(corrId).compareAndSet(false, true)) {
                        currentSummary = new StationSummary(StationStateEnum.STATION_OFFLINE, stackId, 0.0f);
                        try {
                            execInternalOp("handleResult", corrId, false, 0x10);
                        } catch(Exception e) { e.printStackTrace(); }
                        latch.countDown();
                    }
                }
            }
        }, new Metadata());

        call.sendMessage(req);
        call.halfClose();
        call.request(1);

        try {
            latch.await(30, java.util.concurrent.TimeUnit.SECONDS);
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
            if (completedCalls.get(corrId).compareAndSet(false, true)) {
                currentSummary = StationSummary.IDLE;
                try {
                    execInternalOp("handleResult", corrId, false, 0x10);
                } catch(Exception e) {}
                java.util.concurrent.CountDownLatch latch = latches.get(corrId);
                if (latch != null) latch.countDown();
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
            execLinkedOp(timerArtifactId, "cancelTimer", orderId);
        } catch (Exception e) {}
        log("Station " + stationId + " released for order " + orderId + " — currentSummary reset to IDLE");
    }


}
