package factory;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class OrderLedgerReader {

    private final String dbPath;

    public OrderLedgerReader(String dbPath) {
        this.dbPath = dbPath;
    }

    /**
     * Reads all order events for a given runId.
     */
    public Map<String, List<String>> getOrderEvents(int runId) {
        Map<String, List<String>> eventsByOrder = new HashMap<>();
        String query = "SELECT order_id, event_type FROM Orders WHERE run_id = ? ORDER BY sim_time ASC";
        
        try (Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath);
             PreparedStatement ps = conn.prepareStatement(query)) {
            ps.setInt(1, runId);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    String orderId = rs.getString("order_id");
                    String eventType = rs.getString("event_type");
                    eventsByOrder.computeIfAbsent(orderId, k -> new ArrayList<>()).add(eventType);
                }
            }
        } catch (SQLException e) {
            throw new RuntimeException("Failed to read orders from ledger", e);
        }
        return eventsByOrder;
    }
}
