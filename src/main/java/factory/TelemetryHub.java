package factory;

import jakarta.websocket.CloseReason;
import jakarta.websocket.Session;
import java.nio.ByteBuffer;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

final class TelemetryHub {
    private static final Map<String, Session> sessionsById = new ConcurrentHashMap<>();
    private static final Map<String, Integer> runIdBySessionId = new ConcurrentHashMap<>();
    private static final Map<String, Session> sessionByClientToken = new ConcurrentHashMap<>();

    private TelemetryHub() {
    }

    private static org.glassfish.tyrus.server.Server server;
    private static final java.util.concurrent.atomic.AtomicBoolean isRunning = new java.util.concurrent.atomic.AtomicBoolean(false);
    private static final org.slf4j.Logger logger = org.slf4j.LoggerFactory.getLogger(TelemetryHub.class);

    public static synchronized void startServer(int port) {
        if (isRunning.compareAndSet(false, true)) {
            server = new org.glassfish.tyrus.server.Server("127.0.0.1", port, "/", null, TelemetryWebSocketEndpoint.class);
            try {
                server.start();
                logger.info("Global Telemetry WebSocket server started on port " + port);
            } catch (Exception e) {
                logger.error("Failed to start Global Telemetry WebSocket server", e);
                isRunning.set(false);
            }

            // Start the HTTP ticket issuance endpoint on port+1 (e.g. 8081).
            // GET /telemetry/ticket?run_id=N → { "ticket": "<signed-token>" }
            // Uses JDK-builtin HttpServer — zero new dependency.
            try {
                int ticketPort = port + 1;
                com.sun.net.httpserver.HttpServer httpServer =
                        com.sun.net.httpserver.HttpServer.create(
                                new java.net.InetSocketAddress("127.0.0.1", ticketPort), 0);
                httpServer.createContext("/telemetry/ticket", exchange -> {
                    if (!"GET".equals(exchange.getRequestMethod())) {
                        exchange.sendResponseHeaders(405, -1);
                        exchange.close();
                        return;
                    }
                    String query = exchange.getRequestURI().getQuery();
                    int runId = 0;
                    String clientToken = "dashboard-" + System.currentTimeMillis();
                    if (query != null) {
                        for (String param : query.split("&")) {
                            String[] kv = param.split("=", 2);
                            if (kv.length == 2) {
                                if ("run_id".equals(kv[0])) runId = Integer.parseInt(kv[1]);
                                if ("client".equals(kv[0])) clientToken = kv[1];
                            }
                        }
                    }
                    String ticket = TicketIssuer.issue(clientToken, runId);
                    String json = "{\"ticket\":\"" + ticket + "\"}";
                    byte[] body = json.getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set("Content-Type", "application/json");
                    exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
                    exchange.sendResponseHeaders(200, body.length);
                    exchange.getResponseBody().write(body);
                    exchange.close();
                });
                httpServer.setExecutor(null);  // default executor
                httpServer.start();
                logger.info("Telemetry ticket endpoint started on http://127.0.0.1:" + ticketPort + "/telemetry/ticket");
            } catch (Exception e) {
                logger.error("Failed to start ticket HTTP endpoint", e);
            }
        }
    }

    static void register(Session session, int runId, String clientToken) {
        Session prior = sessionByClientToken.put(clientToken, session);
        sessionsById.put(session.getId(), session);
        runIdBySessionId.put(session.getId(), runId);

        if (prior != null && prior.isOpen() && !prior.getId().equals(session.getId())) {
            try {
                prior.close(new CloseReason(new CloseReason.CloseCode() {
                    @Override
                    public int getCode() {
                        return 4001;
                    }
                }, "SUPERSEDED"));
            } catch (Exception ignored) {
            }
        }
    }

    static void unregister(Session session) {
        sessionsById.remove(session.getId());
        runIdBySessionId.remove(session.getId());
        sessionByClientToken.values().removeIf(existing -> existing.getId().equals(session.getId()));
    }

    static void broadcast(
            int runId,
            ByteBuffer frameBytes,
            double simTimeS,
            Runnable confirmedDelivery,
            Runnable failedDelivery) {
        boolean delivered = false;
        for (Map.Entry<String, Integer> entry : runIdBySessionId.entrySet()) {
            if (entry.getValue() != runId) {
                continue;
            }
            Session session = sessionsById.get(entry.getKey());
            if (session == null || !session.isOpen()) {
                continue;
            }

            delivered = true;
            session.getAsyncRemote().sendBinary(frameBytes.duplicate(), result -> {
                if (result.isOK()) {
                    confirmedDelivery.run();
                } else {
                    failedDelivery.run();
                }
            });
        }

        if (!delivered) {
            failedDelivery.run();
        }
    }
}