package factory;

import cartago.*;
import jakarta.websocket.Session;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

import org.glassfish.tyrus.server.Server;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TelemetryArtifact extends Artifact {
    private static final Logger logger = LoggerFactory.getLogger(TelemetryArtifact.class);
    private static final int QUEUE_CAPACITY = 5_000;
    private static final double PUBLISH_INTERVAL_S = 1.0 / 18.0; // ~18Hz, within 15-20Hz band

    private final ArrayBlockingQueue<byte[]> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final AtomicLong droppedTelemetryFrameCount = new AtomicLong(0);
    private volatile double lastPublishedSimTimeS = Double.NEGATIVE_INFINITY;
    private Thread consumerThread;
    private Server server;

    void init(int port) {
        server = new Server("127.0.0.1", port, "/", null, TelemetryWebSocketEndpoint.class);
        try {
            server.start();
            logger.info("Telemetry WebSocket server started on port " + port);
        } catch (Exception e) {
            logger.error("Failed to start Telemetry WebSocket server", e);
        }
        
        consumerThread = new Thread(this::consumeLoop, "telemetry-artifact-consumer");
        consumerThread.setDaemon(true);
        consumerThread.start();
        
        // Also register with MainSimulator
        MainSimulator.INSTANCE.telemetryArtifact = this;
    }

    // In MainSimulator, we use broadcast(TelemetryFrameSnapshot snap) right now.
    @OPERATION
    public void broadcast(TelemetryFrameSnapshot snap) {
        if (snap == null) return;
        if (snap.simTimeS() - lastPublishedSimTimeS < PUBLISH_INTERVAL_S) return;

        byte[] frameBytes = snap.payload();
        boolean offered = queue.offer(frameBytes);
        if (!offered) {
            droppedTelemetryFrameCount.incrementAndGet();
        }
    }

    private void consumeLoop() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                byte[] frame = queue.take();
                Session s = TelemetryWebSocketEndpoint.currentSession();
                if (s == null || !s.isOpen()) continue;

                s.getAsyncRemote().sendBinary(
                    java.nio.ByteBuffer.wrap(frame),
                    result -> {
                        if (result.isOK()) {
                            // Needs access to simTimeS. If we just sent payload(), we can extract it.
                            // StateSnapshot.extractSimTimeS(frame) logic in doc:
                            try {
                                SimBridgeProto.TelemetryFrame parsed = SimBridgeProto.TelemetryFrame.parseFrom(frame);
                                lastPublishedSimTimeS = parsed.getSimTimeS();
                            } catch (Exception e) {
                                // fallback
                            }
                        } else {
                            droppedTelemetryFrameCount.incrementAndGet();
                        }
                    }
                );
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        }
    }

    long getDroppedTelemetryFrameCount() {
        return droppedTelemetryFrameCount.get();
    }
    
    @Override
    protected void dispose() {
        if (server != null) {
            server.stop();
        }
        if (consumerThread != null) {
            consumerThread.interrupt();
        }
        super.dispose();
    }
}
