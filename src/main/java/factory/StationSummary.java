package factory;

import factory.SimBridgeProto.StationStateEnum;

public record StationSummary(
    StationStateEnum state,
    String activeOrderId,
    float processingProgress   // [0.0, 1.0], meaningful only when BUSY_PROCESSING
) {
    public static final StationSummary IDLE = 
        new StationSummary(StationStateEnum.STATION_IDLE, "", 0.0f);
    public static final StationSummary OFFLINE = 
        new StationSummary(StationStateEnum.STATION_OFFLINE, "", 0.0f);
}
