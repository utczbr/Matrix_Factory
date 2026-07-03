const protobuf = require("protobufjs");
const fs = require("fs");

protobuf.load("physical_engine/protos/sim_bridge.proto", function(err, root) {
    if (err) throw err;
    const TelemetryFrame = root.lookupType("factory.TelemetryFrame");
    const buffer = fs.readFileSync("frame.bin");
    const message = TelemetryFrame.decode(buffer);
    console.log(JSON.stringify(message, null, 2));
});
