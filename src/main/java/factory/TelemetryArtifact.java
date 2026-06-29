package factory;

import cartago.*;
import jakarta.websocket.ContainerProvider;
import jakarta.websocket.Session;
import jakarta.websocket.WebSocketContainer;
import java.net.URI;
import java.util.concurrent.atomic.AtomicReference;

public class TelemetryArtifact extends Artifact {
    private Session wsSession;
    
    void init(int port) {
        try {
            // Placeholder: The actual frontend dashboard is Phase 3. 
            // In a real scenario, this connects to the dashboard WS server.
            // WebSocketContainer container = ContainerProvider.getWebSocketContainer();
            // wsSession = container.connectToServer(MyEndpoint.class, URI.create("ws://localhost:8080/telemetry"));
        } catch (Exception e) {
            e.printStackTrace();
        }
        
        MainSimulator.INSTANCE.telemetryArtifact = this;
    }
    
    public void broadcast(TelemetryFrameSnapshot snap) {
        if (wsSession != null && wsSession.isOpen()) {
            try {
                // In Phase 3, this would serialize the Protobuf snap to binary or JSON
                // wsSession.getAsyncRemote().sendObject(snap.toByteArray());
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
    }
}
