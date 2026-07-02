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
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the System
The multi-agent system runs via Gradle. You can pass various simulation arguments:

```bash
# Run with max ticks and log epochs
./gradlew run --args="--max-ticks=100 --log-epochs"

# Run a test simulating an energy price spike
./gradlew run --args="--price-series=price_series_spike_test.csv --max-ticks=100"
```