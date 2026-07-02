package factory;

import cartago.*;
import java.sql.*;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class DatabaseArtifact extends Artifact {
    private static final int QUEUE_CAPACITY = 300_000;
    private static final int MAX_BATCH = 2_000;
    private static final int BACKPRESSURE_HIGH = 300_000;      // queue full
    private static final int BACKPRESSURE_LOW  = 3_000;        // hysteresis clear point
    private static final long DRAIN_INTERVAL_MS = 500L;

    private final ArrayBlockingQueue<TelemetryRecord> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final AtomicBoolean backpressureActive = new AtomicBoolean(false);
    private Connection conn;
    private int runId;
    private Thread drainThread;

    @OPERATION
    void init(String dbPath, int runId) {
        this.runId = runId;
        try {
            conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath);
            try (Statement s = conn.createStatement()) {
                s.execute("PRAGMA journal_mode=WAL;");
                s.execute("PRAGMA wal_autocheckpoint=100;");
                s.execute("PRAGMA synchronous=NORMAL;");
                s.execute("CREATE TABLE IF NOT EXISTS Orders(" +
                          "run_id INTEGER, order_id TEXT, event_type TEXT, sim_time REAL)");
            }
        } catch (SQLException e) {
            throw new IllegalStateException("DatabaseArtifact init failed", e);
        }
        drainThread = new Thread(this::drainLoop, "database-artifact-drain");
        drainThread.setDaemon(true);
        drainThread.start();
    }

    @OPERATION
    void recordEvent(int runId, String orderId, String eventType, double simTime) {
        TelemetryRecord rec = new TelemetryRecord(runId, orderId, eventType, simTime);
        boolean offered = queue.offer(rec);
        if (!offered) {
            // Queue genuinely full — this is the failure path doc3 flags as a silent-drop
            // risk if unhandled. Do not drop silently: signal and let the caller decide.
            signal("database_write_dropped", orderId);
            return;
        }
        if (queue.size() >= BACKPRESSURE_HIGH && backpressureActive.compareAndSet(false, true)) {
            signal("database_backpressure");
        }
    }

    // Adapting signature for Phase 3 legacy calls, though doc uses recordEvent
    @OPERATION
    public void recordOrderStart(String orderId, double simTime) {
        recordEvent(0, orderId, "START", simTime);
    }
    
    @OPERATION
    public void recordOrderFinish(String orderId, double simTime, double revenue, double penalty) {
        recordEvent(0, orderId, "FINISH", simTime);
    }

    private void drainLoop() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                Thread.sleep(DRAIN_INTERVAL_MS);
                int batchSize = Math.min(MAX_BATCH, queue.size());
                if (batchSize == 0) continue;

                java.util.ArrayList<TelemetryRecord> batch = new java.util.ArrayList<>(batchSize);
                for (int i = 0; i < batchSize; i++) {
                    TelemetryRecord rec = queue.poll();
                    if (rec == null) break;
                    batch.add(rec);
                }
                if (batch.isEmpty()) continue;

                try (PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO Orders(run_id, order_id, event_type, sim_time) VALUES (?,?,?,?)")) {
                    conn.setAutoCommit(false);
                    for (TelemetryRecord rec : batch) {
                        ps.setInt(1, rec.runId);
                        ps.setString(2, rec.orderId);
                        ps.setString(3, rec.eventType);
                        ps.setDouble(4, rec.simTime);
                        ps.addBatch();
                    }
                    ps.executeBatch();
                    conn.commit();
                    conn.setAutoCommit(true);
                } catch (SQLException e) {
                    // Failed commit path: restore records to queue so drained events are not
                    // silently lost, then signal failure with restored-count context.
                    int restored = 0;
                    for (TelemetryRecord rec : batch) {
                        if (queue.offer(rec)) restored++;
                    }
                    signal("database_batch_commit_failed", restored);
                }

                if (queue.size() <= BACKPRESSURE_LOW && backpressureActive.compareAndSet(true, false)) {
                    signal("database_pressure_normal");
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private record TelemetryRecord(int runId, String orderId, String eventType, double simTime) {}
}
