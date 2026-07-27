# Quickstart Guide (Tutorial)

This step-by-step tutorial guides you through setting up and running **Matrix Factory Twin** locally in under 2 minutes.

---

## Prerequisites

Before starting, ensure your system has the following installed:
* **Java Development Kit (JDK 17+):** Required for JaCaMo MAS execution.
* **Python 3.10+:** Required for Numba JIT physical engine solvers.
* **Gradle:** Included via the repository wrapper (`./gradlew`).

---

## 1. Clone & Environment Setup

Clone the repository and set up a Python virtual environment:

```bash
# Clone repository
git clone https://github.com/utczbr/Matrix_Factory.git
cd Matrix_Factory

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install physical engine dependencies
pip install -r requirements.txt
```

---

## 2. Launching the Physical Daemon Bridge

Start the Python physical engine gRPC daemon bridge in the background:

```bash
python3 physical_engine/daemon_launcher.py --port 50051 &
```

Expected output:
```text
[DaemonLauncher] Starting SimBridge gRPC daemon on port 50051...
[DaemonLauncher] Physics kernels initialized (Numba JIT warmed up).
[DaemonLauncher] Listening for lock-stepped NER requests...
```

---

## 3. Running the JaCaMo Multi-Agent System

Execute the multi-agent co-simulation using the Gradle wrapper:

```bash
./gradlew run --args="0 50051 --max-ticks=1000"
```

Arguments:
* `0`: Seed for stochastic RNG generation.
* `50051`: Port of the gRPC physical bridge.
* `--max-ticks=1000`: Simulation duration threshold.

---

## 4. Viewing Real-Time Telemetry

Open your web browser and navigate to the live WebSocket telemetry dashboard:

```text
http://localhost:8081/telemetry
```

To authenticate the dashboard client with HMAC SHA-256 tokens:
```bash
curl -X POST http://127.0.0.1:8081/telemetry/ticket
```

---

## Next Steps

* Explore [Architecture Overview](architecture-overview.md) to understand how JaCaMo agents communicate with the physical engine.
* Inspect [Station Physical Solvers](../physical-engine/overview.md) for detailed mathematical models.
