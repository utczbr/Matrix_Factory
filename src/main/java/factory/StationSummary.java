package factory;

import factory.SimBridgeProto.StationStateEnum;

public record StationSummary(
    StationStateEnum state,
    String activeOrderId,
    float processingProgress,   // [0.0, 1.0], meaningful only when BUSY_PROCESSING
    double alphaFinal,
    double delaminationRisk,
    double pinholeRisk,
    double ecsaRatio,
    double damageIndex,
    double gdlPorosity,
    double eTangentMpa,
    double pClampMpa
) {
    public StationSummary(StationStateEnum state, String activeOrderId, float processingProgress) {
        this(state, activeOrderId, processingProgress, 0.0, 0.0, 0.0, 1.0, 0.0, 0.78, 0.0, 4.25);
    }

    public static final StationSummary IDLE = 
        new StationSummary(StationStateEnum.STATION_IDLE, "", 0.0f);
    public static final StationSummary OFFLINE = 
        new StationSummary(StationStateEnum.STATION_OFFLINE, "", 0.0f);
}
