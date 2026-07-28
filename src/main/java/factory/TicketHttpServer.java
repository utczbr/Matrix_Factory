package factory;

import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class TicketHttpServer {
    private static final Logger logger = LoggerFactory.getLogger(TicketHttpServer.class);
    private static HttpServer server;

    public static synchronized void start(int port) throws IOException {
        if (server != null) {
            return;
        }
        server = HttpServer.create(new InetSocketAddress(port), 0);

        // Telemetry Ticket Endpoint
        server.createContext("/telemetry/ticket", exchange -> {
            Map<String, String> q = parseQuery(exchange.getRequestURI().getQuery());
            int runId = Integer.parseInt(q.getOrDefault("run_id", "0"));
            String clientToken = q.getOrDefault("client", UUID.randomUUID().toString());

            String ticket = TicketIssuer.issue(clientToken, runId, "telemetry");
            byte[] body = ("{\"ticket\":\"" + ticket + "\"}").getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });

        // Control Ticket Endpoint
        server.createContext("/control/ticket", exchange -> {
            Map<String, String> q = parseQuery(exchange.getRequestURI().getQuery());
            int runId = Integer.parseInt(q.getOrDefault("run_id", "0"));
            String clientToken = q.getOrDefault("client", UUID.randomUUID().toString());

            String ticket = TicketIssuer.issue(clientToken, runId, "control");
            byte[] body = ("{\"ticket\":\"" + ticket + "\"}").getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });

        // Control Action Endpoint
        server.createContext("/control/action", exchange -> {
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*");
                exchange.getResponseHeaders().add("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
                exchange.getResponseHeaders().add("Access-Control-Allow-Headers", "Content-Type");
                exchange.sendResponseHeaders(204, -1);
                return;
            }

            String ticket = null;
            String type = null;
            String stationId = null;
            String amrId = null;
            String paramName = null;
            double value = 0.0;
            double downtimeSeconds = 60.0;
            int runId = 0;

            String queryStr = exchange.getRequestURI().getQuery();
            if (queryStr != null) {
                Map<String, String> q = parseQuery(queryStr);
                ticket = q.get("ticket");
                type = q.get("type");
                stationId = q.get("stationId");
                amrId = q.get("amrId");
                paramName = q.get("param");
                if (q.containsKey("value")) value = Double.parseDouble(q.get("value"));
                if (q.containsKey("downtimeSeconds")) downtimeSeconds = Double.parseDouble(q.get("downtimeSeconds"));
                if (q.containsKey("run_id")) runId = Integer.parseInt(q.get("run_id"));
            }

            if (ticket == null && "POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                InputStream is = exchange.getRequestBody();
                String bodyStr = new String(is.readAllBytes(), StandardCharsets.UTF_8);
                Map<String, String> jsonMap = parseJsonSimple(bodyStr);
                ticket = jsonMap.get("ticket");
                type = jsonMap.get("type");
                stationId = jsonMap.get("stationId");
                amrId = jsonMap.get("amrId");
                paramName = jsonMap.get("param");
                if (jsonMap.containsKey("value")) value = Double.parseDouble(jsonMap.get("value"));
                if (jsonMap.containsKey("downtimeSeconds")) downtimeSeconds = Double.parseDouble(jsonMap.get("downtimeSeconds"));
                if (jsonMap.containsKey("runId")) runId = Integer.parseInt(jsonMap.get("runId"));
            }

            TicketIssuer.Claims claims = TicketIssuer.verifyAndParse(ticket);
            if (claims == null || claims.isExpired() || !"control".equals(claims.scope())) {
                byte[] err = "{\"error\":\"Forbidden: Invalid or non-control ticket\"}".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*");
                exchange.sendResponseHeaders(403, err.length);
                try (OutputStream os = exchange.getResponseBody()) {
                    os.write(err);
                }
                return;
            }

            MainSimulator sim = RunManager.getSimulator(claims.runId() >= 0 ? claims.runId() : runId);
            boolean executed = false;

            if ("station_setpoint".equalsIgnoreCase(type) && sim != null && stationId != null && paramName != null) {
                for (Object obj : sim.stationArtifacts) {
                    if (obj instanceof BaseStationArtifact sta && sta.stationId.equalsIgnoreCase(stationId)) {
                        sta.adjustSetpoint(paramName, value);
                        executed = true;
                        break;
                    }
                }
            } else if ("amr_breakdown".equalsIgnoreCase(type) && sim != null && amrId != null) {
                if (sim.amrArtifact instanceof AMRArtifact amrArt) {
                    amrArt.triggerBreakdown(amrId, downtimeSeconds);
                    executed = true;
                }
            }

            byte[] resBody;
            int status = executed ? 200 : 400;
            if (executed) {
                resBody = "{\"status\":\"ok\",\"action\":\"applied\"}".getBytes(StandardCharsets.UTF_8);
            } else {
                resBody = "{\"status\":\"error\",\"message\":\"Target artifact or action parameter mismatch\"}".getBytes(StandardCharsets.UTF_8);
            }

            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(status, resBody.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(resBody);
            }
        });

        server.setExecutor(null);
        server.start();
        logger.info("TicketHttpServer started on port {}", port);
    }

    public static synchronized void stop() {
        if (server != null) {
            server.stop(0);
            server = null;
        }
    }

    private static Map<String, String> parseQuery(String query) {
        Map<String, String> result = new HashMap<>();
        if (query == null) return result;
        for (String param : query.split("&")) {
            String[] entry = param.split("=");
            if (entry.length > 1) {
                result.put(entry[0], entry[1]);
            } else if (entry.length == 1) {
                result.put(entry[0], "");
            }
        }
        return result;
    }

    private static Map<String, String> parseJsonSimple(String json) {
        Map<String, String> map = new HashMap<>();
        if (json == null || !json.contains("{")) return map;
        String clean = json.trim().replaceAll("[{}\"]", "");
        for (String pair : clean.split(",")) {
            String[] kv = pair.split(":");
            if (kv.length >= 2) {
                map.put(kv[0].trim(), kv[1].trim());
            }
        }
        return map;
    }
}
