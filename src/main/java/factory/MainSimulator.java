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
    
    public static final MainSimulator INSTANCE = new MainSimulator();
    
    // TMC State
    private double currentTime = 0.0;
    private final AtomicInteger schemaEpoch = new AtomicInteger(0);
    private final AtomicLong sequenceNumber = new AtomicLong(1);
    public final AtomicLong droppedNerCount = new AtomicLong(0);
    
    private volatile String activeOrgSchema = "centralized";
    public volatile OrgSchemaTransition activeTransition = null;
    
    public final int runId = 0;
    
    private int maxTicks = -1;
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
    
    private int registeredAgentCount = 8; // order_manager + 5 stations + 2 AMRs
    
    private boolean shutdown = false;
    
    // Artifact references (populated when artifacts init)
    public Object timerArtifact;           // TODO: Type as TimerArtifact
    public Object energyPriceArtifact;     // TODO: Type as EnergyPriceArtifact
    public Object telemetryArtifact;       // TODO: Type as TelemetryArtifact
    public Object amrArtifact;             // TODO: Type as AMRArtifact
    public final List<Object> stationArtifacts = new CopyOnWriteArrayList<>(); // TODO: Type as BaseStationArtifact
    public Object utilitySystemArtifact;   // TODO: Type as UtilitySystemArtifact
    public Object supervisorArtifact;
    
    public final AtomicReference<TelemetryFrameSnapshot> telemetryRef = new AtomicReference<>();
    
    private GrpcClientBridge grpcBridge;
    
    private MainSimulator() {}
    
    public static void main(String[] args) {
        for (String arg : args) {
            if (arg.startsWith("--max-ticks=")) {
                INSTANCE.maxTicks = Integer.parseInt(arg.substring("--max-ticks=".length()));
            } else if (arg.equals("--log-epochs")) {
                INSTANCE.logEpochs = true;
            } else if (arg.startsWith("--force-abort-on=")) {
                INSTANCE.forceAbortStation = arg.substring("--force-abort-on=".length());
            } else if (arg.startsWith("--order=")) {
                INSTANCE.forceAbortOrder = arg.substring("--order=".length());
            } else if (arg.startsWith("--max-orders=")) {
                INSTANCE.maxOrders = Integer.parseInt(arg.substring("--max-orders=".length()));
            } else if (arg.equals("--cnp-slow-accept")) {
                INSTANCE.cnpSlowAccept = true;
            } else if (arg.startsWith("--ttl=")) {
                INSTANCE.ttl = Long.parseLong(arg.substring("--ttl=".length()));
            } else if (arg.startsWith("--price-series=")) {
                INSTANCE.priceSeriesFile = arg.substring("--price-series=".length());
            } else if (arg.startsWith("--force-spike-at=")) {
                INSTANCE.forceSpikeAt = Double.parseDouble(arg.substring("--force-spike-at=".length()));
            } else if (arg.equals("--grid-stress")) {
                INSTANCE.gridStress = true;
            } else if (arg.startsWith("--lock-hold-orders=")) {
                INSTANCE.lockHoldOrders = arg.substring("--lock-hold-orders=".length());
            } else if (arg.startsWith("--block-ack-from=")) {
                INSTANCE.blockAckFrom = arg.substring("--block-ack-from=".length());
            } else if (arg.startsWith("--inject-epoch-mismatch-on=")) {
                INSTANCE.injectEpochMismatchOn = arg.substring("--inject-epoch-mismatch-on=".length());
            } else if (arg.startsWith("--log-brf=")) {
                INSTANCE.logBrfAgent = arg.substring("--log-brf=".length());
            } else if (arg.equals("--trace-message") || arg.equals("--trace-messages")) {
                INSTANCE.traceMessages = true;
            }
        }
        try {
            // 1. Launch JaCaMo in a background thread so it doesn't block TMC initialization
            Thread jacamoThread = new Thread(() -> {
                try {
                    jacamo.infra.JaCaMoLauncher.main(new String[]{"factory.jcm"});
                } catch (Exception e) {
                    logger.error("JaCaMo failed", e);
                }
            }, "JaCaMo-Launcher");
            jacamoThread.start();
            
            // Wait for CArtAgO to boot
            Thread.sleep(2000);
            
            INSTANCE.start();
        } catch (Exception e) {
            logger.error("Simulation failed", e);
        }
    }
    
    public void start() throws InterruptedException {
        // Configure Jason JUL logging dynamically based on flags
        if (logBrfAgent != null || traceMessages) {
            java.util.logging.Logger rootLogger = java.util.logging.Logger.getLogger("");
            for (java.util.logging.Handler handler : rootLogger.getHandlers()) {
                if (handler.getLevel().intValue() > java.util.logging.Level.FINE.intValue()) {
                    handler.setLevel(java.util.logging.Level.FINE);
                }
            }
            if (logBrfAgent != null) {
                java.util.logging.Logger.getLogger("jason.asSemantics.TransitionSystem").setLevel(java.util.logging.Level.FINE);
            }
            if (traceMessages) {
                java.util.logging.Logger.getLogger("jason.communication").setLevel(java.util.logging.Level.FINE);
                java.util.logging.Logger.getLogger("jason.asSemantics.Message").setLevel(java.util.logging.Level.FINE);
            }
        }

        // 2. GrpcClientBridge.pollUntilReady()
        grpcBridge = new GrpcClientBridge(50051);
        grpcBridge.pollUntilReady();
        
        // Wait for artifacts to register themselves
        logger.info("Waiting for all artifacts to register...");
        while (timerArtifact == null || energyPriceArtifact == null || telemetryArtifact == null || 
               amrArtifact == null || stationArtifacts.size() < 5 || utilitySystemArtifact == null ||
               supervisorArtifact == null) {
            Thread.sleep(500);
        }
        
        ((SupervisorArtifact) supervisorArtifact).setMainSimulator(this);
        
        // 3. initialize EnergyPriceArtifact
        ((EnergyPriceArtifact) energyPriceArtifact).updatePrice(0.0);
        
        schemaEpoch.set(0);
        
        // 4. start simulation tick loop thread
        Thread tickLoop = new Thread(this::tickLoop, "TMC-TickLoop");
        tickLoop.setDaemon(true);
        tickLoop.start();
    }
    
    public void submitNER(String agentId, double requestedNextTime) {
        nerRegistry.put(agentId, new NEREntry(agentId, requestedNextTime));
        if (nerLatch != null) {
            nerLatch.countDown();
        }
    }
    
    public double getCurrentTime() {
        return currentTime;
    }
    
    public GrpcClientBridge getGrpcBridge() {
        return grpcBridge;
    }
    
    private void tickLoop() {
        int ticks = 0;
        while (!shutdown) {
            if (maxTicks > 0 && ticks >= maxTicks) {
                logger.info("Max ticks reached. Shutting down.");
                System.exit(0);
                break;
            }
            try {
                nerLatch = new CountDownLatch(registeredAgentCount);
                if (!nerLatch.await(TICK_QUORUM_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
                    droppedNerCount.incrementAndGet();
                    logger.warn("NER Quorum timeout. Proceeding anyway.");
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
                        SimBridgeProto.TelemetryFrame parsedFrame = SimBridgeProto.TelemetryFrame.parseFrom(snap.payload());
                        logger.info(String.format("[TMC] tick=%d capturedEpoch=%d AdvanceTime.epoch=%d TelemetryFrame.epoch=%d",
                            ticks, currentEpoch, currentEpoch, parsedFrame.getSchemaEpoch()));
                    } catch (Exception e) {
                        logger.error("Failed to parse telemetry frame for logging", e);
                    }
                }
                
                if (telemetryArtifact != null) {
                    ((TelemetryArtifact) telemetryArtifact).broadcast(snap);
                }
                
                clearCommittedTransition();
                
                issueTimeAdvanceGrant(currentTime, currentEpoch);
                
                ticks++;
                
            } catch (Exception e) {
                logger.error("Tick loop error", e);
                try { Thread.sleep(100); } catch (InterruptedException ie) {}
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
        
        // b.setDroppedTelemetryFrameCount(((TelemetryArtifact) telemetryArtifact).droppedTelemetryFrameCount.intValue())
        b.setDroppedTelemetryFrameCount(0)
         .setDroppedNerCount((int) droppedNerCount.get())
         .setRunId(runId);
         
        return new TelemetryFrameSnapshot(b.build().toByteArray(), currentTime, sequenceNumber.getAndIncrement());
    }
    
    private void issueTimeAdvanceGrant(double time, int epoch) {
        // Wake up agents waiting on NER
    }
    
    public synchronized OrgSchemaTransition beginTransition(String targetSchema, double currentSimTimeS) {
        int nextEpoch = schemaEpoch.get() + 1;  // Reserved; not yet applied
        OrgSchemaTransition t = OrgSchemaTransition.startDrain(targetSchema, nextEpoch, currentSimTimeS);
        activeTransition = t;
        return t;
    }

    public synchronized void commitTransition(OrgSchemaTransition t) {
        schemaEpoch.set(t.newEpoch());       // Atomic apply
        activeOrgSchema = t.targetSchema();  // Volatile write
        activeTransition = t.advanceTo(OrgSchemaTransition.TransitionPhase.COMMITTED, Double.NaN);
    }

    public synchronized void clearCommittedTransition() {
        if (activeTransition != null && activeTransition.phase() == OrgSchemaTransition.TransitionPhase.COMMITTED) {
            activeTransition = null;
        }
    }
}
