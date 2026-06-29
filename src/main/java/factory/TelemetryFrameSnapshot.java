package factory;

/**
 * Immutable snapshot of one simulation tick's telemetry payload.
 * Published via AtomicReference.set() in MainSimulator; read by TelemetryArtifact.
 * The byte[] is the result of TelemetryFrame.toByteArray() — Protobuf binary.
 * Treating it as opaque bytes avoids a second serialization pass in TelemetryArtifact.
 */
public record TelemetryFrameSnapshot(byte[] payload, double simTimeS, long sequenceNumber) {}
