package factory;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.UUID;

/**
 * Minimal HMAC-SHA256 ticket issuer and verifier for WebSocket telemetry auth.
 *
 * <p>A ticket is a compact, signed, single-use token passed as a query parameter
 * on the WS handshake. Browsers' native {@code WebSocket} API cannot set custom
 * headers, so this ticket-based approach is the standard pattern (used by Slack
 * RTM, AWS IoT Core, GCP).
 *
 * <p>Ticket format: {@code base64(payload) "." base64(hmac-sha256(payload))}
 * where payload is {@code sub|run_id|iat|exp|jti}.
 *
 * <p>The HMAC secret is read from the {@code TELEMETRY_HMAC_SECRET} env var.
 * For local dev, a hardcoded fallback is used with a warning log.
 */
public final class TicketIssuer {

    private static final String ALGORITHM = "HmacSHA256";
    private static final long TICKET_TTL_MS = 10_000;  // 10 seconds
    private static final org.slf4j.Logger logger =
            org.slf4j.LoggerFactory.getLogger(TicketIssuer.class);

    private static volatile byte[] secretKey;

    private TicketIssuer() {}

    /** Lazily initialise the HMAC secret from env or fallback. */
    private static byte[] getSecretKey() {
        if (secretKey == null) {
            synchronized (TicketIssuer.class) {
                if (secretKey == null) {
                    String envSecret = System.getenv("TELEMETRY_HMAC_SECRET");
                    if (envSecret != null && !envSecret.isBlank()) {
                        secretKey = envSecret.getBytes(StandardCharsets.UTF_8);
                        logger.info("Telemetry HMAC secret loaded from TELEMETRY_HMAC_SECRET env var");
                    } else {
                        // Dev-only fallback — loud warning so this never slips into production
                        secretKey = "INSECURE_DEV_ONLY_FALLBACK_KEY_DO_NOT_USE_IN_PROD"
                                .getBytes(StandardCharsets.UTF_8);
                        logger.warn("TELEMETRY_HMAC_SECRET not set — using INSECURE dev-only fallback key. "
                                + "Set TELEMETRY_HMAC_SECRET before any non-loopback deployment.");
                    }
                }
            }
        }
        return secretKey;
    }

    /**
     * Parsed ticket claims.
     */
    public record Claims(String sub, int runId, long iat, long exp, String jti) {
        public boolean isExpired() {
            return System.currentTimeMillis() > exp;
        }
    }

    /**
     * Mint a new short-lived ticket for the given client/run pair.
     *
     * @param clientToken  opaque client identifier (e.g. session id)
     * @param runId        the run the ticket grants access to
     * @return a compact signed ticket string
     */
    public static String issue(String clientToken, int runId) {
        long now = System.currentTimeMillis();
        String jti = UUID.randomUUID().toString();
        String payload = clientToken + "|" + runId + "|" + now + "|" + (now + TICKET_TTL_MS) + "|" + jti;

        String encodedPayload = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
        String signature = sign(encodedPayload);

        return encodedPayload + "." + signature;
    }

    /**
     * Verify and parse a ticket. Returns null if the signature is invalid
     * or any claim is malformed.
     *
     * @param ticket the compact ticket string
     * @return parsed claims, or null on verification failure
     */
    public static Claims verifyAndParse(String ticket) {
        if (ticket == null || !ticket.contains(".")) return null;

        int dot = ticket.indexOf('.');
        String encodedPayload = ticket.substring(0, dot);
        String providedSignature = ticket.substring(dot + 1);

        String expectedSignature = sign(encodedPayload);
        if (!constantTimeEquals(expectedSignature, providedSignature)) {
            return null;  // invalid signature
        }

        try {
            String payload = new String(
                    Base64.getUrlDecoder().decode(encodedPayload), StandardCharsets.UTF_8);
            String[] parts = payload.split("\\|");
            if (parts.length != 5) return null;

            return new Claims(
                    parts[0],
                    Integer.parseInt(parts[1]),
                    Long.parseLong(parts[2]),
                    Long.parseLong(parts[3]),
                    parts[4]);
        } catch (Exception e) {
            return null;
        }
    }

    private static String sign(String data) {
        try {
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(new SecretKeySpec(getSecretKey(), ALGORITHM));
            byte[] sig = mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(sig);
        } catch (NoSuchAlgorithmException | InvalidKeyException e) {
            throw new RuntimeException("HMAC signing failed", e);
        }
    }

    /** Constant-time comparison to prevent timing attacks. */
    private static boolean constantTimeEquals(String a, String b) {
        if (a.length() != b.length()) return false;
        int result = 0;
        for (int i = 0; i < a.length(); i++) {
            result |= a.charAt(i) ^ b.charAt(i);
        }
        return result == 0;
    }
}
