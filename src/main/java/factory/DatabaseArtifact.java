package factory;

import cartago.*;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.Statement;

public class DatabaseArtifact extends Artifact {
    private Connection conn;
    
    void init(String dbPath) {
        try {
            conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath);
            try (Statement stmt = conn.createStatement()) {
                stmt.execute("CREATE TABLE IF NOT EXISTS Orders (" +
                    "order_id TEXT PRIMARY KEY, " +
                    "received_time REAL, " +
                    "finished_time REAL, " +
                    "revenue REAL, " +
                    "penalty REAL)");
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
    
    @OPERATION
    public void recordOrderStart(String orderId, double simTime) {
        try (PreparedStatement pstmt = conn.prepareStatement(
            "INSERT INTO Orders (order_id, received_time) VALUES (?, ?)")) {
            pstmt.setString(1, orderId);
            pstmt.setDouble(2, simTime);
            pstmt.executeUpdate();
        } catch (Exception e) {
            failed("DB error: " + e.getMessage());
        }
    }
    
    @OPERATION
    public void recordOrderFinish(String orderId, double simTime, double revenue, double penalty) {
        try (PreparedStatement pstmt = conn.prepareStatement(
            "UPDATE Orders SET finished_time = ?, revenue = ?, penalty = ? WHERE order_id = ?")) {
            pstmt.setDouble(1, simTime);
            pstmt.setDouble(2, revenue);
            pstmt.setDouble(3, penalty);
            pstmt.setString(4, orderId);
            pstmt.executeUpdate();
        } catch (Exception e) {
            failed("DB error: " + e.getMessage());
        }
    }
}
