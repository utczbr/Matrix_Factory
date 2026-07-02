const protobuf = require("protobufjs");
protobuf.load("physical_engine/protos/sim_bridge.proto", function(err, root) {
    if (err) throw err;
    const TelemetryFrame = root.lookupType("factory.TelemetryFrame");
    const payload = {
        sequenceNumber: 1,
        simTimeS: 1.5,
        amrStates: [{ amrId: "A1", gridX: 2, gridY: 3 }],
        stationStates: [{ stationId: "S1", state: 2 }]
    };
    const errMsg = TelemetryFrame.verify(payload);
    if (errMsg) throw Error(errMsg);
    const message = TelemetryFrame.create(payload);
    const buffer = TelemetryFrame.encode(message).finish();
    
    const decoded = TelemetryFrame.decode(buffer);
    console.log(JSON.stringify(decoded, null, 2));
});
