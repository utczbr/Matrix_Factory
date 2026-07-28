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

    private final java.util.concurrent.ConcurrentHashMap<String, Double> setpoints = new java.util.concurrent.ConcurrentHashMap<>();

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

        // Populate nominal setpoints
        if ("S1".equals(stationId) || recipeStep == 1) {
            setpoints.put("t_press_k", StationNominalParams.S1_T_PRESS_NOMINAL_K);
            setpoints.put("dwell_time_s", StationNominalParams.S1_DWELL_TIME_NOMINAL_S);
        } else if ("S2".equals(stationId) || recipeStep == 2) {
            setpoints.put("v_coat_m_s", StationNominalParams.S2_V_COAT_NOMINAL_M_S);
            setpoints.put("mu_slurry_pa_s", StationNominalParams.S2_MU_SLURRY_NOMINAL_PA_S);
        } else if ("S3".equals(stationId) || recipeStep == 3) {
            setpoints.put("press_force_kn", StationNominalParams.S3_PRESS_FORCE_NOMINAL_KN);
            setpoints.put("w0_initial_wear", 0.0);
        } else if ("S4".equals(stationId) || recipeStep == 4) {
            for (int i = 0; i < 4; i++) {
                setpoints.put("torque_bolt_" + i, StationNominalParams.S4_TORQUE_NOMINAL_NM);
            }
            for (int i = 0; i < 8; i++) {
                setpoints.put("mu_friction_" + i, 0.15);
            }
        }
        
        defineObsProperty("my_recipe_step", recipeStep);
        defineObsProperty("current_processing_cost", baseCost);

        RunManager.getSimulator(runId).stationArtifacts.add(this);
    }

    @OPERATION
    public void adjustSetpoint(String paramName, double value) {
        setpoints.put(paramName, value);
        log("Station " + stationId + ": Setpoint " + paramName + " adjusted to " + value);
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

        double tProc = tMean_s;
        boolean defect = false;
        double ecsaRatio = 1.0;
        double damageIndex = 0.0;
        double pClampMpa = 4.25;
        double gdlPorosity = 0.78;
        boolean callSuccess = false;

        GrpcClientBridge bridge = RunManager.getSimulator(runId).getGrpcBridge();
        if (bridge != null) {
            try {
                SimBridgeProto.StationProcessRequest.Builder reqB = SimBridgeProto.StationProcessRequest.newBuilder()
                        .setStationId(stationId)
                        .setOrderId(orderId)
                        .setKTime(1.0);

                if ("S1".equals(stationId) || recipeStep == 1) {
                    reqB.setStation1(SimBridgeProto.Station1Params.newBuilder()
                            .setTPressK(setpoints.getOrDefault("t_press_k", StationNominalParams.S1_T_PRESS_NOMINAL_K))
                            .setDwellTimeS(setpoints.getOrDefault("dwell_time_s", StationNominalParams.S1_DWELL_TIME_NOMINAL_S))
                            .build());
                } else if ("S2".equals(stationId) || recipeStep == 2) {
                    reqB.setStation2(SimBridgeProto.Station2Params.newBuilder()
                            .setVCoatMS(setpoints.getOrDefault("v_coat_m_s", StationNominalParams.S2_V_COAT_NOMINAL_M_S))
                            .setMuSlurryPaS(setpoints.getOrDefault("mu_slurry_pa_s", StationNominalParams.S2_MU_SLURRY_NOMINAL_PA_S))
                            .build());
                } else if ("S3".equals(stationId) || recipeStep == 3) {
                    reqB.setStation3(SimBridgeProto.Station3Params.newBuilder()
                            .setPressForceKn(setpoints.getOrDefault("press_force_kn", StationNominalParams.S3_PRESS_FORCE_NOMINAL_KN))
                            .setW0InitialWear(setpoints.getOrDefault("w0_initial_wear", 0.0))
                            .build());
                } else if ("S4".equals(stationId) || recipeStep == 4) {
                    SimBridgeProto.Station4Params.Builder s4b = SimBridgeProto.Station4Params.newBuilder();
                    for (int i = 0; i < 4; i++) {
                        s4b.addAppliedTorquesNm(setpoints.getOrDefault("torque_bolt_" + i, StationNominalParams.S4_TORQUE_NOMINAL_NM));
                    }
                    for (int i = 0; i < 8; i++) {
                        s4b.addFrictionCoefficients(setpoints.getOrDefault("mu_friction_" + i, 0.15));
                    }
                    reqB.setStation4(s4b.build());
                }

                SimBridgeProto.StationProcessResponse response = bridge.simulateStationProcess(reqB.build());
                if (response != null) {
                    tProc = response.getProcTimeS();
                    defect = response.getIsDefective();
                    if ("S2".equals(stationId) || recipeStep == 2) {
                        ecsaRatio = response.getEcsaRatio();
                    } else if ("S3".equals(stationId) || recipeStep == 3) {
                        damageIndex = response.getDamageIndex();
                    } else if ("S4".equals(stationId) || recipeStep == 4) {
                        pClampMpa = response.getPClampMpa();
                        gdlPorosity = response.getGdlPorosity();
                    }
                    callSuccess = true;
                }
            } catch (Exception e) {
                // Fallback to legacy Gaussian/Bernoulli model
            }
        }

        if (!callSuccess) {
            tProc = tMean_s + rng.nextGaussian() * tStd_s;
            tProc = Math.max(tMean_s * 0.1, Math.min(tProc, tMean_s * 3.0));
            defect = rng.nextDouble() < defectRate;
            if ("S2".equals(stationId) || recipeStep == 2) {
                ecsaRatio = defect ? 0.65 : 1.0;
            } else if ("S3".equals(stationId) || recipeStep == 3) {
                damageIndex = defect ? 1.35 : 0.86;
            } else if ("S4".equals(stationId) || recipeStep == 4) {
                pClampMpa = defect ? 2.50 : 4.22;
                gdlPorosity = defect ? 0.82 : 0.772;
            }
        }

        String agentId = getOpUserName();
        double currentSimTime = RunManager.getSimulator(runId).getCurrentTime();
        double requestedNextTime = currentSimTime + tProc;

        java.util.concurrent.CountDownLatch tagLatch = new java.util.concurrent.CountDownLatch(1);
        RunManager.getSimulator(runId).submitNER(agentId, requestedNextTime, tagLatch);

        try {
            await(new cartago.IBlockingCmd() {
                @Override
                public void exec() {
                    try {
                        tagLatch.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
            });
        } catch (Exception e) {}

        RunManager.getSimulator(runId).removeNER(agentId);

        // Log this station's process variation to the manufacturing-quality
        // bridge so Station 5 can later reconstruct the stack's cumulative
        // quality profile (doc2 §2 / digital-twin fidelity requirement).
        // Best-effort: a lookup/log failure here must not fail the order.
        try {
            ArtifactId databaseArtifactId = lookupArtifact("database");
            execLinkedOp(databaseArtifactId, "recordStationQuality",
                    runId, orderId, stationId, defect, tProc, tMean_s, currentSimTime);

            execLinkedOp(databaseArtifactId, "recordMechanisticQuality",
                    orderId, ecsaRatio, damageIndex, pClampMpa, gdlPorosity);
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
