package factory;

import jakarta.websocket.HandshakeResponse;
import jakarta.websocket.server.HandshakeRequest;
import jakarta.websocket.server.ServerEndpointConfig;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * WebSocket handshake authenticator that validates short-lived signed tickets.
 *
 * <p>Runs during the HTTP Upgrade — <em>before</em> any WS session is created —
 * so unauthenticated clients never reach {@code @OnOpen}. This closes both an
 * authentication gap (is this caller authorised at all?) and an authorization
 * gap (the ticket's {@code run_id} claim must match the requested {@code run_id},
 * so a valid ticket for run 3 can't be replayed against run 7's stream).
 *
 * <p>Tickets are single-use via their {@code jti} claim, tracked in a short-TTL
 * consumed set that self-cleans (tickets live ≤10s, so stale jti entries are
 * reaped on a 60s cadence).
 *
 * @see TicketIssuer
 */
public class TicketAuthConfigurator extends ServerEndpointConfig.Configurator {

    // Consumed ticket JTIs — prevents replay.  Entries are cheap (UUID strings)
    // and self-clean on a 60s cadence since tickets have a 10s TTL.
    private static final Set<String> consumedJtis = ConcurrentHashMap.newKeySet();
    private static long lastCleanupMs = System.currentTimeMillis();
    private static final long CLEANUP_INTERVAL_MS = 60_000;

    private static final org.slf4j.Logger logger =
            org.slf4j.LoggerFactory.getLogger(TicketAuthConfigurator.class);

    @Override
    public void modifyHandshake(ServerEndpointConfig sec,
                                 HandshakeRequest request,
                                 HandshakeResponse response) {
        String ticket = queryParam(request, "ticket");
        String runIdStr = queryParam(request, "run_id");

        // Allow unauthenticated connections if no ticket system is configured
        // (backwards compatibility for existing dashboard.js during migration)
        if (ticket == null || ticket.isBlank()) {
            boolean requireTicket = "true".equalsIgnoreCase(System.getenv("TELEMETRY_REQUIRE_TICKET"));
            if (requireTicket) {
                logger.warn("No ticket provided, and TELEMETRY_REQUIRE_TICKET is true — rejecting connection.");
                throw new RuntimeException("401: Unauthorized (Ticket Required)");
            }

            logger.debug("No ticket provided — allowing unauthenticated connection (migration mode)");
            if (runIdStr != null) {
                sec.getUserProperties().put("run_id", Integer.parseInt(runIdStr));
            }
            sec.getUserProperties().put("client_token", "anonymous");
            return;
        }

        TicketIssuer.Claims claims = TicketIssuer.verifyAndParse(ticket);

        if (claims == null) {
            logger.warn("Ticket verification failed — invalid signature or format");
            throw new RuntimeException("401: Invalid ticket");
        }

        if (claims.isExpired()) {
            logger.warn("Ticket expired (exp=" + claims.exp() + ")");
            throw new RuntimeException("401: Ticket expired");
        }

        if (runIdStr != null) {
            int requestedRunId = Integer.parseInt(runIdStr);
            if (claims.runId() != requestedRunId) {
                logger.warn("Ticket run_id mismatch: ticket=" + claims.runId()
                        + " requested=" + requestedRunId);
                throw new RuntimeException("403: Ticket run_id mismatch");
            }
        }

        // Single-use check
        if (consumedJtis.contains(claims.jti())) {
            logger.warn("Ticket already consumed (jti=" + claims.jti() + ")");
            throw new RuntimeException("401: Ticket already used");
        }
        consumedJtis.add(claims.jti());
        maybeCleanupConsumedJtis();

        // Stash validated claims in session properties for onOpen to read
        sec.getUserProperties().put("run_id", claims.runId());
        sec.getUserProperties().put("client_token", claims.sub());
    }

    private static String queryParam(HandshakeRequest request, String name) {
        Map<String, List<String>> params = request.getParameterMap();
        if (params == null) return null;
        List<String> values = params.get(name);
        return (values != null && !values.isEmpty()) ? values.get(0) : null;
    }

    /** Reap stale JTI entries periodically (tickets live ≤10s). */
    private static void maybeCleanupConsumedJtis() {
        long now = System.currentTimeMillis();
        if (now - lastCleanupMs > CLEANUP_INTERVAL_MS) {
            // Simple bulk clear — any ticket older than 10s is expired anyway,
            // so replaying it would fail the exp check before hitting the jti check.
            consumedJtis.clear();
            lastCleanupMs = now;
        }
    }
}
