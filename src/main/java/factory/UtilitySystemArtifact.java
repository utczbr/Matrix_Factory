package factory;

import cartago.*;
import factory.SimBridgeProto.StepReady;

public class UtilitySystemArtifact extends Artifact {
    private volatile double currentSimTimeS = 0.0;
    private int runId;

    @OPERATION
    void init(int runId) {
        this.runId = runId;
        defineObsProperty("h2_pressure_bar", 0.0);
        defineObsProperty("h2_fill_fraction", 0.0);
        defineObsProperty("chiller_temp_k", 0.0);
        defineObsProperty("compressor_power_kw", 0.0);
        defineObsProperty("schema_epoch", 0);
        RunManager.getSimulator(runId).utilitySystemArtifact = this;
    }

    public void updateFromStateVector(StepReady ready, double simTimeS, int currentEpoch) {
        this.currentSimTimeS = simTimeS;
        java.util.List<Double> sv = ready.getStateVectorList();
        if (sv.size() >= ProtoIndex.VECTOR_LENGTH) {
            beginExtSession();
            try {
                if (hasObsProperty("h2_pressure_bar")) {
                    updateObsProperty("h2_pressure_bar", sv.get(ProtoIndex.H2_TANK_PRESSURE_BAR));
                    updateObsProperty("h2_fill_fraction", sv.get(ProtoIndex.H2_TANK_FILL_FRACTION));
                    updateObsProperty("chiller_temp_k", sv.get(ProtoIndex.CHILLER_TEMP_K));
                    updateObsProperty("compressor_power_kw", sv.get(ProtoIndex.COMPRESSOR_POWER_KW));
                    updateObsProperty("schema_epoch", currentEpoch);
                }
            } finally {
                endExtSession();
            }
        }
    }

    /**
     * Synchronous simulation-time query. Called by supervisor_agent.asl via
     * getSimTime(SimT) whenever a plan needs to timestamp an event.
     * No observable event is generated; no belief revision occurs.
     */
    @OPERATION
    void getSimTime(OpFeedbackParam<Double> simTime) {
        simTime.set(currentSimTimeS);
    }
}
