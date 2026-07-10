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

@ServerEndpoint(value = "/telemetry", configurator = TicketAuthConfigurator.class)
public class TelemetryWebSocketEndpoint {
    @OnOpen
    public void onOpen(Session session) {
        // When TicketAuthConfigurator validates a ticket, it stashes run_id
        // and client_token in session user properties.  Fall back to query
        // params for backwards compatibility during migration.
        Map<String, Object> userProps = session.getUserProperties();
        int runId;
        String clientToken;

        if (userProps.containsKey("run_id")) {
            runId = (int) userProps.get("run_id");
            clientToken = (String) userProps.getOrDefault("client_token", session.getId());
        } else {
            // Legacy path: read from query params (no ticket)
            Map<String, List<String>> params = session.getRequestParameterMap();
            runId = Integer.parseInt(params.getOrDefault("run_id", List.of("0")).get(0));
            clientToken = params.getOrDefault("client", List.of(session.getId())).get(0);
        }

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

