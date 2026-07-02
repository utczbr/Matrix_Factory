package factory;

import cartago.*;
import java.util.Comparator;
import java.util.PriorityQueue;

public class TimerArtifact extends Artifact {
    private final PriorityQueue<TimerEntry> timerQueue = new PriorityQueue<>(
            Comparator.comparingDouble(TimerEntry::fireAtSimTime));

    private record TimerEntry(String orderId, double fireAtSimTime, String targetAgentId) {
    }
    private int runId;
    @OPERATION
    void init(int runId) {
        this.runId = runId;
        RunManager.getSimulator(runId).timerArtifact = this;
    }

    @OPERATION
    public void startTimer(String orderId, int ttlMs, Object agentIdObj) {
        String agentId = agentIdObj.toString();
        double currentSimTime = RunManager.getSimulator(runId).getCurrentTime();
        double fireAt = currentSimTime + ttlMs / 1000.0;
        System.out.println("[TimerArtifact] startTimer called. orderId=" + orderId + ", ttl=" + ttlMs + ", agentId=" + agentId + ", fireAt=" + fireAt);
        synchronized (timerQueue) {
            timerQueue.offer(new TimerEntry(orderId, fireAt, agentId));
        }
        RunManager.getSimulator(runId).submitNER(agentId, fireAt);
    }

    @OPERATION
    public void cancelTimer(String orderId) {
        synchronized (timerQueue) {
            timerQueue.removeIf(entry -> entry.orderId().equals(orderId));
        }
    }

    public void evaluateTTLs(double simTime) {
        synchronized (timerQueue) {
            while (!timerQueue.isEmpty() && timerQueue.peek().fireAtSimTime() <= simTime) {
                TimerEntry entry = timerQueue.poll();
                try {
                    System.out.println("[TimerArtifact] evaluateTTLs queuing signalTimerExpired for orderId=" + entry.orderId() + ", agentId=" + entry.targetAgentId());
                    execInternalOp("signalTimerExpired", entry.orderId(), entry.targetAgentId());
                    RunManager.getSimulator(runId).removeNER(entry.targetAgentId());
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
        }
    }

    @INTERNAL_OPERATION
    void signalTimerExpired(String orderId, String agentId) {
        System.out.println("[TimerArtifact] signalTimerExpired executed for orderId=" + orderId + ", agentId=" + agentId);
        signal("timer_expired", orderId, new jason.asSyntax.Atom(agentId));
    }
}
