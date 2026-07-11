package factory;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

public final class TicketHttpServer {

    public static void start(int port) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/telemetry/ticket", exchange -> {
            Map<String, String> q = parseQuery(exchange.getRequestURI().getQuery());
            int runId = Integer.parseInt(q.getOrDefault("run_id", "0"));
            String clientToken = q.getOrDefault("client", UUID.randomUUID().toString());

            String ticket = TicketIssuer.issue(clientToken, runId);
            byte[] body = ("{\"ticket\":\"" + ticket + "\"}").getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.getResponseHeaders().add("Access-Control-Allow-Origin", "*"); // loopback dev; tighten before non-loopback use
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) { 
                os.write(body); 
            }
        });
        server.setExecutor(null);
        server.start();
    }

    private static Map<String, String> parseQuery(String query) {
        Map<String, String> result = new HashMap<>();
        if (query == null) return result;
        for (String param : query.split("&")) {
            String[] entry = param.split("=");
            if (entry.length > 1) {
                result.put(entry[0], entry[1]);
            } else {
                result.put(entry[0], "");
            }
        }
        return result;
    }
}
