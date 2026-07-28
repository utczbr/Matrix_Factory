package factory;

import factory.SimBridgeProto.AMRStatusEnum;

public record AMRSnapshot(
    String amrId,
    int gridX,
    int gridY,
    int nextGridX,
    int nextGridY,
    float movementProgress,    // [0.0, 1.0]
    AMRStatusEnum status,
    String carryingOrderId,
    boolean breakdownActive
) {
    public AMRSnapshot(String amrId, int gridX, int gridY, int nextGridX, int nextGridY, float movementProgress, AMRStatusEnum status, String carryingOrderId) {
        this(amrId, gridX, gridY, nextGridX, nextGridY, movementProgress, status, carryingOrderId, false);
    }
}
