package factory;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class MainSimulator {
    private static final Logger logger = LoggerFactory.getLogger(MainSimulator.class);

    // TMC State
    private double currentTime = 0.0;
    private final AtomicInteger schemaEpoch = new AtomicInteger(0);
    private final AtomicLong sequenceNumber = new AtomicLong(1);
    public final AtomicLong droppedNerCount = new AtomicLong(0);

    private volatile String activeOrgSchema = "centralized";
    public volatile OrgSchemaTransition activeTransition = null;

    public final int runId;

    int maxTicks = -1;  // package-private for test harness access
    private boolean logEpochs = false;

    public String forceAbortStation = null;
    public String forceAbortOrder = null;

    // Test Hooks
    public int maxOrders = 5;
    public boolean cnpSlowAccept = false;
    public long ttl = -1;
    public String priceSeriesFile = null;
    public Double forceSpikeAt = null;
    public boolean gridStress = false;
    public String lockHoldOrders = null;
    public String blockAckFrom = null;
    public String injectEpochMismatchOn = null;
    public String logBrfAgent = null;
    public boolean traceMessages = false;

    // NER Quorum
    private final ConcurrentHashMap<String, NEREntry> nerRegistry = new ConcurrentHashMap<>();
    private CountDownLatch nerLatch;
    private final long TICK_QUORUM_TIMEOUT_MS = 10;
    private final double MIN_DT = 0.01;
    private final double MAX_DT = 1.0;

    // ROOT CAUSE FIX: this was 8, matching a stale "order_manager + 5
    // stations + 2 AMRs" comment from an earlier single-order-manager phase.
    // The current roster (factory.jcm) is 5 concurrent order holons + 5
    // stations + 2 AMRs + 1 supervisor (which also runs startTimer for its
    // own ADACOR phase timers) = 13. This count only sizes a best-effort
    // CountDownLatch quorum (a 10ms miss just falls through to "proceed
    // anyway" and bumps droppedNerCount), so the old value didn't hang
    // anything — it just meant the tick loop almost never saw a full
    // quorum and fell back to the timeout path far more than intended.
    private int registeredAgentCount = 13; // 5 order holons + 5 stations + 2 AMRs + 1 supervisor

    private boolean shutdown = false;
    private final CountDownLatch shutdownLatch = new CountDownLatch(1);

    // Artifact references (populated when artifacts init)
    public Object timerArtifact; 
    public Object energyPriceArtifact; 
    public Object telemetryArtifact; 
    public Object amrArtifact; 
    public final List<Object> stationArtifacts = new CopyOnWriteArrayList<>(); 
    public Object utilitySystemArtifact; 
    public Object supervisorArtifact;
    public Object databaseArtifact;

    public final AtomicReference<TelemetryFrameSnapshot> telemetryRef = new AtomicReference<>();

    private final GrpcClientBridge grpcBridge;
    private final String jcmPath;

    public MainSimulator(int runId, int port) {
        this(runId, port, "factory.jcm");
    }

    public MainSimulator(int runId, int port, String jcmPath) {
        this.runId = runId;
        this.jcmPath = jcmPath;
        this.grpcBridge = new GrpcClientBridge(port);
    }

    public String getJcmPath() {
        return jcmPath;
    }

    public static void main(String[] args) {
        java.util.List<String> posArgs = new java.util.ArrayList<>();
        boolean phase4 = false;
        int runCount = 30;
        int basePort = 50051;
        String phase4JcmDir = null;
        for (String arg : args) {
            if ("--phase4".equals(arg)) {
                phase4 = true;
            } else if (arg.startsWith("--run-count=")) {
                runCount = Integer.parseInt(arg.substring("--run-count=".length()));
            } else if (arg.startsWith("--base-port=")) {
                basePort = Integer.parseInt(arg.substring("--base-port=".length()));
            } else if (arg.startsWith("--phase4-jcm-dir=")) {
                phase4JcmDir = arg.substring("--phase4-jcm-dir=".length());
            } else if (!arg.startsWith("--")) {
                posArgs.add(arg);
            }
        }

        if (phase4) {
            RunManager.launchPhase4(runCount, basePort, phase4JcmDir);
            return;
        }

        int runId = posArgs.size() > 0 ? Integer.parseInt(posArgs.get(0)) : 0;
        int port = posArgs.size() > 1 ? Integer.parseInt(posArgs.get(1)) : 50051;

        // Note: For Phase 1-3 single runs, we fallback to JaCaMoLauncher directly.
        // We will just create one and run it.
        MainSimulator sim = new MainSimulator(runId, port);
        
        for (String arg : args) {
            if (arg.startsWith("--max-ticks=")) {
                sim.maxTicks = Integer.parseInt(arg.substring("--max-ticks=".length()));
            } else if (arg.equals("--log-epochs")) {
                sim.logEpochs = true;
            } else if (arg.startsWith("--force-abort-on=")) {
                sim.forceAbortStation = arg.substring("--force-abort-on=".length());
            } else if (arg.startsWith("--order=")) {
                sim.forceAbortOrder = arg.substring("--order=".length());
            } else if (arg.startsWith("--max-orders=")) {
                sim.maxOrders = Integer.parseInt(arg.substring("--max-orders=".length()));
            } else if (arg.equals("--cnp-slow-accept")) {
                sim.cnpSlowAccept = true;
            } else if (arg.startsWith("--ttl=")) {
                sim.ttl = Long.parseLong(arg.substring("--ttl=".length()));
            } else if (arg.startsWith("--price-series=")) {
                sim.priceSeriesFile = arg.substring("--price-series=".length());
            } else if (arg.startsWith("--force-spike-at=")) {
                sim.forceSpikeAt = Double.parseDouble(arg.substring("--force-spike-at=".length()));
            } else if (arg.equals("--grid-stress")) {
                sim.gridStress = true;
            } else if (arg.startsWith("--lock-hold-orders=")) {
                sim.lockHoldOrders = arg.substring("--lock-hold-orders=".length());
            } else if (arg.startsWith("--block-ack-from=")) {
                sim.blockAckFrom = arg.substring("--block-ack-from=".length());
            } else if (arg.startsWith("--inject-epoch-mismatch-on=")) {
                sim.injectEpochMismatchOn = arg.substring("--inject-epoch-mismatch-on=".length());
            } else if (arg.startsWith("--log-brf=")) {
                sim.logBrfAgent = arg.substring("--log-brf=".length());
            } else if (arg.equals("--trace-message") || arg.equals("--trace-messages")) {
                sim.traceMessages = true;
            }
        }
        
        // Register it for single run
        RunManager.registerSimulator(runId, sim);
        TelemetryHub.startServer(8080);
        try {
            TicketHttpServer.start(8081);
        } catch (java.io.IOException e) {
            e.printStackTrace();
        }

        try {
            sim.startTmcThreads();
            jacamo.infra.JaCaMoLauncher.main(new String[] { sim.getJcmPath() });
        } catch (Exception e) {
            logger.error("Simulation failed", e);
        }
    }

    public void startTmcThreads() {
        Thread tickLoop = new Thread(this::tickLoop, "TMC-TickLoop-" + runId);
        tickLoop.setDaemon(true);
        tickLoop.start();
    }

    public void submitNER(String agentId, double requestedNextTime) {
        nerRegistry.put(agentId, new NEREntry(agentId, requestedNextTime));
        if (nerLatch != null) {
            nerLatch.countDown();
        }
    }

    public void removeNER(String agentId) {
        nerRegistry.remove(agentId);
    }

    public double getCurrentTime() {
        return currentTime;
    }

    public GrpcClientBridge getGrpcBridge() {
        return grpcBridge;
    }

    private void tickLoop() {
        // Wait for artifacts to register themselves
        try {
            grpcBridge.pollUntilReady();
            logger.info("Waiting for all artifacts to register in run " + runId + "...");
            while (timerArtifact == null || energyPriceArtifact == null || telemetryArtifact == null ||
                    amrArtifact == null || stationArtifacts.size() < 5 || utilitySystemArtifact == null ||
                    supervisorArtifact == null) {
                Thread.sleep(500);
            }

            ((SupervisorArtifact) supervisorArtifact).setMainSimulator(this);
            ((EnergyPriceArtifact) energyPriceArtifact).updatePrice(0.0);
            schemaEpoch.set(0);

            logger.info("Waiting for JaCaMo agents to spawn for run " + runId + "...");
            Thread.sleep(5000); 
        } catch (InterruptedException e) {
            return;
        }

        int ticks = 0;
        while (!shutdown) {
            if (maxTicks > 0 && ticks >= maxTicks) {
                logger.info("Max ticks reached (" + maxTicks + "). Shutting down cleanly.");
                shutdown = true;
                shutdownLatch.countDown();
                return;
            }
            try {
                nerLatch = new CountDownLatch(registeredAgentCount);
                if (!nerLatch.await(TICK_QUORUM_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
                    droppedNerCount.incrementAndGet();
                    logger.trace("NER Quorum timeout. Proceeding anyway.");
                }

                double computedDt = MAX_DT;
                for (NEREntry entry : nerRegistry.values()) {
                    double reqDt = entry.requestedNextTime() - currentTime;
                    if (reqDt < computedDt) {
                        computedDt = reqDt;
                    }
                }
                computedDt = Math.max(MIN_DT, Math.min(MAX_DT, computedDt));

                final int currentEpoch = schemaEpoch.get();

                SimBridgeProto.StepReady ready = grpcBridge.advanceTime(currentTime, computedDt, currentEpoch);
                ProtoIndex.validateVectorLength(ready.getStateVectorCount());

                currentTime = ready.getTargetTime();

                ((TimerArtifact) timerArtifact).evaluateTTLs(currentTime);
                ((EnergyPriceArtifact) energyPriceArtifact).updatePrice(currentTime);
                ((AMRArtifact) amrArtifact).updatePositions(currentTime, computedDt);
                ((UtilitySystemArtifact) utilitySystemArtifact).updateFromStateVector(ready, currentTime);

                TelemetryFrameSnapshot snap = assembleTelemetryFrame(ready, currentEpoch);
                telemetryRef.set(snap);

                if (logEpochs) {
                    try {
                        SimBridgeProto.TelemetryFrame parsedFrame = SimBridgeProto.TelemetryFrame
                                .parseFrom(snap.payload());
                        logger.info(String.format(
                                "[TMC] tick=%d capturedEpoch=%d AdvanceTime.epoch=%d TelemetryFrame.epoch=%d",
                                ticks, currentEpoch, currentEpoch, parsedFrame.getSchemaEpoch()));
                    } catch (Exception e) {
                        logger.error("Failed to parse telemetry frame for logging", e);
                    }
                }

                if (telemetryArtifact != null) {
                    ((TelemetryArtifact) telemetryArtifact).broadcast(snap, runId);
                }

                clearCommittedTransition();

                issueTimeAdvanceGrant(currentTime, currentEpoch);

                ticks++;

            } catch (Exception e) {
                logger.error("Tick loop error", e);
                try {
                    Thread.sleep(100);
                } catch (InterruptedException ie) {
                }
            }
        }
    }

    private TelemetryFrameSnapshot assembleTelemetryFrame(SimBridgeProto.StepReady ready, int currentEpoch) {
        SimBridgeProto.TelemetryFrame.Builder b = SimBridgeProto.TelemetryFrame.newBuilder();

        b.setSequenceNumber(sequenceNumber.get())
                .setSimTimeS(currentTime)
                .setSchemaEpoch(currentEpoch)
                .setActiveOrgSchema(activeOrgSchema);

        // AMR state
        AMRSnapshot[] amrPositions = ((AMRArtifact) amrArtifact).currentPositions;
        if (amrPositions != null) {
            for (AMRSnapshot snap : amrPositions) {
                b.addAmrStates(SimBridgeProto.AMRState.newBuilder()
                        .setAmrId(snap.amrId())
                        .setGridX(snap.gridX()).setGridY(snap.gridY())
                        .setNextGridX(snap.nextGridX()).setNextGridY(snap.nextGridY())
                        .setMovementProgress(snap.movementProgress())
                        .setStatus(snap.status())
                        .setCarryingOrderId(snap.carryingOrderId())
                        .build());
            }
        }

        // Station state
        for (Object obj : stationArtifacts) {
            if (obj instanceof BaseStationArtifact sta) {
                StationSummary sum = sta.currentSummary;
                b.addStationStates(SimBridgeProto.StationState.newBuilder()
                        .setStationId(sta.stationId)
                        .setState(sum.state())
                        .setActiveOrderId(sum.activeOrderId())
                        .setProcessingProgress(sum.processingProgress())
                        .build());
            } else if (obj instanceof TestBenchArtifact tb) {
                StationSummary sum = tb.currentSummary;
                b.addStationStates(SimBridgeProto.StationState.newBuilder()
                        .setStationId(tb.stationId)
                        .setState(sum.state())
                        .setActiveOrderId(sum.activeOrderId())
                        .setProcessingProgress(sum.processingProgress())
                        .build());
            }
        }

        b.addAllThermoStateVector(ready.getStateVectorList());

        List<Double> sv = ready.getStateVectorList();
        if (sv.size() >= ProtoIndex.VECTOR_LENGTH) {
            b.setStation5StackVoltageV(sv.get(ProtoIndex.STACK_VOLTAGE_V))
                    .setStation5CurrentDensityACm2(sv.get(ProtoIndex.STACK_CURRENT_A_CM2))
                    .setStation5StackTempK(sv.get(ProtoIndex.STACK_TEMP_K))
                    .setStation5StackCoreTempK(sv.get(ProtoIndex.STACK_CORE_TEMP_K))
                    .setStation5StackSkinTempK(sv.get(ProtoIndex.STACK_SKIN_TEMP_K))
                    .setH2TankPressureBar(sv.get(ProtoIndex.H2_TANK_PRESSURE_BAR))
                    .setH2TankFillFraction(sv.get(ProtoIndex.H2_TANK_FILL_FRACTION))
                    .setChillerTempK(sv.get(ProtoIndex.CHILLER_TEMP_K))
                    .setCompressorPowerKw(sv.get(ProtoIndex.COMPRESSOR_POWER_KW));
        }

        // station5_failure_flags mirrors the last RunBatchTest result (doc6
        // §3.1). This is sourced from the TestBenchArtifact directly, not
        // parsed out of the AdvanceTime state vector, because
        // STATION_DEFECT_DETECTED on tb.currentSummary is reset back to
        // STATION_IDLE by releaseStation() almost immediately after being
        // set (resource_holon.asl calls it right after processOrder
        // returns, on both the pass and fail paths, so the station remains
        // claimable for the next order) — these fields on TestBenchArtifact
        // are the reliable channel; they are never touched by
        // releaseStation(). (station5_current_density/voltage above ARE
        // read from the AdvanceTime state vector — RunBatchTest mirrors its
        // in-progress current/voltage into that same shared state under
        // `_physics_step_lock` so a live test is visible in telemetry.)
        for (Object obj : stationArtifacts) {
            if (obj instanceof TestBenchArtifact tb) {
                b.setStation5FailureFlags(tb.lastFailureFlags)
                        .setStation5HasRunTest(tb.hasRunAnyTest)
                        .setStation5LastTestPassed(tb.lastTestPassed)
                        .setStation5LastTestedStackId(tb.lastTestedStackId)
                        .addAllStation5LastMeasuredVoltages(tb.lastMeasuredVoltages);
                break;
            }
        }

        // b.setDroppedTelemetryFrameCount(((TelemetryArtifact)
        // telemetryArtifact).droppedTelemetryFrameCount.intValue())
        b.setDroppedTelemetryFrameCount(0)
                .setDroppedNerCount((int) droppedNerCount.get())
                .setRunId(runId);

        return new TelemetryFrameSnapshot(b.build().toByteArray(), currentTime, sequenceNumber.getAndIncrement());
    }

    private void issueTimeAdvanceGrant(double time, int epoch) {
        // Wake up agents waiting on NER
    }

    public synchronized OrgSchemaTransition beginTransition(String targetSchema, double currentSimTimeS) {
        int nextEpoch = schemaEpoch.get() + 1; // Reserved; not yet applied
        OrgSchemaTransition t = OrgSchemaTransition.startDrain(targetSchema, nextEpoch, currentSimTimeS);
        activeTransition = t;
        return t;
    }

    public synchronized void commitTransition(OrgSchemaTransition t) {
        schemaEpoch.set(t.newEpoch()); // Atomic apply
        activeOrgSchema = t.targetSchema(); // Volatile write
        activeTransition = t.advanceTo(OrgSchemaTransition.TransitionPhase.COMMITTED, Double.NaN);
    }

    public synchronized void clearCommittedTransition() {
        if (activeTransition != null && activeTransition.phase() == OrgSchemaTransition.TransitionPhase.COMMITTED) {
            activeTransition = null;
        }
    }

    // ── Test support ─────────────────────────────────────────────────────

    /**
     * Blocks until the tick loop sets {@code shutdown = true} (e.g. after
     * maxTicks is reached), or until the timeout elapses.
     *
     * @return {@code true} if the simulator shut down within the timeout
     */
    public boolean waitForShutdown(long timeout, TimeUnit unit) throws InterruptedException {
        return shutdownLatch.await(timeout, unit);
    }

    public boolean isShutdown() {
        return shutdown;
    }

    /** Typed accessor — avoids the Object-typed field for test assertions. */
    public AMRArtifact getAmrArtifact() {
        return (AMRArtifact) amrArtifact;
    }

    /** Typed accessor — avoids the Object-typed field for test assertions. */
    public DatabaseArtifact getDatabaseArtifact() {
        return (DatabaseArtifact) databaseArtifact;
    }

    /** Typed accessor — avoids the Object-typed field for test assertions. */
    public SupervisorArtifact getSupervisorArtifact() {
        return (SupervisorArtifact) supervisorArtifact;
    }

    /** Typed accessor for the timer artifact. */
    public TimerArtifact getTimerArtifact() {
        return (TimerArtifact) timerArtifact;
    }
}
