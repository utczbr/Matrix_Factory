package factory;

import cartago.*;
import java.sql.*;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.time.Duration;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

public class DatabaseArtifact extends Artifact {
    private static final int QUEUE_CAPACITY = 300_000;
    private static final int MAX_BATCH = 2_000;
    private static final int BACKPRESSURE_HIGH = 300_000;      // queue full
    private static final int BACKPRESSURE_LOW  = 3_000;        // hysteresis clear point
    private static final long DRAIN_INTERVAL_MS = 500L;

    private final ArrayBlockingQueue<TelemetryRecord> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final ArrayBlockingQueue<QualityRecord> qualityQueue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    private final AtomicBoolean backpressureActive = new AtomicBoolean(false);
    private Connection conn;
    private int runId;
    private Thread drainThread;

    // ------------------------------------------------------------------
    // Manufacturing-quality bridge (Stations 1-4 -> Station 5)
    // ------------------------------------------------------------------
    // In-memory accumulator, keyed by stack_id. Stations 1-4 push into this
    // synchronously (via recordStationQuality) so Station 5 can read a
    // stack's *complete* cumulative quality profile the instant it arrives
    // at the test bench, without waiting on the async SQLite drain loop
    // (which is write-behind on a 500ms cadence and only intended for
    // durable audit history, not the process-order hot path).
    // Caffeine cache replaces ConcurrentHashMap — bounded size + TTL catches
    // orphaned entries from stacks aborted before reaching Station 5 (the
    // ADACOR abort path). .asMap() preserves the existing merge/remove
    // semantics so no call site outside this class needs to change.
    private final Cache<String, QualityProfile> qualityProfilesCache = Caffeine.newBuilder()
        .maximumSize(10_000)                       // generous multiple of realistic concurrent in-flight stacks
        .expireAfterAccess(Duration.ofMinutes(30))  // catches orphans from aborted orders
        .build();

    /**
     * Immutable, additively-mergeable quality accumulator for one stack.
     *
     * @param defectCount            number of station events flagged as
     *                                defective (rng.nextDouble() < defectRate)
     * @param stationsVisited        number of Stations 1-4 events recorded
     * @param cumulativeVarianceRatio sum over visited stations of
     *                                |tProc - tMean| / tMean — a proxy for
     *                                cumulative process imprecision even on
     *                                runs that didn't trip the boolean
     *                                defect flag
     */
    public record QualityProfile(int defectCount, int stationsVisited, double cumulativeVarianceRatio) {
        static final QualityProfile EMPTY = new QualityProfile(0, 0, 0.0);

        QualityProfile plus(QualityProfile other) {
            return new QualityProfile(
                    this.defectCount + other.defectCount,
                    this.stationsVisited + other.stationsVisited,
                    this.cumulativeVarianceRatio + other.cumulativeVarianceRatio);
        }
    }

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
                s.execute("CREATE TABLE IF NOT EXISTS StationQuality(" +
                          "run_id INTEGER, stack_id TEXT, station_id TEXT, " +
                          "defect INTEGER, t_proc_s REAL, t_mean_s REAL, sim_time REAL)");
            }
        } catch (SQLException e) {
            throw new IllegalStateException("DatabaseArtifact init failed", e);
        }
        drainThread = new Thread(this::drainLoop, "database-artifact-drain");
        drainThread.setDaemon(true);
        drainThread.start();
    }

    /**
     * Stations 1-4 call this at the end of {@code processOrder} to log the
     * process variation ({@code rng.nextGaussian()}-derived processing time)
     * and defect roll ({@code rng.nextDouble() < defectRate}) that just
     * occurred, so Station 5 can later reconstruct the stack's cumulative
     * manufacturing-quality profile.
     *
     * Updates the in-memory accumulator synchronously (read path for
     * Station 5 is instant) and enqueues a durable row for SQLite (write
     * path is async/batched, same as {@link #recordEvent}).
     */
    @OPERATION
    public void recordStationQuality(int runId, String stackId, String stationId,
                                      boolean defect, double tProcS, double tMeanS, double simTime) {
        double varianceRatio = tMeanS > 0.0 ? Math.abs(tProcS - tMeanS) / tMeanS : 0.0;
        QualityProfile delta = new QualityProfile(defect ? 1 : 0, 1, varianceRatio);
        qualityProfilesCache.asMap().merge(stackId, delta, QualityProfile::plus);

        QualityRecord rec = new QualityRecord(runId, stackId, stationId, defect, tProcS, tMeanS, simTime);
        if (!qualityQueue.offer(rec)) {
            signal("database_write_dropped", stackId);
        }
    }

    /**
     * Station 5 (TestBenchArtifact) calls this when a stack arrives at the
     * test bench, to fetch its cumulative quality profile before building
     * the {@code BatchTestRequest}. Returns all-zero for a stack with no
     * logged station events (never seen defects/variance — treated as a
     * perfect stack, not an error).
     */
    @OPERATION
    public void getQualityProfile(String stackId, OpFeedbackParam<Integer> defectCount,
                                   OpFeedbackParam<Integer> stationsVisited,
                                   OpFeedbackParam<Double> cumulativeVarianceRatio) {
        // Consuming read: once Station 5 reads a stack's profile, that entry
        // is provably dead — no station downstream of S5 exists to write to
        // it again. remove() instead of getOrDefault() prevents unbounded
        // accumulation on the normal (non-abort) path.
        QualityProfile p = qualityProfilesCache.asMap().remove(stackId);
        if (p == null) p = QualityProfile.EMPTY;
        defectCount.set(p.defectCount());
        stationsVisited.set(p.stationsVisited());
        cumulativeVarianceRatio.set(p.cumulativeVarianceRatio());
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

                // Observability: log qualityProfiles cache size periodically so a
                // future leak (e.g. from a new pipeline stage bypassing S5) shows
                // up as a metric instead of requiring another manual audit.
                long cacheSize = qualityProfilesCache.estimatedSize();
                if (cacheSize > 100) {
                    System.out.println("[DatabaseArtifact] qualityProfiles cache size: " + cacheSize);
                }

                int qBatchSize = Math.min(MAX_BATCH, qualityQueue.size());
                if (qBatchSize > 0) {
                    java.util.ArrayList<QualityRecord> qBatch = new java.util.ArrayList<>(qBatchSize);
                    for (int i = 0; i < qBatchSize; i++) {
                        QualityRecord rec = qualityQueue.poll();
                        if (rec == null) break;
                        qBatch.add(rec);
                    }
                    if (!qBatch.isEmpty()) {
                        try (PreparedStatement ps = conn.prepareStatement(
                                "INSERT INTO StationQuality(run_id, stack_id, station_id, defect, t_proc_s, t_mean_s, sim_time) " +
                                "VALUES (?,?,?,?,?,?,?)")) {
                            conn.setAutoCommit(false);
                            for (QualityRecord rec : qBatch) {
                                ps.setInt(1, rec.runId());
                                ps.setString(2, rec.stackId());
                                ps.setString(3, rec.stationId());
                                ps.setInt(4, rec.defect() ? 1 : 0);
                                ps.setDouble(5, rec.tProcS());
                                ps.setDouble(6, rec.tMeanS());
                                ps.setDouble(7, rec.simTime());
                                ps.addBatch();
                            }
                            ps.executeBatch();
                            conn.commit();
                            conn.setAutoCommit(true);
                        } catch (SQLException e) {
                            signal("database_batch_commit_failed", qBatch.size());
                        }
                    }
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private record TelemetryRecord(int runId, String orderId, String eventType, double simTime) {}

    private record QualityRecord(int runId, String stackId, String stationId,
                                  boolean defect, double tProcS, double tMeanS, double simTime) {}
}
