package factory;

import cartago.*;
import jakarta.websocket.Session;
import java.nio.ByteBuffer;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;

import org.glassfish.tyrus.server.Server;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TelemetryArtifact extends Artifact {
    private static final Logger logger = LoggerFactory.getLogger(TelemetryArtifact.class);
    private static final int QUEUE_CAPACITY = 5_000;
    private static final double PUBLISH_INTERVAL_S = 1.0 / 18.0; // ~18Hz, within 15-20Hz band

    private record PendingFrame(int runId, byte[] frameBytes, double simTimeS) {
    }

    private final ArrayBlockingQueue<PendingFrame> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final AtomicLong droppedTelemetryFrameCount = new AtomicLong(0);
    private volatile double lastPublishedSimTimeS = Double.NEGATIVE_INFINITY;
    private Thread consumerThread;
    private int runId;
    @OPERATION
    void init(int port, int runId) {
        this.runId = runId;
        consumerThread = new Thread(this::consumeLoop, "telemetry-artifact-consumer-" + runId);
        consumerThread.setDaemon(true);
        consumerThread.start();

        RunManager.getSimulator(runId).telemetryArtifact = this;
    }

    // In MainSimulator, we use broadcast(TelemetryFrameSnapshot snap) right now.
    @OPERATION
    public void broadcast(TelemetryFrameSnapshot snap, int runId) {
        if (snap == null)
            return;
        if (snap.simTimeS() - lastPublishedSimTimeS < PUBLISH_INTERVAL_S)
            return;

        boolean offered = queue.offer(new PendingFrame(runId, snap.payload(), snap.simTimeS()));
        if (!offered) {
            droppedTelemetryFrameCount.incrementAndGet();
        }
    }

    private void consumeLoop() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                PendingFrame pending = queue.take();
                TelemetryHub.broadcast(
                        pending.runId(),
                        ByteBuffer.wrap(pending.frameBytes()),
                        pending.simTimeS(),
                        () -> lastPublishedSimTimeS = pending.simTimeS(),
                        droppedTelemetryFrameCount::incrementAndGet);
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
        if (consumerThread != null) {
            consumerThread.interrupt();
        }
        super.dispose();
    }
}
