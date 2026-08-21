# Security & mTLS Configuration (How-To Guide)

This guide details certificate generation, **mutual TLS (mTLS)** across gRPC daemon channels, production fail-closed security guards, and HMAC ticket scope claims (`"telemetry"` vs `"control"`).

---

## Security Overview

IPC communication between the Java JVM and Python physical solvers is encrypted and authenticated via mTLS. In addition, HTTP telemetry and control endpoints enforce HMAC SHA-256 signed ticket tokens.

```mermaid
graph LR
    JVM["Java CArtAgO SimBridge (Client Certificate)"] ==>|TLS 1.3 mTLS (Encrypted gRPC)| DAEMON["Python SimBridge Daemon (Server Certificate)"]
    DASH["Dashboard Frontend"] -->|HMAC Ticket (scope="control")| HTTP["TicketHttpServer (Port 8081)"]
```

---

## Production Fail-Closed Security Guard

`MainSimulator.java` enforces a fail-closed guard when running in production environments (`MATRIX_FACTORY_ENV=production`):

```java
if ("production".equalsIgnoreCase(System.getenv("MATRIX_FACTORY_ENV"))) {
    if (!"true".equalsIgnoreCase(System.getenv("GRPC_SECURE_MODE"))
        || !"true".equalsIgnoreCase(System.getenv("TELEMETRY_REQUIRE_TICKET"))) {
        throw new IllegalStateException(
            "Refusing to start: GRPC_SECURE_MODE and TELEMETRY_REQUIRE_TICKET "
            + "must both be true when MATRIX_FACTORY_ENV=production");
    }
}
```

If launched under production settings without active TLS or ticket security, the JVM throws an `IllegalStateException` immediately at startup.

---

## Scoped Ticket Authentication (`TicketIssuer.java`)

Tickets carry explicit scope claims to prevent token replay across different security boundaries:

- **Telemetry Tickets**: Issued via `/telemetry/ticket?run_id=N` with payload claim `scope="telemetry"`.
- **Control Tickets**: Issued via `/control/ticket?run_id=N` with payload claim `scope="control"`.

Attempts to invoke `/control/action` endpoints with a telemetry-scoped ticket are rejected with `403 Forbidden`.

---

## Step 1: Automated Certificate Provisioning

`launch_phase4.sh` defaults to secure mode (`GRPC_SECURE_MODE:=true`, `TELEMETRY_REQUIRE_TICKET:=true`) and automatically executes `scripts/generate_certs.sh` on first run if certificate directories are absent:

```bash
bash scripts/generate_certs.sh certs/
```

This provisions 2048-bit RSA keys and certificates:
- `ca.key`, `ca.crt`: Root Certificate Authority.
- `server.key`, `server.crt`: Python gRPC Server certificate.
- `client.key`, `client.crt`: Java JVM gRPC Client certificate.

---

## Step 2: Running Secure Daemons & JVM Instances

```bash
export GRPC_SECURE_MODE=true
export TELEMETRY_REQUIRE_TICKET=true
export GRPC_CERT_DIR=certs

# 1. Start Python physical daemon in secure mTLS mode
python3 physical_engine/sim_bridge_server.py --port 50051 --run-id 0

# 2. Start Java MAS in secure mTLS mode
./gradlew run --args="0 50051 --max-ticks=1000"
```

Verification test suite:
* Test Script: [`physical_engine/factory_simulation/test_grpc_security.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/test_grpc_security.py)
