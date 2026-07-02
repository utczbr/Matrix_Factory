package factory;

import jakarta.websocket.OnClose;
import jakarta.websocket.OnOpen;
import jakarta.websocket.Session;
import jakarta.websocket.server.ServerEndpoint;
import java.util.concurrent.atomic.AtomicReference;

@ServerEndpoint("/telemetry")
public class TelemetryWebSocketEndpoint {
    private static final AtomicReference<Session> CURRENT = new AtomicReference<>();

    @OnOpen
    public void onOpen(Session session) {
        Session prior = CURRENT.getAndSet(session);
        if (prior != null && prior.isOpen() && !prior.getId().equals(session.getId())) {
            try { prior.close(); } catch (Exception ignored) {}
        }
    }

    @OnClose
    public void onClose(Session session) {
        CURRENT.compareAndSet(session, null);
    }

    static Session currentSession() {
        Session s = CURRENT.get();
        if (s != null && !s.isOpen()) {
            CURRENT.compareAndSet(s, null);
            return null;
        }
        return s;
    }
}
