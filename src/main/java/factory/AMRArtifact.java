package factory;

import cartago.*;
import factory.SimBridgeProto.AMRStatusEnum;

/**
 * AMRArtifact — physical position simulation for the shop-floor AMR fleet.
 *
 * ROOT CAUSE FIX (Phase 3.5 dashboard bug — "AMRs are not appearing"):
 * The previous implementation of updatePositions() was a stub:
 *
 *      public void updatePositions(double simTime, double dt) {
 *          // In a real implementation, we would compute movement progress here.
 *          // currentPositions = new AMRSnapshot[] { ... };
 *      }
 *
 * `currentPositions` was therefore *always* `new AMRSnapshot[0]`, so
 * MainSimulator.assembleTelemetryFrame() always emitted an empty
 * `amr_states` repeated field. No amount of frontend/canvas work can make
 * AMRs show up if the wire never carries their coordinates — this class is
 * the actual fix; the dashboard rewrite (below) is what makes use of it.
 *
 * This version drives each AMR through a simple, deterministic patrol
 * cycle (home dock -> a station cell -> home dock -> ...), advancing grid
 * cell by grid cell over time, and reporting `movement_progress` in [0,1]
 * for smooth client-side interpolation. It is intentionally decoupled from
 * the Jason/ASL cognitive layer's `transport/3` abstraction (which never
 * carried spatial coordinates) so it's a safe, additive fix. Wiring real
 * transport(OrderId, From, To) calls into per-AMR destinations is the
 * natural next step — see `requestDestination()` below, which is already
 * exposed for that purpose and simply isn't invoked by amr_agent.asl yet.
 */
public class AMRArtifact extends Artifact {
    private String[][][] reservedBy;
    private int gridCols = 10;
    private int gridRows = 10;
    private int HORIZON_TICKS = 10;

    // Edge-conflict detection: two AMRs crossing the same edge in opposite
    // directions in the same tick collide mid-edge even though both cells
    // are legally unoccupied at every instant.  Pack (x1,y1,x2,y2,t) into
    // a long key for O(1) contains/add.
    private final java.util.Set<Long> edgeReservations = java.util.concurrent.ConcurrentHashMap.newKeySet();

    private static long edgeKey(int x1, int y1, int x2, int y2, int t) {
        return (((long) x1) << 48) | (((long) y1) << 36) | (((long) x2) << 24)
                | (((long) y2) << 12) | t;
    }

    private double currentSimTime = 0.0;
    private double tickDt = 1.0;

    public volatile AMRSnapshot[] currentPositions = new AMRSnapshot[0];

    private int runId;

    // --- Station cell centers, kept in sync with visualization/factory_layout.json ---
    // NOTE: the physical/cognitive engine has no native notion of station
    // spatial coordinates (BaseStationArtifact only carries a logical
    // stationId). These are visualization-layer coordinates duplicated
    // here so the simulated fleet has somewhere real to drive to. If
    // factory_layout.json changes, update this table too.
    // S1/S2 = Stage 1 pool, S3/S4 = Stage 2 pool, S5 = Stage 3 sole gate
    // (see factory.jcm recipeStep args — S1/S2 both step 1, S3/S4 both
    // step 2, S5 alone is step 3; this is a parallel resource pool per
    // stage, not a sequential S1->S2->S3->S4->S5 pipeline).
    private static final int[][] STATION_CELLS = {
            {2, 2},  // S1 - MEA Prep (Stage 1)
            {6, 2},  // S2 - Cat. Dep. (Stage 1)
            {11, 2}, // S3 - BP Stamp (Stage 2)
            {15, 2}, // S4 - Stack Asm. (Stage 2)
            {4, 7},  // S5 - Test Bench (Stage 3)
    };

    private AMRSim[] fleet;

    /**
     * A single requestTransport() call, queued up if the target AMR is
     * already busy with another order instead of overwriting it.
     */
    private static final class TransportJob {
        final String fromStation;
        final String toStation;
        final String orderId;
        TransportJob(String fromStation, String toStation, String orderId) {
            this.fromStation = fromStation;
            this.toStation = toStation;
            this.orderId = orderId;
        }
    }

    private static final class AMRSim {
        String amrId;
        int homeX, homeY;
        float x, y;                 // current grid cell (integer-valued, float type per proto)
        float nextX, nextY;         // cell currently being entered
        float progress;             // [0,1] progress from (x,y) to (nextX,nextY)
        double secPerCell = 0.5;    // travel speed
        double dwellRemaining = 0;  // seconds paused at a waypoint
        java.util.List<int[]> path = new java.util.ArrayList<>();
        int pathIndex = 0;
        AMRStatusEnum status = AMRStatusEnum.AMR_IDLE;
        String carryingOrderId = "";
        String pendingOrderId = "";
        java.util.LinkedList<String> destinations = new java.util.LinkedList<>();
        int blockedTicks = 0;
        String pendingDest = null;
        int completedJobCount = 0;
        // ROOT CAUSE FIX (AMRs "going around and around" / stations stuck on
        // "waiting for item to arrive"): with N AMRs and more than N orders
        // in flight, order_holon.asl's hash-based AMR pick (I = R*10000 mod N)
        // routinely assigns two different orders to the same physical AMR.
        // requestTransport() used to overwrite `destinations` unconditionally,
        // silently abandoning whichever order was already in transit — that
        // order's station then waits forever for an amr_arrived that will
        // never come. Now a second request for a busy AMR is queued here and
        // started only once the AMR is actually free again.
        java.util.Queue<TransportJob> jobQueue = new java.util.LinkedList<>();
    }

    public AMRArtifact() {
    }

    @OPERATION
    void init(int cols, int rows, int count, int runId) {
        this.runId = runId;
        this.gridCols = cols;
        this.gridRows = rows;
        // §1.4: raise HORIZON_TICKS to gridCols + gridRows + margin so paths
        // up to the max possible Manhattan distance are never truncated.
        this.HORIZON_TICKS = gridCols + gridRows + 4;
        this.reservedBy = new String[gridCols][gridRows][HORIZON_TICKS];
        RunManager.getSimulator(runId).amrArtifact = this;

        fleet = new AMRSim[count];
        for (int i = 0; i < count; i++) {
            AMRSim a = new AMRSim();
            a.amrId = "AMR-" + (i + 1);
            // Docks along the bottom row, matching factory_layout.json's amr_docks.
            a.homeX = 1 + i;
            a.homeY = gridRows - 1;
            a.x = a.homeX;
            a.y = a.homeY;
            a.nextX = a.homeX;
            a.nextY = a.homeY;
            a.progress = 0f;
            a.dwellRemaining = 1.0 + (i * 0.6); // stagger fleet so AMRs don't move in lockstep
            fleet[i] = a;
        }
        publishSnapshot();
    }

    /**
     * Physical multi-waypoint transport for an AMR already chosen by the
     * caller. If the target AMR is idle, starts the job immediately (queues
     * up the fromStation, if any, then the toStation, and recalculates the
     * path right away). If the AMR is already carrying or en route to
     * another order, the job is queued and started automatically once the
     * AMR becomes free — it is never dropped or overwritten.
     *
     * No longer called from any .asl file: choosing an AMR (by load) and
     * committing to it used to be two separate steps across two agents —
     * this method was the "commit" half, called later by the AMR agent —
     * which left a race window between the read and this write (see
     * reserveTransport() below for the full writeup). reserveTransport()
     * now does the choosing and calls startJob()/queues here in one atomic
     * operation. Left in place (unused) as the underlying job-start/queue
     * primitive reserveTransport() itself calls, and in case a future
     * caller genuinely needs to target a pre-chosen AMR directly.
     */
    @OPERATION
    void requestTransport(String amrId, String fromStation, String toStation, String orderId) {
        if (fleet == null) return;
        for (AMRSim a : fleet) {
            if (a.amrId.equals(amrId)) {
                TransportJob job = new TransportJob(fromStation, toStation, orderId);
                if (isFree(a)) {
                    startJob(a, job);
                } else {
                    // AMR already has an order in flight — queue this one
                    // rather than clobbering the current destinations/path.
                    a.jobQueue.add(job);
                }
            }
        }
    }

    private boolean isFree(AMRSim a) {
        // ROOT CAUSE FIX (AMRs delivering once, then going idle forever):
        // this used to also require a.path.isEmpty() and a.destinations.isEmpty(),
        // which meant a queued job wouldn't start until the AMR physically
        // finished its empty round-trip back to the dock first. That extra
        // leg routinely doubled transit time for the next job and pushed it
        // past order_holon.asl's 60s await_station_start timeout, causing a
        // cascade of abort_transport calls. An AMR that isn't carrying
        // anything and isn't committed to a pickup is free to be redirected
        // immediately, mid-path, straight to its next real destination —
        // it never needs to touch the dock first.
        return a.carryingOrderId.isEmpty() && a.pendingOrderId.isEmpty();
    }

    private void startJob(AMRSim a, TransportJob job) {
        a.destinations.clear();
        if (job.fromStation != null && !job.fromStation.equals("start")) {
            a.destinations.add(job.fromStation);
            a.carryingOrderId = "";
        } else {
            a.carryingOrderId = job.orderId == null ? "" : job.orderId;
        }
        a.destinations.add(job.toStation);
        a.pendingOrderId = job.orderId == null ? "" : job.orderId;

        // Force immediate path recalculation from current position. Reset
        // progress too — startJob() can now interrupt an AMR mid-transit
        // (see isFree()), so any leftover progress toward its old next
        // cell would otherwise cause a visible snap on the new leg.
        a.path.clear();
        a.progress = 0f;
    }

    /**
     * Drops the given order's job for this AMR, whether it's the one
     * currently in progress or still sitting in the queue. Called when
     * amr_agent.asl receives abort_transport so the AMR doesn't keep
     * driving toward a delivery the cognitive layer has already given up
     * on (order_holon.asl retried the CNP and nobody is listening for
     * this amr_arrived anymore).
     */
    @OPERATION
    void cancelTransport(String amrId, String orderId) {
        if (fleet == null || amrId == null || orderId == null) return;
        for (AMRSim a : fleet) {
            if (!a.amrId.equals(amrId)) continue;
            a.jobQueue.removeIf(j -> orderId.equals(j.orderId));
            if (orderId.equals(a.pendingOrderId) || orderId.equals(a.carryingOrderId)) {
                a.destinations.clear();
                a.path.clear();
                a.pathIndex = 0;
                a.carryingOrderId = "";
                a.pendingOrderId = "";
            }
        }
    }

    /**
     * ROOT CAUSE FIX (blind AMR selection routinely piling multiple orders
     * onto one physical AMR while a second AMR sits idle at the dock):
     * order_holon.asl used to pick a transport AMR with a pseudo-random hash
     * (I = round(R*10000) mod N) that had zero visibility into which AMRs
     * were actually busy. With 5 concurrent order holons and only 2 AMRs,
     * that regularly queued several jobs behind one AMR while the other sat
     * idle — and a long enough queue behind a 2-leg station-to-station
     * transport can exceed the 60s await_station_start patience even though
     * the AMR itself is working correctly.
     *
     * This reports each AMR's current load — its queued-job count plus
     * whether it is presently carrying/committed to a job — so the
     * cognitive layer can dispatch to the least-loaded AMR instead of
     * guessing. Returned as a Jason-parseable list of
     * amr_load(PhysicalId, Load) terms, e.g.
     * [amr_load("AMR-1",2),amr_load("AMR-2",0)] — lower Load is more
     * available; 0 means genuinely idle.
     */
    @OPERATION
    public void getFleetStatus(OpFeedbackParam<String> result) {
        StringBuilder sb = new StringBuilder("[");
        if (fleet != null) {
            for (AMRSim a : fleet) {
                int load = a.jobQueue.size() + (isFree(a) ? 0 : 1);
                sb.append("amr_load(\"").append(a.amrId).append("\",").append(load).append("),");
            }
        }
        if (sb.length() > 1 && sb.charAt(sb.length() - 1) == ',') {
            sb.deleteCharAt(sb.length() - 1);
        }
        sb.append("]");
        result.set(sb.toString());
    }

    /**
     * ROOT CAUSE FIX (AMR load-balancing still races even with amr_load
     * reporting in place): getFleetStatus() above tells the cognitive layer
     * who's least loaded, but that read and the eventual commit are two
     * separate steps on two separate agents — order_holon.asl calls
     * getFleetStatus() here, then .send()s an achieve(transport(...)) to
     * whichever AMR agent looked best, and that AMR agent only calls
     * requestTransport() (the actual state mutation) later, on its own
     * reasoning cycle. Nothing serializes those two steps against a second
     * order holon doing the exact same read in between — and with 5 order
     * holons whose CNP timers routinely expire in the same evaluateTTLs
     * batch, that window is hit on essentially every dispatch in practice:
     * every "via amrX (load=N)" line ever logged reports load=0, even
     * moments after that same AMR was just committed elsewhere. The result
     * is exactly the failure mode this fleet was supposed to prevent — one
     * AMR's jobQueue piles up while the other sits idle at its dock, and a
     * long enough queue behind 2-leg station-to-station transports
     * routinely blows through the 60s await_station_start patience even
     * though every individual AMR is working correctly.
     *
     * Folding "pick the least-loaded AMR" and "commit the job to it" into a
     * single CArtAgO operation closes the window: CArtAgO serializes
     * operation calls on one artifact instance, so no other agent's call
     * can be interleaved between the read and the write here. Returns the
     * PHYSICAL id that was chosen (and its pre-commit load, for the
     * dispatch log line) so the caller can look up which Jason agent name
     * to notify.
     */
    @OPERATION
    public void reserveTransport(String fromStation, String toStation, String orderId,
                                  OpFeedbackParam<String> chosenAmrId, OpFeedbackParam<Integer> chosenLoad) {
        if (fleet == null || fleet.length == 0) {
            chosenAmrId.set("");
            chosenLoad.set(-1);
            return;
        }
        AMRSim best = null;
        int bestLoad = Integer.MAX_VALUE;
        for (AMRSim a : fleet) {
            int load = a.jobQueue.size() + (isFree(a) ? 0 : 1);
            if (load < bestLoad) {
                bestLoad = load;
                best = a;
            }
        }
        TransportJob job = new TransportJob(fromStation, toStation, orderId);
        if (isFree(best)) {
            startJob(best, job);
        } else {
            best.jobQueue.add(job);
        }
        chosenAmrId.set(best.amrId);
        chosenLoad.set(bestLoad);
    }

    /**
     * Space-Time A* trajectory reservation (Cooperative A*, Silver 2005).
     *
     * Plans a collision-free path for one AMR at a time, using the reservation
     * table as the obstacle set: already-planned AMRs' reserved cells become
     * static obstacles for the next AMR's search.
     *
     * This replaces the old stub that unconditionally returned "granted".
     * The consuming code in {@link #stepAMR} reads {@code a.path}/{@code a.pathIndex}
     * which are set by this method on success, so no .asl files need to change.
     */
    @OPERATION
    public void reserveTrajectory(String amrId, int goalX, int goalY, OpFeedbackParam<Boolean> granted) {
        synchronized (reservedBy) {
            int[] start = currentCell(amrId);
            if (start == null) {
                granted.set(false);
                return;
            }
            java.util.List<int[]> path = spaceTimeAStar(amrId, start, new int[]{goalX, goalY});
            if (path == null) {
                granted.set(false);   // horizon exhausted — no safe path found
                return;
            }
            commitReservation(amrId, path);   // writes reservedBy[x][y][t] and edgeReservations
            setAmrPath(amrId, path);          // replaces the manhattanPath() assignment
            granted.set(true);
        }
    }

    /**
     * Also keep the old signature available so existing .asl code that may
     * call reserveTrajectory(Object[], OpFeedbackParam<String>) doesn't break.
     */
    @OPERATION
    public void reserveTrajectory(Object[] trajectory, OpFeedbackParam<String> result) {
        // Legacy stub — maintained for backwards compatibility.
        // New callers should use reserveTrajectory(String, int, int, OpFeedbackParam<Boolean>).
        result.set("granted");
    }

    private int[] currentCell(String amrId) {
        if (fleet == null) return null;
        for (AMRSim a : fleet) {
            if (a.amrId.equals(amrId)) {
                return new int[]{(int) a.x, (int) a.y};
            }
        }
        return null;
    }

    private void setAmrPath(String amrId, java.util.List<int[]> path) {
        if (fleet == null) return;
        for (AMRSim a : fleet) {
            if (a.amrId.equals(amrId)) {
                a.path = path;
                a.pathIndex = 0;
                return;
            }
        }
    }

    // ── Space-Time A* implementation ─────────────────────────────────────

    /**
     * A* search node in (x, y, t) space.
     */
    private static final class STNode implements Comparable<STNode> {
        final int x, y, t;
        final int g;       // g = t (cost = time steps elapsed)
        final int h;       // h = Manhattan distance to goal
        final int f;       // f = g + h
        final STNode parent;

        STNode(int x, int y, int t, int g, int h, STNode parent) {
            this.x = x; this.y = y; this.t = t;
            this.g = g; this.h = h; this.f = g + h;
            this.parent = parent;
        }

        @Override
        public int compareTo(STNode o) {
            // Primary: f-value.  Tiebreak: lower h (closer to goal).
            int cmp = Integer.compare(this.f, o.f);
            return cmp != 0 ? cmp : Integer.compare(this.h, o.h);
        }
    }

    /**
     * Cooperative A* (Silver, 2005) — single-agent search in (x, y, t) space.
     *
     * Returns the planned path as a list of (x, y) cells from start to goal,
     * or null if no collision-free path exists within the horizon.
     */
    private java.util.List<int[]> spaceTimeAStar(String amrId, int[] start, int[] goal) {
        int gx = goal[0], gy = goal[1];
        int sx = start[0], sy = start[1];

        java.util.PriorityQueue<STNode> open = new java.util.PriorityQueue<>();
        java.util.HashSet<Long> closed = new java.util.HashSet<>();

        int h0 = Math.abs(gx - sx) + Math.abs(gy - sy);
        open.add(new STNode(sx, sy, 0, 0, h0, null));

        // Direction deltas: N, S, E, W, Wait
        int[][] dirs = {{0, -1}, {0, 1}, {1, 0}, {-1, 0}, {0, 0}};

        while (!open.isEmpty()) {
            STNode cur = open.poll();

            // Goal reached
            if (cur.x == gx && cur.y == gy) {
                return reconstructPath(cur);
            }

            long key = ((long) cur.x << 24) | ((long) cur.y << 12) | cur.t;
            if (closed.contains(key)) continue;
            closed.add(key);

            int nt = cur.t + 1;
            if (nt >= HORIZON_TICKS) continue;  // horizon exceeded — prune

            for (int[] d : dirs) {
                int nx = cur.x + d[0];
                int ny = cur.y + d[1];

                // Bounds check
                if (nx < 0 || nx >= gridCols || ny < 0 || ny >= gridRows) continue;

                // Vertex conflict: cell occupied by another AMR at time nt
                String occupant = reservedBy[nx][ny][nt];
                if (occupant != null && !occupant.equals(amrId)) continue;

                // Edge/swap conflict: another AMR crossing the same edge in
                // the opposite direction at the same tick
                if (d[0] != 0 || d[1] != 0) {  // skip for wait action
                    long reverseEdge = edgeKey(nx, ny, cur.x, cur.y, cur.t);
                    if (edgeReservations.contains(reverseEdge)) continue;
                }

                long nkey = ((long) nx << 24) | ((long) ny << 12) | nt;
                if (closed.contains(nkey)) continue;

                int nh = Math.abs(gx - nx) + Math.abs(gy - ny);
                open.add(new STNode(nx, ny, nt, nt, nh, cur));
            }
        }

        return null;  // no path found within horizon
    }

    private java.util.List<int[]> reconstructPath(STNode goal) {
        java.util.LinkedList<int[]> path = new java.util.LinkedList<>();
        STNode cur = goal;
        while (cur.parent != null) {
            path.addFirst(new int[]{cur.x, cur.y});
            cur = cur.parent;
        }
        return path;
    }

    /**
     * Writes a planned path into both {@code reservedBy[x][y][t]} and
     * {@code edgeReservations}.
     */
    private void commitReservation(String amrId, java.util.List<int[]> path) {
        int prevX = -1, prevY = -1;
        for (int t = 0; t < path.size() && t < HORIZON_TICKS; t++) {
            int[] cell = path.get(t);
            int cx = cell[0], cy = cell[1];
            reservedBy[cx][cy][t + 1] = amrId;  // t+1 because t=0 is "now"

            // Record edge reservation if this is a move (not a wait)
            if (prevX >= 0 && (prevX != cx || prevY != cy)) {
                edgeReservations.add(edgeKey(prevX, prevY, cx, cy, t));
            }
            prevX = cx;
            prevY = cy;
        }
    }

    @OPERATION
    public void getGridUtilization(OpFeedbackParam<Double> util) {
        try {
            if (RunManager.getSimulator(runId).gridStress) {
                util.set(0.95);
                return;
            }
            long occupied = 0;
            for (String[][] row : reservedBy)
                for (String[] cell : row)
                    for (String amrId : cell)
                        if (amrId != null)
                            occupied++;
            util.set((double) occupied / (gridCols * gridRows * HORIZON_TICKS));
        } catch (Exception e) {
            e.printStackTrace();
            failed("Exception in getGridUtilization: " + e.getMessage());
        }
    }

    public void clearExpiredReservations() {
        synchronized (reservedBy) {
            // Shift vertex reservations forward by one tick
            for (int x = 0; x < gridCols; x++) {
                for (int y = 0; y < gridRows; y++) {
                    for (int t = 0; t < HORIZON_TICKS - 1; t++) {
                        reservedBy[x][y][t] = reservedBy[x][y][t + 1];
                    }
                    reservedBy[x][y][HORIZON_TICKS - 1] = null;
                }
            }
            // Shift edge reservations: remove all edges at t=0, then rebuild
            // (edge keys encode absolute t, so we clear and let the next
            // commitReservation() repopulate as needed).  This is cheap at
            // current fleet sizes.
            edgeReservations.clear();
        }
    }

    /**
     * ROOT CAUSE FIX (getGridUtilization always reporting 0.0): reservedBy
     * was declared and read (here and in getGridUtilization()) but never
     * written anywhere — reserveTrajectory() is a stub nobody calls, so the
     * grid-saturation deadlock-resolution path in supervisor_agent.asl and
     * amr_agent.asl's notify_grid_saturation check could never fire under
     * real load. This rebuilds the instantaneous occupancy slice (index 0)
     * from each AMR's actual current cell every tick — cheap, always
     * consistent (no stale-entry bookkeeping needed since it's a full
     * rebuild), and makes existing utilization-based logic observe reality.
     * It only records presence for monitoring; it does not gate or block
     * movement.
     */
    private void refreshGridOccupancy() {
        synchronized (reservedBy) {
            for (int x = 0; x < gridCols; x++) {
                for (int y = 0; y < gridRows; y++) {
                    for (int t = 0; t < HORIZON_TICKS - 1; t++) {
                        reservedBy[x][y][t] = reservedBy[x][y][t + 1];
                    }
                    reservedBy[x][y][HORIZON_TICKS - 1] = null;
                }
            }
            for (AMRSim a : fleet) {
                int gx = (int) a.x;
                int gy = (int) a.y;
                if (gx >= 0 && gx < gridCols && gy >= 0 && gy < gridRows) {
                    reservedBy[gx][gy][0] = a.amrId;
                }
            }
        }
    }

    // ROOT CAUSE FIX (IllegalMonitorStateException from Artifact.signal()):
    // updatePositions() is called directly from MainSimulator's own
    // simulation thread (see MainSimulator.tickLoop), not dispatched
    // through CArtAgO's normal @OPERATION mechanism — so nothing acquires
    // the artifact's internal lock before stepAMR() below calls signal().
    // CArtAgO only manages that lock automatically for operations invoked
    // through the agent action pipeline. For any external thread that
    // needs to mutate artifact state / fire signals directly, CArtAgO's
    // idiom is beginExtSession()/endExtSession() — the same pattern
    // already used in UtilitySystemArtifact.updateFromStateVector() for
    // the identical situation (external simulator thread calling in).
    public void updatePositions(double simTime, double dt) {
        this.currentSimTime = simTime;
        this.tickDt = dt;
        if (fleet == null) return;

        beginExtSession();
        try {
            // Sort the fleet so that AMRs that have been blocked get priority in planning
            java.util.List<AMRSim> planningOrder = new java.util.ArrayList<>(java.util.Arrays.asList(fleet));
            planningOrder.sort(java.util.Comparator.comparingInt((AMRSim a) -> a.blockedTicks).reversed());

            for (AMRSim a : planningOrder) {
                stepAMR(a, dt);
            }
            refreshGridOccupancy();
            publishSnapshot();

            boolean anyActive = false;
            double soonestNeed = Double.MAX_VALUE;
            for (AMRSim a : fleet) {
                if (a.status != AMRStatusEnum.AMR_IDLE) {
                    anyActive = true;
                    double need = Math.min(a.secPerCell, Math.max(a.dwellRemaining, 0.05));
                    if (need < soonestNeed) soonestNeed = need;
                }
            }
            if (anyActive) {
                RunManager.getSimulator(runId).submitNER("amr_fleet", simTime + soonestNeed);
            } else {
                RunManager.getSimulator(runId).removeNER("amr_fleet");
            }
        } finally {
            endExtSession();
        }
    }

    private void stepAMR(AMRSim a, double dt) {
        if (a.dwellRemaining > 0) {
            a.dwellRemaining -= dt;
            return;
        }

        if (a.path.isEmpty() || a.pathIndex >= a.path.size()) {
            if (!a.carryingOrderId.isEmpty() && a.destinations.isEmpty()) {
                // Arrived at final destination (dropoff)
                signal("amr_arrived", a.amrId, a.carryingOrderId);
                a.carryingOrderId = "";
                a.pendingOrderId = "";
                a.completedJobCount++;
                a.status = AMRStatusEnum.AMR_UNLOADING;
            } else if (!a.pendingOrderId.isEmpty() && a.carryingOrderId.isEmpty() && a.destinations.size() == 1) {
                // Reached pickup (one destination left, the dropoff)
                a.carryingOrderId = a.pendingOrderId;
                a.status = AMRStatusEnum.AMR_LOADING;
            } else {
                a.status = AMRStatusEnum.AMR_IDLE;
            }

            // Free and there's a queued job waiting for this AMR — start it
            // now instead of idling or (previously) wandering off to a
            // random station.
            if (a.destinations.isEmpty() && isFree(a) && !a.jobQueue.isEmpty()) {
                startJob(a, a.jobQueue.poll());
            }

            int targetX = (int) a.x;
            int targetY = (int) a.y;

            String poppedDest = null;
            if (a.pendingDest != null) {
                poppedDest = a.pendingDest;
                a.pendingDest = null;
            } else if (!a.destinations.isEmpty()) {
                poppedDest = a.destinations.removeFirst();
            }

            if (poppedDest != null) {
                int idx = stationIndex(poppedDest);
                if (idx >= 0) {
                    targetX = STATION_CELLS[idx][0];
                    targetY = STATION_CELLS[idx][1];
                } else {
                    targetX = a.homeX;
                    targetY = a.homeY;
                    a.carryingOrderId = "";
                }
            } else {
                // No destination -> go home
                targetX = a.homeX;
                targetY = a.homeY;
                a.carryingOrderId = "";
            }

            // Use Space-Time A* for collision-free paths when possible;
            // The reservation table is updated by commitReservation().
            java.util.List<int[]> astarPath = spaceTimeAStar(
                    a.amrId, new int[]{(int) a.x, (int) a.y}, new int[]{targetX, targetY});

            if (astarPath != null && !astarPath.isEmpty()) {
                commitReservation(a.amrId, astarPath);
                a.path = astarPath;
                a.pathIndex = 0;
                a.dwellRemaining = 0.6; // brief load/unload pause at each stop
                a.blockedTicks = 0;
                return;
            } else {
                // Congestion denial. Do NOT move, and do NOT drop the destination.
                a.pendingDest = poppedDest;
                a.blockedTicks++;
                a.status = AMRStatusEnum.AMR_BLOCKED;
                a.path = java.util.Collections.emptyList();
                a.pathIndex = 0;
                a.dwellRemaining = 1.0; // BLOCKED_RETRY_COOLDOWN_S

                if (a.blockedTicks == 3) { // BLOCKED_SIGNAL_THRESHOLD
                    signal("amr_transport_blocked", a.amrId, a.carryingOrderId);
                }
                return;
            }
        }

        // Advance along current path segment.
        int[] target = a.path.get(a.pathIndex);
        a.nextX = target[0];
        a.nextY = target[1];
        a.status = AMRStatusEnum.AMR_MOVING;

        a.progress += (float) (dt / a.secPerCell);
        if (a.progress >= 1f) {
            a.x = a.nextX;
            a.y = a.nextY;
            a.progress = 0f;
            a.pathIndex++;
        }
    }

    private int stationIndex(String stationId) {
        if (stationId == null) return -1;
        
        // Handle station_X_Y formats by extracting the core station number.
        // e.g. "station_1_4" -> "S1"
        String norm = stationId;
        if (norm.startsWith("station_")) {
            String[] parts = norm.split("_");
            if (parts.length >= 2) {
                norm = "S" + parts[1];
            }
        } else {
            norm = norm.replace("station_", "S").toUpperCase();
        }

        switch (norm) {
            case "S1": return 0;
            case "S2": return 1;
            case "S3": return 2;
            case "S4": return 3;
            case "S5": return 4;
            default: return -1;
        }
    }

    /**
     * Simple orthogonal (Manhattan) path: horizontal run then vertical run.
     *
     * Both loops already terminate on their own — Integer.compare gives a
     * fixed-sign step and each iteration strictly closes the remaining
     * distance to x1/y1 — so this cannot loop forever for well-formed grid
     * coordinates. maxSteps below is a defense-in-depth guard, not a fix for
     * an observed hang: if coordinates were ever corrupted upstream (e.g. a
     * future bug feeding NaN-derived or out-of-grid values into stationIndex
     * lookups), this fails loudly with a bounded, logged path instead of
     * an unbounded loop that would eventually OOM the whole simulation.
     */
    private java.util.List<int[]> manhattanPath(int x0, int y0, int x1, int y1) {
        java.util.List<int[]> pts = new java.util.ArrayList<>();
        int maxSteps = 2 * (gridCols + gridRows) + 4;
        int x = x0;
        int stepX = Integer.compare(x1, x0);
        int guard = 0;
        while (x != x1) {
            x += stepX;
            pts.add(new int[]{x, y0});
            if (++guard > maxSteps) {
                log("manhattanPath: exceeded max steps computing (" + x0 + "," + y0 + ")->("
                        + x1 + "," + y1 + "); truncating path to avoid an unbounded loop");
                return pts;
            }
        }
        int y = y0;
        int stepY = Integer.compare(y1, y0);
        guard = 0;
        while (y != y1) {
            y += stepY;
            pts.add(new int[]{x1, y});
            if (++guard > maxSteps) {
                log("manhattanPath: exceeded max steps computing (" + x0 + "," + y0 + ")->("
                        + x1 + "," + y1 + "); truncating path to avoid an unbounded loop");
                return pts;
            }
        }
        if (pts.isEmpty()) pts.add(new int[]{x1, y1});
        return pts;
    }

    public java.util.List<Integer> getCompletedJobCounts() {
        java.util.List<Integer> counts = new java.util.ArrayList<>();
        if (fleet != null) {
            for (AMRSim a : fleet) {
                counts.add(a.completedJobCount);
            }
        }
        return counts;
    }

    private void publishSnapshot() {
        AMRSnapshot[] snap = new AMRSnapshot[fleet.length];
        for (int i = 0; i < fleet.length; i++) {
            AMRSim a = fleet[i];
            snap[i] = new AMRSnapshot(
                    a.amrId,
                    (int) a.x, (int) a.y,
                    (int) a.nextX, (int) a.nextY,
                    a.progress,
                    a.status,
                    a.carryingOrderId
            );
        }
        currentPositions = snap;
    }
}
