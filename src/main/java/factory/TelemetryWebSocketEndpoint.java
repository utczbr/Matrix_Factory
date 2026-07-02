package factory;

import jakarta.websocket.CloseReason;
import jakarta.websocket.OnClose;
import jakarta.websocket.OnMessage;
import jakarta.websocket.OnOpen;
import jakarta.websocket.Session;
import jakarta.websocket.server.ServerEndpoint;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Map;

@ServerEndpoint("/telemetry")
public class TelemetryWebSocketEndpoint {
    @OnOpen
    public void onOpen(Session session) {
        Map<String, List<String>> params = session.getRequestParameterMap();
        int runId = Integer.parseInt(params.getOrDefault("run_id", List.of("0")).get(0));
        String clientToken = params.getOrDefault("client", List.of(session.getId())).get(0);
        TelemetryHub.register(session, runId, clientToken);
    }

    @OnMessage
    public void onMessage(Session session, ByteBuffer message) {
        try {
            session.close(new CloseReason(CloseReason.CloseCodes.CANNOT_ACCEPT, "publish-only"));
        } catch (Exception ignored) {
        }
    }

    @OnClose
    public void onClose(Session session) {
        TelemetryHub.unregister(session);
    }
}
