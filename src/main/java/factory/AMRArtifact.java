package factory;

import cartago.*;
import factory.SimBridgeProto.AMRStatusEnum;

public class AMRArtifact extends Artifact {
    private String[][][] reservedBy;
    private int gridCols = 10;
    private int gridRows = 10;
    private int HORIZON_TICKS = 10;
    
    private double currentSimTime = 0.0;
    private double tickDt = 1.0;
    
    public volatile AMRSnapshot[] currentPositions = new AMRSnapshot[0];
    
    public AMRArtifact() {
    }
    
    void init(int cols, int rows, int count) {
        this.gridCols = cols;
        this.gridRows = rows;
        this.reservedBy = new String[gridCols][gridRows][HORIZON_TICKS];
        MainSimulator.INSTANCE.amrArtifact = this;
    }
    
    @OPERATION
    public void reserveTrajectory(Object[] trajectory, OpFeedbackParam<String> result) {
        String agentId = getOpUserName();
        synchronized(reservedBy) {
            // Minimal mock validation
            result.set("granted");
        }
    }
    
    @OPERATION
    public void getGridUtilization(OpFeedbackParam<Double> util) {
        if (MainSimulator.INSTANCE.gridStress) {
            util.set(0.95);
            return;
        }
        long occupied = 0;
        for (String[][] row : reservedBy)
            for (String[] cell : row)
                for (String amrId : cell)
                    if (amrId != null) occupied++;
        util.set((double) occupied / (gridCols * gridRows * HORIZON_TICKS));
    }
    
    public void clearExpiredReservations() {
        synchronized(reservedBy) {
            for (int x = 0; x < gridCols; x++) {
                for (int y = 0; y < gridRows; y++) {
                    for (int t = 0; t < HORIZON_TICKS - 1; t++) {
                        reservedBy[x][y][t] = reservedBy[x][y][t+1];
                    }
                    reservedBy[x][y][HORIZON_TICKS - 1] = null;
                }
            }
        }
    }
    
    public void updatePositions(double simTime, double dt) {
        this.currentSimTime = simTime;
        this.tickDt = dt;
        // In a real implementation, we would compute movement progress here.
        // currentPositions = new AMRSnapshot[] { ... };
    }
}
