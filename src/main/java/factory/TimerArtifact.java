package factory;

import cartago.*;
import java.util.Comparator;
import java.util.PriorityQueue;

public class TimerArtifact extends Artifact {
    private final PriorityQueue<TimerEntry> timerQueue = new PriorityQueue<>(
        Comparator.comparingDouble(TimerEntry::fireAtSimTime)
    );
    private record TimerEntry(String orderId, double fireAtSimTime, String targetAgentId) {}

    void init() {
        MainSimulator.INSTANCE.timerArtifact = this;
    }

    @OPERATION
    public void startTimer(String orderId, double ttlMs, String agentId) {
        double currentSimTime = MainSimulator.INSTANCE.getCurrentTime();
        double fireAt = currentSimTime + ttlMs / 1000.0;
        synchronized(timerQueue) {
            timerQueue.offer(new TimerEntry(orderId, fireAt, agentId));
        }
    }

    @OPERATION
    public void cancelTimer(String orderId) {
        synchronized(timerQueue) {
            timerQueue.removeIf(entry -> entry.orderId().equals(orderId));
        }
    }

    public void evaluateTTLs(double simTime) {
        synchronized(timerQueue) {
            while (!timerQueue.isEmpty() && timerQueue.peek().fireAtSimTime() <= simTime) {
                TimerEntry entry = timerQueue.poll();
                try {
                    execInternalOp("signalTimerExpired", entry.orderId(), entry.targetAgentId());
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
        }
    }

    @INTERNAL_OPERATION
    void signalTimerExpired(String orderId, String agentId) {
        signal("timer_expired", orderId, agentId);
    }
}
