# Matrix Factory Twin

The Matrix Factory Twin is an advanced, event-driven multi-agent simulation framework that models a responsive, dynamic manufacturing environment.

It features a hybrid architecture combining a Java-based multi-agent system (MAS) with a Python-based physical engine, bridged via gRPC. 

## Key Features

- **Multi-Agent Orchestration (JaCaMo):** Agent behaviors are programmed using the Jason BDI (Belief-Desire-Intention) language, coordinating seamlessly through CArtAgO artifacts.
- **Dynamic Structural Transitions (ADACOR / PROSA):** The system dynamically shifts between the PROSA (hierarchical/heterarchical) and ADACOR (agile/adaptive) control schemas.
- **Tick-based Simulation Engine:** Replaces wall-clock dependencies (e.g., `Thread.sleep`) with a deterministic, synchronized `MainSimulator` tick loop.
- **Two-Phase Commit Synchronization:** Safe transitional state handling using Phase 0 (Drain) and Phase 1 (Suspend) logic to pause and restructure operations during market events.
- **Energy Price Hysteresis:** An event-driven `EnergyPriceArtifact` triggers structural transitions based on dynamic pricing thresholds and hysteresis bands.
- **Python Physical Engine:** A Python backend handles complex physical and thermodynamic simulations (PEM fuel cells, thermal models, compressors) using Numba for optimization and gRPC for communication with the MAS layer.

## Architecture Stack

### Multi-Agent System (MAS)
* **Jason:** BDI Agent reasoning (e.g., `supervisor_agent.asl`, `order_manager.asl`).
* **CArtAgO:** Environment artifacts (e.g., `TimerArtifact`, `EnergyPriceArtifact`, `SupervisorArtifact`).
* **Gradle:** Build and dependency management.

### Physical Engine
* **Python 3.11+:** Backend runtime.
* **gRPC / Protocol Buffers:** High-performance RPC bridge between the Python simulation and Java agents.
* **Numba & NumPy:** High-performance computation for physical models.

## Getting Started

### Python Environment
1. Ensure Python 3.11+ is installed.
2. Create and activate a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the System
The simulation requires both the Python backend and the Java MAS engine running.

**1. Start the Python physical engine daemon (in `venv`):**
```bash
python -m physical_engine.sim_bridge_server --port=50051 --run-id=0
```

**2. Start the Multi-Agent System (MAS) via Gradle:**
```bash
# Run with parameter overrides (run_id, port, max_ticks)
./gradlew run --args="0 50051 --max-ticks=1000"
```

## Advanced Features (Phase 3.5+)

- **Asynchronous Telemetry:** Embedded Tyrus standalone WebSocket server (`ws://127.0.0.1:8080/telemetry`) securely multiplexes and streams real-time simulation state to clients without blocking BDI reasoning.
- **Asynchronous Database Drain:** Thread-safe, lock-free SQLite JDBC integration utilizing `ArrayBlockingQueue`, WAL pragmas, and adaptive batching for high-throughput historic data storage.

## Phase 4: High-Concurrency Monte Carlo Scale

Phase 4 introduces a Single-JVM Fan-Out architecture, allowing up to 30 parallel, fully isolated JaCaMo simulation runs to execute within a single JVM instance. This avoids the memory overhead of spawning 30 separate JVMs.

Key features of Phase 4 scaling:
- **Namespace-Rewriting Generator:** `scripts/generate_factory_jcm.py` dynamically rewrites ASL definitions and bindings to create strictly isolated agent namespaces (e.g., `run_0_amr_agent`, `run_1_amr_agent`) without cross-talk.
- **Isolated State Registry:** `RunManager` explicitly tracks and binds artifact state to its respective run ID.
- **Pinned Execution:** The multi-agent JVM operates on a restricted set of CPU cores while the Python physical engine daemons utilize the rest.

### Running Phase 4 (Full Scale)
To launch a full 30-run Monte Carlo simulation:
```bash
./scripts/launch_phase4.sh
```
This script will automatically:
1. Spin up 30 isolated Python `sim_bridge_server` daemons (ports `50051`-`50080`).
2. Generate the isolated `factory_phase4.jcm` and required ASL files using the namespace-rewriting generator.
3. Wait for all gRPC endpoints to become ready.
4. Launch a single, taskset-pinned JVM via Gradle that orchestrates all 30 parallel runs.
### The PROSA vs ADACOR Experiment
The central experiment of this repository compares the PROSA baseline against the ADACOR transition logic during an energy price spike. The full 3600-tick Monte Carlo simulation (`experiments/run_prosa_vs_adacor.py`) is designed to evaluate:
- **PROSA**: Maintains steady order admission, leading to AMR fleet saturation, high work-in-process (WIP), and extremely high maximum cycle times (tardiness) during the energy spike.
- **ADACOR**: The supervisor safely triggers a Two-Phase Commit to transition to an agile schema, temporarily throttling order admission. This sacrifices short-term throughput but aims to avoid buffer saturation, yielding better aggregate throughput and more controlled maximum tardiness over a long horizon.

> [!WARNING]
> **Defective Baseline Data:** Analysis of the headline dataset (`analysis/results.csv`) reveals that the ADACOR arm failed to complete orders in **15 out of 15 runs** (0 throughput) due to a suspend/resume deadlock bug in the order holons. The original claims that ADACOR "yields better aggregate throughput" are unsupported by this data. The recent patch fixes this deadlock; a new dataset must be generated to evaluate the true efficacy of the ADACOR schema.

## Known Limitations
- **gRPC Security**: The communication between the CArtAgO artifacts (Java) and the physical engine daemons (Python) uses plaintext gRPC. In a production cloud environment, this should be upgraded to use TLS/mTLS to secure the telemetry and command streams.
