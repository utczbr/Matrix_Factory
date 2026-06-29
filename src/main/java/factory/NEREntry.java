package factory;

public record NEREntry(String agentId, double requestedNextTime) 
    implements Comparable<NEREntry> {
    @Override
    public int compareTo(NEREntry o) {
        return Double.compare(this.requestedNextTime, o.requestedNextTime);
    }
}
