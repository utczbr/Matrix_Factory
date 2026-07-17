package factory;

import java.util.concurrent.CountDownLatch;

public record NEREntry(String agentId, double requestedNextTime, CountDownLatch tagLatch) 
    implements Comparable<NEREntry> {
    
    public NEREntry(String agentId, double requestedNextTime) {
        this(agentId, requestedNextTime, null);
    }

    @Override
    public int compareTo(NEREntry o) {
        return Double.compare(this.requestedNextTime, o.requestedNextTime);
    }
}
